"""Explicit local tools; no model-generated code or commands are executed."""
import importlib
import json
import re
import secrets
import uuid
from pathlib import Path

ABILITIES = ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')
COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


def roll_dice(expression: str):
    match = re.fullmatch(r'(\d{1,3})d(\d{1,4})([+-]\d{1,4})?', expression.replace(' ', ''))
    if not match:
        raise ValueError('Use NdS or NdS+modifier, such as 2d6+3')
    count, sides = map(int, match.group(1, 2))
    modifier = int(match.group(3) or 0)
    if not 1 <= count <= 100 or not 2 <= sides <= 1000:
        raise ValueError('Dice limits: 1–100 dice, 2–1000 sides')
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return {'rolls': rolls, 'modifier': modifier, 'total': sum(rolls) + modifier}


def ability_scores(method: str = 'standard', scores: dict | None = None):
    if method == 'roll':
        dice = [[secrets.randbelow(6) + 1 for _ in range(4)] for _ in range(6)]
        return {'method': method, 'rolls': dice, 'scores': [sum(r) - min(r) for r in dice]}
    if method == 'standard':
        return {'method': method, 'scores': [15, 14, 13, 12, 10, 8],
                'note': 'Assign these to abilities before origin increases.'}
    if method != 'point_buy' or not isinstance(scores, dict) or set(scores) != set(ABILITIES):
        raise ValueError('point_buy requires all six named abilities')
    if any(type(v) is not int or v not in COST for v in scores.values()):
        raise ValueError('Base point-buy scores must be integers from 8 through 15')
    spent = sum(COST[v] for v in scores.values())
    return {'scores': scores, 'spent': spent, 'remaining': 27 - spent,
            'valid': spent <= 27, 'note': 'Base scores only, before origin increases.'}


def character_draft(name: str, character_class: str, species: str, background: str,
                    scores: dict, level: int = 1):
    if type(level) is not int or not 1 <= level <= 20:
        raise ValueError('Level must be 1–20')
    for value in (name, character_class, species, background):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError('Names and choices must be 1–200 characters')
    if not isinstance(scores, dict) or set(scores) != set(ABILITIES):
        raise ValueError('Provide all six abilities')
    if any(type(v) is not int or not 1 <= v <= 30 for v in scores.values()):
        raise ValueError('Scores must be integers from 1 through 30')
    return {'name': name, 'class': character_class, 'species': species,
            'background': background, 'level': level, 'scores': scores,
            'modifiers': {k: (v - 10) // 2 for k, v in scores.items()},
            'proficiency_bonus': 2 + (level - 1) // 4,
            'status': 'DRAFT — choices and origin increases require source verification',
            'remaining': ['Verify class/species/background availability and features',
                          'Verify score generation and origin increases',
                          'Choose proficiencies, equipment, spells, and feats',
                          'Calculate HP, AC, attacks, and resource limits from sources']}


def schema(name, description, properties, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties,
                           'required': list(required), 'additionalProperties': False}}}


def builtins():
    string = {'type': 'string'}
    score_schema = {'type': 'object', 'properties': {
        k: {'type': 'integer'} for k in ABILITIES}, 'required': list(ABILITIES),
        'additionalProperties': False}
    return [
        (roll_dice, schema('roll_dice', 'Roll bounded dice using real local randomness.',
                          {'expression': string}, ['expression'])),
        (ability_scores, schema('ability_scores', 'Standard array, 4d6 drop lowest, or 27-point buy. Base scores only.',
             {'method': {'type': 'string', 'enum': ['standard', 'roll', 'point_buy']},
              'scores': score_schema})),
        (character_draft, schema('character_draft', 'Create a draft and calculate modifiers. Does not certify rule legality.',
             {'name': string, 'character_class': string, 'species': string, 'background': string,
              'scores': score_schema, 'level': {'type': 'integer', 'minimum': 1, 'maximum': 20}},
             ['name', 'character_class', 'species', 'background', 'scores'])),
    ]


def validate_arguments(value, spec):
    expected = spec.get('type')
    checks = {'object': lambda v: isinstance(v, dict),
              'string': lambda v: isinstance(v, str),
              'integer': lambda v: type(v) is int,
              'number': lambda v: type(v) in (int, float),
              'array': lambda v: isinstance(v, list),
              'boolean': lambda v: type(v) is bool}
    if expected in checks and not checks[expected](value):
        raise ValueError(f'Tool argument must have type {expected}')
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError('Tool argument is not an allowed choice')
    if expected == 'object':
        properties = spec.get('properties', {})
        if any(k not in value for k in spec.get('required', [])):
            raise ValueError('Missing required tool arguments')
        if spec.get('additionalProperties') is False and set(value) - set(properties):
            raise ValueError('Unexpected tool arguments')
        for key, item in value.items():
            if key in properties:
                validate_arguments(item, properties[key])
    if expected in ('integer', 'number'):
        if value < spec.get('minimum', value) or value > spec.get('maximum', value):
            raise ValueError('Tool argument is out of range')


class Registry:
    def __init__(self):
        self.functions = {}
        self.schemas = []
        self.external = set()

    def add(self, function, specification, external=False):
        name = specification['function']['name']
        if name in self.functions or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,63}', name):
            raise ValueError('Duplicate or invalid tool name')
        self.functions[name] = function
        self.schemas.append(specification)
        if external:
            self.external.add(name)

    def load_extensions(self, path):
        """Load trusted installed Python modules explicitly listed by the user."""
        for entry in json.loads(Path(path).read_text()):
            module, attribute = entry['callable'].split(':', 1)
            function = getattr(importlib.import_module(module), attribute)
            self.add(function, entry['schema'], external=True)

    def call(self, name, arguments, approve=None):
        if name not in self.functions:
            raise ValueError('Unknown tool')
        if not isinstance(arguments, dict):
            raise ValueError('Tool arguments must be an object')
        specification = next(s for s in self.schemas if s['function']['name'] == name)
        validate_arguments(arguments, specification['function']['parameters'])
        if name in self.external and (approve is None or approve(name, arguments) is not True):
            raise PermissionError('External tool not approved')
        return self.functions[name](**arguments)


def save_draft(root, content):
    """Explicit CLI export; not exposed as a model tool."""
    directory = Path(root) / '.state' / 'characters'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{uuid.uuid4().hex}.json'
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False))
    return path

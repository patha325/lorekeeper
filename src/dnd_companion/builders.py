"""Brainstorm Club's documented-in-source legacy share-link protocol."""
import base64
import json
import re

from .tools import character_draft

CLASSES = set('barbarian bard cleric druid fighter monk paladin ranger rogue sorcerer warlock wizard'.split())
RACES_2014 = {'dragonborn', 'dwarf', 'elf', 'gnome', 'half-elf', 'half-orc', 'halfling', 'human', 'tiefling'}
RACES_2024 = {'dragonborn', 'dwarf', 'elf', 'gnome', 'goliath', 'halfling', 'human', 'orc', 'tiefling'}


def brainstorm_share(draft, edition):
    """Pre-fill a partial draft. Verify all derived fields inside the builder."""
    if edition not in {'2014', '2024'}:
        raise ValueError('Edition must be 2014 or 2024')
    validated = character_draft(draft['name'], draft['class'], draft['species'],
                                draft['background'], draft['scores'], draft.get('level', 1))
    def slug(value):
        return re.sub(r'\s+', '-', value.strip().lower())
    race, class_id = slug(validated['species']), slug(validated['class'])
    if class_id not in CLASSES or race not in (RACES_2014 if edition == '2014' else RACES_2024):
        raise ValueError('Share adapter currently supports SRD classes and race IDs only')
    compact = {'v': 'dnd5e' if edition == '2014' else 'dnd2024',
               'n': validated['name'], 'r': race, 'c': class_id,
               'lv': validated['level'], 'bg': slug(validated['background']),
               'as': {key[:3]: value for key, value in validated['scores'].items()}}
    payload = base64.urlsafe_b64encode(json.dumps(compact, ensure_ascii=False,
                                                separators=(',', ':')).encode()).decode().rstrip('=')
    if len(payload) > 20000:
        raise ValueError('Draft is too large for the builder share-link format')
    return 'https://brainstorm-club.github.io/dnd-character-builder/share/' + payload

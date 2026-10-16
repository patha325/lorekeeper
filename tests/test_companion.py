import base64
import json

import httpx
import pytest

from dnd_companion.assistant import Assistant
from dnd_companion.builders import brainstorm_share
from dnd_companion.knowledge import Knowledge
from dnd_companion.tools import ABILITIES, Registry, ability_scores, builtins, character_draft, roll_dice


def test_point_buy():
    scores = dict(zip(ABILITIES, [15, 15, 15, 8, 8, 8]))
    assert ability_scores('point_buy', scores)['remaining'] == 0
    scores['charisma'] = 15
    assert ability_scores('point_buy', scores)['valid'] is False
    with pytest.raises(ValueError):
        ability_scores('point_buy', {**scores, 'strength': True})


def test_rolls():
    assert 5 <= roll_dice('2d6+3')['total'] <= 15
    assert 6 <= roll_dice('1d20+5')['total'] <= 25
    for expression in ['__import__("os")', '0d6', '101d6', '1d1']:
        with pytest.raises(ValueError):
            roll_dice(expression)
    rolled = ability_scores('roll')
    assert rolled['scores'] == [sum(r) - min(r) for r in rolled['rolls']]


def test_draft_and_share():
    draft = character_draft('Éowyn', 'Fighter', 'Human', 'Acolyte', dict.fromkeys(ABILITIES, 10))
    assert draft['proficiency_bonus'] == 2
    url = brainstorm_share(draft, '2014')
    payload = url.rsplit('/', 1)[1]
    decoded = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    assert decoded['v'] == 'dnd5e'
    assert decoded['n'] == 'Éowyn'
    assert decoded['as'] == dict.fromkeys(['str', 'dex', 'con', 'int', 'wis', 'cha'], 10)
    assert decoded['c'] == 'fighter'


def test_external_approval():
    registry = Registry()
    function, specification = builtins()[0]
    registry.add(function, specification, external=True)
    with pytest.raises(PermissionError):
        registry.call('roll_dice', {'expression': '1d6'})
    assert registry.call('roll_dice', {'expression': '1d6'}, lambda *_: True)['total'] >= 1


class FakeEmbedding:
    def embed(self, texts, model):
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_edition_isolation_and_embedding_change(tmp_path):
    knowledge = Knowledge(tmp_path)
    knowledge.backend.client.close()
    knowledge.backend = FakeEmbedding()
    for edition, text in [('2014', 'Zombie HP 22'), ('2024', 'Zombie HP 15')]:
        folder = tmp_path / 'documents' / edition
        folder.mkdir(parents=True)
        (folder / 'zombie.txt').write_text(text)
        knowledge.index(edition)
    assert knowledge.search('Zombie', '2014')['sources'][0]['excerpt'] == 'Zombie HP 22'
    assert knowledge.search('Zombie', '2024')['sources'][0]['excerpt'] == 'Zombie HP 15'
    assert knowledge.search('notes', scope='campaign')['sources'] == []
    knowledge.embedding = 'different'
    with pytest.raises(RuntimeError, match='Re-index'):
        knowledge.search('Zombie')


def test_ollama_tool_loop_and_citations(tmp_path):
    replies = iter([
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'function': {'name': 'roll_dice', 'arguments': {'expression': '1d20'}}}]},
        {'role': 'assistant', 'content': 'The zombie has 22 HP [S1].'},
    ])
    def handle(request):
        body = json.loads(request.content)
        assert body['stream'] is False
        if len(body['messages']) > 4:
            assert body['messages'][-1]['role'] == 'tool'
        return httpx.Response(200, json={'message': next(replies)})
    assistant = Assistant(tmp_path, client=httpx.Client(
        base_url='http://localhost:11434', transport=httpx.MockTransport(handle)))
    assistant.knowledge.search = lambda *a, **k: {'sources': [
        {'collection': '2014', 'path': 'srd.pdf', 'page': 1, 'excerpt': 'Zombie HP 22', 'score': .9}], 'warning': None}
    result = assistant.ask('Zombie HP?')
    assert result['sources'][0]['id'] == 'S1'
    assert result['tools'][0]['name'] == 'roll_dice'
    assistant.close()


def test_unknown_tool_not_executed():
    with pytest.raises(ValueError):
        Registry().call('shell', {'command': 'anything'})


def test_model_argument_validation():
    registry = Registry()
    for function, specification in builtins():
        registry.add(function, specification)
    for args in [{'expression': 12}, {'expression': '1d6', 'command': 'bad'}, {}]:
        with pytest.raises(ValueError):
            registry.call('roll_dice', args)


def test_whitespace_normalization_and_provenance(tmp_path):
    folder = tmp_path / 'documents' / '2014'
    folder.mkdir(parents=True)
    (folder / 'rules.txt').write_text('Zombie\r\u00a0 hit\n points 22')
    knowledge = Knowledge(tmp_path)
    knowledge.backend.client.close()
    knowledge.backend = FakeEmbedding()
    knowledge.index('2014')
    source = knowledge.search('Zombie')['sources'][0]
    assert source['path'] == 'rules.txt'
    assert source['excerpt'] == 'Zombie hit points 22'


def test_pdf_neighbor_pages_are_retrieved(tmp_path):
    folder = tmp_path / 'documents' / '2014'
    folder.mkdir(parents=True)
    (folder / 'first.txt').write_text('Zombie Medium undead Hit Points 22')
    (folder / 'second.txt').write_text('Undead Fortitude. Ogre Zombie Hit Points 85')
    knowledge = Knowledge(tmp_path)
    knowledge.backend.client.close()
    knowledge.backend = FakeEmbedding()
    knowledge.index('2014')
    metadata = tmp_path / '.state' / '2014' / 'embedding.json'
    settings = json.loads(metadata.read_text())
    for origin in settings['provenance'].values():
        origin['page'] = 1 if origin['path'] == 'first.txt' else 2
        origin['path'] = 'rules.pdf'
    metadata.write_text(json.dumps(settings))
    result = knowledge.search('Zombie', limit=1)
    assert result['sources'][0]['pages'] == [1, 2]
    assert 'Hit Points 22' in result['sources'][0]['excerpt']
    assert 'Undead Fortitude' in result['sources'][0]['excerpt']

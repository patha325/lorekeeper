"""Version-isolated LibreIndex ingestion and evidence retrieval."""
import json
import re
import tempfile
import sys
import math
from pathlib import Path

import httpx
import lancedb
from libreindex import LibreIndex
from libreindex.backend import OllamaBackend
from libreindex.readers import discover, read


class BatchedBackend(OllamaBackend):
    def embed(self, texts, model):
        result = []
        for start in range(0, len(texts), 8):
            if len(texts) > 8 and start % 80 == 0:
                print(f'Embedding passages: {start}/{len(texts)}', file=sys.stderr, flush=True)
            response = self._post('/api/embed', {
                'model': model, 'input': list(texts[start:start + 8]), 'truncate': False,
                'keep_alive': 0 if getattr(self, 'unload_after_embed', False) else '5m',
            })
            vectors = response.json()['embeddings']
            if len(vectors) != len(texts[start:start + 8]):
                raise RuntimeError('Embedding count mismatch')
            if any(not v or not all(math.isfinite(x) for x in v) for v in vectors):
                raise RuntimeError('Invalid embedding')
            result.extend(vectors)
        return result


class Knowledge:
    def __init__(self, root, host='http://127.0.0.1:11434', embedding='embeddinggemma'):
        self.root = Path(root).resolve()
        self.embedding = embedding
        self.backend = BatchedBackend(host)

    def _paths(self, collection):
        if collection not in {'2014', '2024', 'campaign'}:
            raise ValueError('Collection must be 2014, 2024, or campaign')
        return self.root / 'documents' / collection, self.root / '.state' / collection

    def index(self, collection):
        folder, database = self._paths(collection)
        folder.mkdir(parents=True, exist_ok=True)
        # Some SRD PDF pages contain carriage returns between every word.
        # Normalize before chunking while keeping original file/page provenance.
        provenance = {}
        skipped = 0
        files = discover(folder, database)
        with tempfile.TemporaryDirectory(prefix='dnd-prepared-') as prepared:
            for path in files:
                try:
                    documents = read(path, folder)
                except (OSError, ValueError):
                    skipped += 1
                    continue
                for document in documents:
                    text = re.sub(r'\s+', ' ', document.text).strip()
                    if not text:
                        continue
                    name = f'{len(provenance):06d}.txt'
                    provenance[name] = {'path': document.path, 'page': document.page,
                                        'record': document.record}
                    (Path(prepared) / name).write_text(text)
            index = LibreIndex(prepared, database=database, backend=self.backend,
                               embedding_model=self.embedding, chunk_size=2200, chunk_overlap=400)
            index.index()
        (database / 'embedding.json').write_text(json.dumps({
            'model': self.embedding, 'provenance': provenance}))
        report = index.report.model_dump()
        report['files'] = len(files)
        report['skipped'] += skipped
        return report

    def search(self, query, edition='2014', scope='rules', limit=4):
        if edition not in {'2014', '2024'}:
            raise ValueError('Edition must be 2014 or 2024')
        if scope not in {'rules', 'campaign'}:
            raise ValueError('Scope must be rules or campaign')
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError('Query must contain 1–4000 characters')
        if type(limit) is not int or not 1 <= limit <= 12:
            raise ValueError('Limit must be 1–12')
        collection = edition if scope == 'rules' else 'campaign'
        _, database = self._paths(collection)
        metadata = database / 'embedding.json'
        if not metadata.exists():
            return {'sources': [], 'warning': f'{collection} is not indexed. Run dnd index.'}
        settings = json.loads(metadata.read_text())
        if settings['model'] != self.embedding:
            raise RuntimeError('Embedding model changed. Re-index this collection.')
        vector = self.backend.embed([query], self.embedding)[0]
        table = lancedb.connect(database).open_table('chunks')
        rows = (table.search(vector)
                .distance_type('cosine').limit(limit).to_list())
        # Rules/stat blocks can cross PDF page boundaries. Include the pages
        # around the best hit so a trailing trait is not mistaken for the next monster.
        if rows:
            best = settings.get('provenance', {}).get(rows[0]['path'], {})
            if best.get('page') is not None:
                adjacent = [name for name, origin in settings.get('provenance', {}).items()
                            if origin['path'] == best['path'] and origin.get('page') is not None
                            and abs(origin['page'] - best['page']) == 1]
                seen = {row['id'] for row in rows}
                for name in adjacent:
                    for row in table.search().where(f"path = '{name}'").limit(3).to_list():
                        if row['id'] not in seen:
                            rows.append(row)
                            seen.add(row['id'])
        sources = []
        for row in rows:
            score = max(0.0, min(1.0, 1.0 - float(row.get('_distance', 1.0))))
            origin = settings.get('provenance', {}).get(row['path'], {})
            sources.append({'collection': collection, 'path': origin.get('path', row['path']),
                            'page': origin.get('page', None if row['page'] < 0 else row['page']),
                            'excerpt': re.sub(r'\s+', ' ', row['text']).strip(), 'score': score})
        # A source can span pages: keep a split stat block under one citation ID.
        grouped = []
        for source in sorted(sources, key=lambda s: (s['path'], s['page'] or 0)):
            if source['page'] is None:
                grouped.append(source)
                continue
            group = next((g for g in grouped if g['path'] == source['path']
                          and 'pages' in g and source['page'] <= max(g['pages']) + 1), None)
            if group is None:
                group = dict(source, pages=[source['page']], excerpt='')
                grouped.append(group)
            if source['page'] not in group['pages']:
                group['pages'].append(source['page'])
            group['score'] = max(group['score'], source['score'])
            group['excerpt'] += f"[PDF page {source['page']}] {source['excerpt']}\n"
        sources = sorted(grouped, key=lambda s: s['score'], reverse=True)
        return {'sources': sources, 'warning': (
            'Weak retrieval match; this is not a probability of correctness.'
            if not sources or sources[0]['score'] < 0.45 else None)}

    def close(self):
        self.backend.client.close()

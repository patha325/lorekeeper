"""Local CLI, with explicit setup, indexing, and exports."""
import argparse
import json
import sys
from pathlib import Path

import httpx

from .assistant import Assistant
from .knowledge import Knowledge
from .tools import save_draft


def display(result):
    print(result['answer'])
    for warning in result['warnings']:
        print(f'\nNote: {warning}')
    for source in result['sources']:
        page = (f", pages {', '.join(map(str, source['pages']))}" if source.get('pages')
                else f", page {source['page']}" if source['page'] else '')
        print(f"\n[{source['id']}] {source['collection']}/{source['path']}{page}")
        print(source['excerpt'])


def main():
    parser = argparse.ArgumentParser(description='Local D&D assistant using Ollama and LibreIndex')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--edition', choices=['2014', '2024'], default='2014')
    parser.add_argument('--model', default='qwen3:8b')
    parser.add_argument('--embedding', default='embeddinggemma')
    parser.add_argument('--extensions', type=Path, help='Trusted local extension registry JSON')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('fetch-srd')
    index = sub.add_parser('index')
    index.add_argument('--collection', choices=['2014', '2024', 'campaign'])
    ask = sub.add_parser('ask')
    ask.add_argument('question')
    ask.add_argument('--json', action='store_true')
    sub.add_parser('chat')
    handoff = sub.add_parser('handoff')
    handoff.add_argument('builder', choices=['dndbeyond', 'brainstorm'])
    handoff.add_argument('draft', type=Path)
    args = parser.parse_args()

    def approve(name, arguments):
        print(f'External tool {name}: {json.dumps(arguments, ensure_ascii=False)}')
        return sys.stdin.isatty() and input('Allow this call? [y/N] ').strip().lower() == 'y'

    assistant = None
    try:
        if args.command == 'fetch-srd':
            filename = 'SRD_CC_v5.1.pdf' if args.edition == '2014' else 'SRD_CC_v5.2.1.pdf'
            version = '5.1' if args.edition == '2014' else '5.2'
            url = f'https://media.dndbeyond.com/compendium-images/srd/{version}/{filename}'
            target = args.root / 'documents' / args.edition / filename
            if target.exists():
                print(f'Already downloaded: {target}')
                return
            with httpx.Client(timeout=120, trust_env=False, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
            if not response.content.startswith(b'%PDF'):
                raise ValueError('The official download did not return a PDF')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            print(f'Downloaded official SRD: {target}')
            return
        if args.command == 'doctor':
            with httpx.Client(trust_env=False) as client:
                response = client.get('http://127.0.0.1:11434/api/tags')
                response.raise_for_status()
                names = [x['name'] for x in response.json()['models']]
            print('Ollama reachable. Installed models:', ', '.join(names))
            print('Selected chat:', args.model, '| embeddings:', args.embedding)
            for collection in [args.edition, 'campaign']:
                print(collection, 'indexed:', (args.root / '.state' / collection / 'embedding.json').exists())
            return
        if args.command == 'index':
            knowledge = Knowledge(args.root, embedding=args.embedding)
            try:
                print(json.dumps(knowledge.index(args.collection or args.edition), indent=2))
            finally:
                knowledge.close()
            return
        assistant = Assistant(args.root, args.edition, args.model, args.embedding,
                              extensions=args.extensions, approve=approve)
        if args.command == 'handoff':
            print(json.dumps(assistant.builder_handoff(args.builder, json.loads(args.draft.read_text())), indent=2))
        elif args.command == 'ask':
            result = assistant.ask(args.question)
            print(json.dumps(result, indent=2) if args.json else '')
            if not args.json:
                display(result)
        else:
            print(f'D&D companion — {args.edition}. /quit to exit; /save exports last character draft.')
            last = None
            while True:
                question = input('\nYou: ').strip()
                if question == '/quit':
                    break
                if question == '/save':
                    drafts = [x['result'] for x in (last or {}).get('tools', [])
                              if x['name'] == 'character_draft' and 'error' not in x['result']]
                    print(save_draft(args.root, dict(drafts[-1], edition=args.edition)) if drafts else 'No draft in the last answer.')
                elif question:
                    last = assistant.ask(question)
                    display(last)
    except (httpx.HTTPError, RuntimeError, ValueError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')
    except (EOFError, KeyboardInterrupt):
        print('\nGoodbye.')
    finally:
        if assistant:
            assistant.close()


if __name__ == '__main__':
    main()

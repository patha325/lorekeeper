#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -e .
fi
if ! command -v ollama >/dev/null; then
  print 'Install Ollama from https://ollama.com, start it, then open this file again.'
  read '?Press Return to close.'
  exit 1
fi
.venv/bin/lorekeeper doctor
.venv/bin/lorekeeper fetch-srd
if [[ ! -f .state/2014/embedding.json ]]; then
  .venv/bin/lorekeeper index
fi
if [[ ! -f .state/campaign/embedding.json ]]; then
  mkdir -p documents/campaign
  if [[ -z "$(ls -A documents/campaign)" ]]; then
    cp examples/campaign-template.md documents/campaign/notes.md
  fi
  .venv/bin/lorekeeper index --collection campaign
fi
.venv/bin/lorekeeper chat

# Lorekeeper

A working local command-line RAG assistant built with your **LibreIndex** library and Ollama. **2014 / SRD 5.1 is the default.** The 2024 SRD is available as a separate collection. Rules answers carry source excerpts and PDF page references; worldbuilding suggestions are distinguished from official rules.

## Start

On this Mac you can also double-click `Start.command`. It creates a local Python environment on first launch. Ollama must be running with `qwen3:8b` and `embeddinggemma` installed.

Open a terminal in this folder, with Python 3.11+, Git, and Ollama installed:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ollama pull qwen3:8b
ollama pull embeddinggemma
lorekeeper doctor
lorekeeper fetch-srd
lorekeeper index
mkdir -p documents/campaign
cp examples/campaign-template.md documents/campaign/notes.md
lorekeeper index --collection campaign
lorekeeper chat
```

The model downloads require internet once. Afterwards, indexing, retrieval, dice, and generation run locally. The local download bundle includes both official SRD PDFs. GitHub users fetch the selected official PDF once with `lorekeeper fetch-srd`. First indexing can take several minutes. Existing prebuilt `.state` indexes, when present in this working folder, use `embeddinggemma`.

Examples:

```sh
lorekeeper ask 'What are the 2014 zombie statistics and how does Undead Fortitude work?'
lorekeeper ask 'Help me create a level 1 human cleric, using the standard array.'
lorekeeper ask 'Suggest three mysteries for my cemetery opening. Label homebrew.'
lorekeeper --edition 2024 fetch-srd
lorekeeper --edition 2024 index
lorekeeper --edition 2024 ask 'How does the Prone condition work?'
```

Run from this folder or set `lorekeeper --root /absolute/path/to/lorekeeper …`.
Use `/quit` to exit chat. `/save` exports a character draft made in the last answer to `.state/characters/`. Drafts explicitly list the fields still needing verification. No claim is made that a draft is a complete or legal character sheet.

## Your character builders

Ask: “Create a draft of a level 1 human fighter, then use builder_handoff with brainstorm.” The local model can call the tools itself.

- **Brainstorm Club:** `builder_handoff` generates a pre-filled share link using the site's existing compact/base64 protocol. It includes name, edition, race, class, level, background, and ability scores. Open the link and complete the remaining steps. Verify base scores versus racial/origin bonuses, HP, AC, equipment, proficiencies, features, and spells. The adapter currently supports SRD class and race identifiers; subraces and specialized options require editing in the builder. Link generation does not create or save a remote character. Protocol verified against source commit `dabb1f1df895aee06687f7f8e55979dd7a97c335`; deployed versions may differ.
- **D&D Beyond:** provides the character-builder URL and a checklist of choices to enter. Account login and source availability remain in your browser. This version does not automatically fill or save a Beyond character.

For an exported local draft:

```sh
lorekeeper handoff brainstorm .state/characters/YOUR-DRAFT-ID.json
```

Builder use requires internet. Browser account access is not part of the local RAG. There is no assumed private D&D Beyond API.

## Add material

Put readable PDF, Markdown, text, CSV, or JSON files into:

- `documents/2014/`: 2014 rules and additional material you can use locally.
- `documents/2024/`: revised rules, isolated from 2014 retrieval.
- `documents/campaign/`: your world, NPCs, session notes, and character exports.

Then explicitly re-run the relevant index command. Scanned PDFs need OCR first. Review the index report's `skipped` count. The included SRDs cover a substantial rules subset, not every published book, setting, feat, subclass, or monster. No paid-book scraping is included.

Re-indexing replaces that collection's local index. Keep only its generated index files in `.state/<collection>/`. Changing the embedding model requires re-indexing. Changing the chat model does not.

## Tool support and extensions

Built-in model-callable tools: `search_sources`, `roll_dice`, `ability_scores`, `character_draft`, and `builder_handoff`. Dice rolls use local randomness. Point buy is calculated deterministically. The agent is limited to 9 model turns and 12 tool calls per question.

You can connect another installed Python tool with an explicitly configured registry file:

```json
[
  {
    "callable": "my_character_tools:create_character",
    "schema": {
      "type": "function",
      "function": {
        "name": "create_character",
        "description": "Create a character using my configured character service",
        "parameters": {
          "type": "object",
          "properties": {"name": {"type": "string"}},
          "required": ["name"],
          "additionalProperties": false
        }
      }
    }
  }
]
```

Run `lorekeeper --extensions tools.json chat`. Only load modules you trust: importing a Python module executes its code. External calls require per-call terminal approval, and are denied in non-interactive use. The registry is a Python adapter, not an MCP client. A model cannot install extensions or run arbitrary commands.

LibreIndex handles document ingestion/chunking and persistent LanceDB storage. This app adds version isolation, a batched Ollama embedding backend, retrieval tools, citations, and bounded tool execution. Ollaborate is not needed for this first single-assistant implementation; the typed local functions can also be wrapped as Ollaborate tools later.

## Limitations

RAG improves grounding but cannot guarantee correctness. Source scores are cosine similarities, not calibrated probabilities. The app warns about missing citations, unknown citation IDs, weak matches, and absent indexes; it does not prove that each cited passage supports every claim. Review mechanics and builds before play. Conversation stays in memory for one session; start a new chat when context grows large. Campaign search is available as a separate tool, so user notes are never treated as official rules.

## Verification

```sh
pytest -q
python -m build
```

Tests cover edition isolation using a real temporary LanceDB, embedding-model mismatch, point buy, random dice bounds, draft arithmetic, share-link encoding, external-tool approval, and the Ollama tool-result loop with mocked HTTP.

See `VALIDATION.md` for checks performed on this machine and `ATTRIBUTION.md` for SRD attribution.

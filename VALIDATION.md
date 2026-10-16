# Validation — 16 October 2026

- Python 3.12: 10 tests passed.
- Source distribution and wheel built successfully.
- Local Ollama 0.40.4, `qwen3:8b` generation and `embeddinggemma` embeddings exercised over HTTP.
- Official 2014 SRD: 403 pages processed into 904 normalized passages, with no skipped pages. Original PDF page references are preserved.
- A live rules question returned the ordinary 2014 Zombie's 22 HP, with a citation to the grouped pages 356–358. Separate checks returned the Undead Fortitude saving-throw rule correctly. See `examples/live-rules-answer.json`.
- A real model-requested `roll_dice` call rolled 1d20+3: die 6, modifier 3, total 9. The model reported 9. This example is a recorded random result, not a deterministic expected roll.
- Brainstorm Club's deployed site accepted the generated 2014 fighter draft and displayed its name, class, background, and ability scores. It remains a partial draft, not a complete sheet.
- The 2024 PDF is available locally; the default 2014 collection was indexed and live-tested. Index 2024 explicitly when needed.
- GitHub CI is configured for Python 3.11–3.13. Its result is reported separately after upload.

The live check exposed a page-boundary error: the model initially confused Zombie with Ogre Zombie. PDF whitespace normalization, neighboring-page retrieval, and grouped citations were added, with regression coverage. These improve evidence quality but do not guarantee every generated answer is correct.

Ollama briefly stopped during verification. After the user restarted its app, live embedding, generation, and tool tests succeeded. Models are unloaded between embedding retrieval and generation to reduce concurrent memory use. No system-wide Ollama settings were changed.

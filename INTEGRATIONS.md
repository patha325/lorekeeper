# Character-builder integration

## Brainstorm Club

Repository: https://github.com/Brainstorm-Club/dnd-character-builder
Inspected commit: `dabb1f1df895aee06687f7f8e55979dd7a97c335`.

The adapter uses the existing share-link protocol in `src/utils/shareCharacter.ts`, with the import behavior in `src/views/ShareView.vue`. It independently encodes compact keys as UTF-8 URL-safe base64, without copying builder code or game data. The deployed site accepted a sample 2014 human fighter draft in a live browser check. See `examples/builder-draft.png`.

The link populates a **partial** character. In the verified example, the review page still showed HP 0 and default hit-die information because class progression, equipment, and other wizard steps had not been completed. Revisit the creation steps to calculate those fields before playing. The local assistant says this explicitly and does not treat a successful import as a finished character.

Ability scores in the link populate the builder's `abilityScores` fields. Verify whether your draft uses base or final scores before applying racial/origin bonuses. Background strings use slug IDs and need review, especially for material outside the SRD. No character is saved by the adapter.

## D&D Beyond

Handoff URL: https://www.dndbeyond.com/characters/builder

This implementation prepares choices and opens a path for manual entry. It does not access account credentials, automate private endpoints, or claim remote character creation. For a 2014 campaign, choose the matching legacy rules/content within the builder. You can add an exported sheet to `documents/campaign/`, then re-index it for local reference.

## Future service adapters

The explicit Python extension registry lets an installed tool be connected without changing the assistant loop. Model tool calls are bounded, arguments are checked, and external calls require approval. A specific supported service API or browser automation implementation would still be needed for account-side character creation.

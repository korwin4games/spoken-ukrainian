# Ukrainian translation store (planned)

This directory is reserved for **reviewed, versioned Ukrainian translation records** keyed by **canonical Spoken IDs**, independently of the final Lua Community Pack format.

No actual translation corpus is checked in yet.

- `places/`, `readables/`, `bosses/`, `quests/` and `ui/`: our own or manually curated translations.
- `imported/<provider>/`: reviewed source snapshots when `save_translations: true` and source identity, text provenance and legal permissions are verified.
- Third-party imports and our editorial overrides are **never silently overwritten** by upstream updates.
- Drafts and raw download/extraction files remain in ignored `build/` until separately approved for inclusion.
- Runtime packaging needs its own verified module compatibility, rights and content approval.

The directory layout, YAML writer and source refresh action are documented as **future work**, not implemented by the current configuration parser. See [storage and update policy](../../docs/TRANSLATION_STORAGE_POLICY.md).

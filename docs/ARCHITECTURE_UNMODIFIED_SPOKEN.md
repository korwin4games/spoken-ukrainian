# Architecture decision: keep the original Spoken Player unmodified

**Status: accepted project design constraint (2026-11-16).** Applies to Stage 2B review, Stage 3 identity mapping, all future Ukrainian Community Packs, helper addons, audio work and releases. This is a project choice, not proof that every target feature is supported by today's Spoken API.

## Decision

**Spoken Ukrainian is a consumer of released, unmodified Spoken Player and its public Community Pack contracts.** Never fork, vendor, patch, overwrite, repackage, replace or monkey-patch Spoken Player or its modules to make Ukrainian content appear supported.

- Use only documented or verified public Community Pack metadata, registries, interfaces and load-on-demand integration points.
- Treat `GetLocale()` as the real WoW client locale (initially `enUS`) and `ukUA` as an independent **content** language. Never spoof the client locale, disguise Ukrainian as `enUS`, modify global functions, override private Spoken implementation, or install silently rewritten Lua.
- Do not fabricate sound filenames, durations, fake MP3s or silence to bypass audio availability checks.
- Do not modify ClassicUA either; players may install it independently to translate **native game UI**, not as a way to claim Spoken captions or Compendium are translated.
- Never change the canonical Spoken ID namespace merely because text or a voice pack is Ukrainian.

## Compatibility-first delivery strategy

| Priority | Integration | Policy |
| --- | --- | --- |
| A — default | Pure Ukrainian **Community Packs** through existing Spoken public contracts | Preferred. Release only features demonstrated safe on the pinned player; preserve fallback and module semantics. |
| B — optional | **ClassicUA** installed alongside unchanged Spoken | ClassicUA may translate native quest/gossip/readable windows; this does **not** guarantee Ukrainian Spoken narrator captions, audio-free Compendium text or in-app texts. Test each surface independently with ClassicUA both on and off. |
| C — separate decision, later | Small **standalone Ukrainian helper addon with its own UI** | Consider only if public contracts cannot supply an essential text display. It must be independently installable/removable; use public WoW events/APIs and avoid any monkey-patching, private globals, player overwrite, or implicit changes in Spoken. Do **not** assume it can alter existing Spoken windows. Evaluate technical/UX costs and request separate authorization before implementation. |
| Upstream evolution | Maintainers of **Spoken** independently add public features to a new official version | We may document issues or propose backward-compatible API designs, without creating/modifying a player fork. Adoption of a newer released Spoken revision is a separate explicit, pinned and tested compatibility task. Never depend on an unmerged upstream idea. |

## Verified limitations of the pinned baseline (not acceptance of a workaround)

Stage 2B characterization (locally reported; not yet independently reviewed in the remote repository) identifies the following for Spoken `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`:

- **Places:** independent `ukUA` text-only lore has been demonstrated for the diagnostic content.
- **Readables:** a page with text but no `file` may be counted as audio by `HasAudio`, while `ClipFor`/`PlayFrom` may error; `enUS` Compendium selects English page text. **Do not package audio-free Readables entries as if they were fully supported.**
- **Quests/Gossip:** available voice-clip metadata does not by itself unlock Ukrainian captions for an English client; text-only queue creation is not established.
- **Bosses:** English text-only fallback does not establish independent Ukrainian community-pack story display on `enUS`.

These are constraints to reproduce and keep covered by tests. Offline characterization is **not** a substitute for actual Forever acceptance. Verify the precise findings in tracked Stage 2B artifacts before treating them as a completed review.

## How to handle a blocked module

1. Report the supported surface and behavior honestly; distinguish native Blizzard text, ClassicUA-translated native text, Spoken captions, Compendium text and audio.
2. Mark the unsupported feature **blocked**. Continue independent offline mapping and provenance work where safe. Do not invent dummy clips, silent takes, altered client locales or unsupported load behavior.
3. When an official, **unmodified** Spoken release provides the needed public contract, independently inspect and pin that release, run Stage 2B regression tests and conduct real client tests before enabling the module.
4. If upstream support does not arrive and independent display is essential, evaluate the **optional separate-UI helper** as a separately approved project. It must not be marketed as native Spoken integration.
5. Keep target feature descriptions, README compatibility claims and release candidates aligned with actual tested capabilities.

## Impact on Stage 2B and Stage 3

- **Stage 2B:** deliver executable baseline characterizations and documented limitations; upstream API suggestions are allowed as *non-binding design proposals*, not code changes or an implementation requirement. Real game tests remain pending until executed and recorded.
- **Stage 3:** implement deterministic, update-ready ClassicUA-to-canonical-Spoken crosswalks **independent of runtime readiness**. A successful mapping is not permission to emit a currently unsafe pack.
- **Later pack milestones:** Places original or separately cleared lore can ship where independently tested; Quests/Gossip with real approved audio can be explored within actual contract constraints, with truthful subtitle/fallback documentation; audio-free Readables and blocked Bosses stories wait for real support or a separately approved independent UI.

## Release and change controls

`AGENTS.md` and `.agents/skills/spoken-runtime-contracts/SKILL.md` must enforce this decision. Any exception that would modify Spoken Player is **out of scope under the current architecture** and needs a new explicit user decision; no agent should reinterpret a research task as authorization to patch it. Do not create player forks, submit upstream code PRs, bump `VERSION`, publish community packs, or perform paid TTS operations in this policy-documentation change.

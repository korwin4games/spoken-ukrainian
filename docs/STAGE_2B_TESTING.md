# Stage 2B testing and manual acceptance

Date: 2026-11-16. Branch: `feat/spoken-runtime-compatibility`.
Automated characterization passes. **Stage 2B manual Forever acceptance is pending.**
The Stage 1 diagnostic's earlier user-reported game acceptance remains recorded in
`STAGE_1_TESTING.md`; it is not a new game result for Readables, Quests, Gossip or Bosses.

## Automated commands and evidence

Run from the project root, with Python 3, Git, system `liblua5.4` and a local
Spoken checkout containing the exact locked revision. The normal location is
`../spoken-wow`; set `SPOKEN_SOURCE=/absolute/path/to/spoken-wow` otherwise.
No dependency download or network request is part of these commands.

```sh
python3 tools/version.py check
python3 tools/build.py
python3 -m unittest discover -s tests -v
# Optional focused repeat:
python3 -m unittest discover -s tests -p test_stage2b.py -v
```

Final full result: **88 tests passed**, no skips or expected-failure markers:
36 Stage 2A adapter/parser/source tests, 16 unchanged Stage 1 tests,
15 new Stage 2B tests and 21 version tests. `version.py check` returned `0.0.1`.
The diagnostic build remains exactly **1651 bytes**, with SHA-256:

```text
5a2519858229c9aa004dbef075d1c8c51561e33f09828112504e0558005c8a8e
```

The Stage 2B tests below live in `test_stage2b.RuntimeCompatibilityTests`.
Each Python method invokes the indicated Lua entry point with a fresh VM.

| Python method (prefix `test_`) | Lua evidence | Result / meaningful assertion |
| --- | --- | --- |
| `readables_text_without_file_is_available_but_unsafe` | `readables_text_without_file` | PASS: text accessible, false audio-positive, both `ClipFor` and `PlayFrom` error; valid EN fallback cannot bypass; queue not called |
| `readables_compendium_language_is_client_not_voice` | `readables_compendium` | PASS: English UI words/title under UK voice; English pack override works; no independent text getter/setter |
| `readables_audio_metadata_and_nonclient_captions` | `readables_audio` | PASS: valid path/key/length contract, UK text/timings and playlist submission; absent UK text falls back to English caption without UK timings |
| `readables_missing_disabled_fallback_and_legacy` | `readables_fallback` | PASS: no registered UK pack → missing; legacy EN fallback, Stay Silent, Auto/enUS and unsupported format rejection |
| `readables_matching_and_player_templates` | `readables_matching` | PASS: actual checksum/index page recognition; name/class/race/gender rendering; mail excluded |
| `quests_registration_load_order_and_disabled` | `quests_registration` | PASS: enumeration before registration required, ukUA voice vs enUS matching; disabled pack not enumerated/registered, stale choice retained |
| `quests_audio_required_queue_and_caption_locale_gate` | `quests_audio` | PASS: text-only never queues; valid metadata queues, actual narrator text falls back to captured window; all three quest events gated |
| `quests_missing_fallback_and_gender` | `quests_fallback` | PASS: English text/timings on fallback, Stay Silent, female stem selection, unmatched wording and disabled pack |
| `quests_compendium_text_remains_in_client_language` | `quests_compendium` | PASS: real `PartText` returns English without audio and with UK audio; EN take words override on fallback |
| `gossip_matched_unmatched_and_player_templates` | `gossip_matching` | PASS: player token matching with two names, unrelated text refused; single foreign moment heuristic vs two foreign moments |
| `gossip_audio_required_and_caption_locale_gate` | `gossip_audio` | PASS: missing audio refused, UK transcript gated, actual narrator captured text, EN fallback, Stay Silent and disabled pack |
| `places_text_and_voice_with_audio_metadata` | `places_audio` | PASS: lore without audio; valid path and narrator transcript; selected UK lore under EN fallback; Stay Silent and removed audio preserve lore |
| `bosses_text_only_pack_is_safe_but_client_gated` | `bosses_text` | PASS: UK pack words accessible, no audio flag, English story/text-only clip; absent pack preserves core |
| `bosses_audio_caption_mismatch_fallback_and_missing_core` | `bosses_audio` | PASS: UK path with EN transcript/no timings; EN fallback vs English text-only under Stay Silent; no core → no story clip despite recording |
| `core_text_only_admission_is_not_module_support` | `core_text_only` | PASS: real queue admission bypasses audio channel for text-only, still honors source disablement |

“PASS” on a capability gap means its current absence/error was correctly reproduced.
No-filename errors are caught and inspected explicitly, not hidden behind skipped
tests or normalized away. The Stage 1 suite additionally verifies metadata/native
name menus, text selection/reload, disabled/removed packs, English behavior,
font rejection, restricted diagnostic globals and deterministic packaging.

## Harness and limitations

`tests/lua_runtime.py` is reused without alteration. `test_stage2b.py` reads immutable
blobs using `git show <locked-commit>:<path>`, checks SHA-256 against the existing
lock plus `tests/stage2b_sources.json`, and passes complete chunks to Lua. The
additional manifest pins only source-file hashes, not copied source or translations.
Existing source-lock entries are unchanged. Snapshot checks compare tracked and
nonignored untracked upstream file contents before/after both contract suites.
They do not monitor ignored caches, Git metadata or access times.

`tests/runtime_contract.lua` loads real language/API code, Readables checksum,
Core/Language/Reader/Audio/Playlist/UI, Quests Enums/Utils/Language/FuzzySearch/
DataModules/Player/QuestsTab, Bosses Core/Audio/UI and the generic queue admission
function. Places reuses Stage 1's real-module Session. Original Lua bodies are not
rewritten or replaced. An appended `return` exposes lexical UI helpers (`Words`,
`PartText`, `Story`) and queue `WhyRefused` in their original closure. This changes
only what the test chunk returns, not its decisions or a player's installation.

Only relevant TOC-relative load order is executed. Synthetic English/Ukrainian
records replace external corpora; no ClassicUA source or real translated story is
loaded into these tests. No new crosswalk is implied by synthetic page/moment IDs.
The harness supplies saved profiles, enabled/disabled metadata, player APIs,
nonsecret values, frame event registration and inert decorative Compendium data.
Quests enumeration uses real metadata readers before explicit simulated pack load;
Readables/Bosses disabled packs are modeled by absence from the registry after load,
not a claim of hot-unloading an already loaded addon.

Audio-present fixtures are **symbolic valid metadata**, with nonempty relative
stems, positive durations and optional word times. They represent what a pack with
a genuine recording supplies; they are never written to an addon or checked for
playability. Queue boundaries only record submissions. All direct sound/network
calls are forbidden. Genuine audio, its measured duration, listening quality and
client rejection cannot be certified by these tests. No silent or fake MP3 exists.

The VM is Lua 5.4, not the game's Lua 5.1/client runtime. `load(..., environment)`
provides the environment and a test-only `setfenv` stub validates it; a private
`table.getn` shim preserves the old API without changing the host library. Each
test verifies the host global table has no unexpected additions/replacements.
This is isolation evidence, not a sandbox for arbitrary untrusted Lua: only pinned
player code is executed. Stage 2A still parses ClassicUA without executing it.

Frame events are registered but not dispatched through a full WoW lifecycle.
Widget layout, fonts, settings persistence in the client, cut/mute behavior,
combat, automatic encounter narration and ClassicUA hook timing remain manual.
No test asserts that a language-name width fixture proves real Ukrainian glyphs.
Static-only native-frame/label conclusions are marked S in the compatibility matrix.

## Manual Forever checklist and record

All rows below are **PENDING** for Stage 2B. Use an isolated test profile/addon
directory, not a normal playing session. Record original settings/enable states
first and restore them afterward. Nothing here was installed by the agent.

| ID | Procedure and expected evidence |
| --- | --- |
| M-0 environment | Record `/dump GetBuildInfo()`, `/dump GetLocale()` (must be enUS), loaded Spoken and all five module TOC versions, actual source/release relationship, ClassicUA version when enabled, and enabled pack versions. Record date, character sex/class/race, text/voice/fallback choices and `scriptErrors` value. Enable `/console scriptErrors 1` for observation. |
| M-R safe baseline | With ClassicUA and audio packs disabled, open a known identified book and Compendium entry. Record native page, narrator, Compendium title/body separately. Existing English text can display without audio; no playback should be offered for an absent recording. Confirm English client matching and mail exclusion. An unmodified player has no independent UK Readables text setting. Use the isolated reproduction below for the no-file defect; do not install an unsafe pack in the live profile. |
| M-Q quests | In the isolated setup, capture offer/progress/hand-in for a known quest, including player name/class/race/gender variants. With no audio record no normal narrator clip. With an already authorized genuine UK clip, choose UK voice; compare captured native words vs narrator vs Compendium. Expect the client-language gate, not independent UK text. Disable the UK pack and reload; verify English audio fallback and then Stay Silent. Unmatched wording must not select an arbitrary moment. |
| M-G Gossip | Use a verified canonical greeting/page and a deliberately unmatched dialog. Observe matching before/after a player-dependent variant, missing audio, disabled UK pack, EN fallback and Stay Silent. Never substitute a ClassicUA hash or a menu-option translation for a Spoken page ID. Record the single-foreign-moment heuristic separately from an exact match. |
| M-P Places | Repeat Stage 1 Ukrainian diagnostic text selection/reload, glyph inspection, English restoration and disabled/removed pack behavior. Change Voice Language independently. No recording means no narrator, while lore remains visible. With genuine authorized voice available, compare selected text vs voice and verify mismatched-language timings are not applied. Check map labels independently. |
| M-B Bosses | Open a known boss with core story in Compendium and its encounter/map story surface, with no voice pack: expect an English text-only story. Under a declared UK story pack, observe locale-gated English story. With genuine UK audio, compare actual language heard and English transcript; remove UK audio, test EN fallback and Stay Silent. Record known boss lacking core story separately; it should not acquire a story clip solely from pack audio. |
| M-A real audio | Only if lawful genuine recordings already exist or are separately supplied: verify referenced files and measured durations, then listen in the isolated profile. Check Play/Stop, page continuation, queue deduplication and missing-file recovery. Do not generate audio or use fabricated paths to claim this check passed. Until clips are available, record unavailable/pending. |
| M-C coexistence | Run M-R/Q/G/P/B once with ClassicUA disabled, then enabled, keeping client locale enUS and recording its exact loaded version. Compare native quest/gossip/ItemTextFrame changes, Spoken captured captions, recognition, Compendium and lore separately. Note hook/event order, missing audio, Lua errors and glyphs. Do not infer the pack owns text merely because ClassicUA changed a frame. |
| M-restore | Restore all language/fallback choices, pack enable states, discovery/voiced filters, unlock settings and `scriptErrors`; reload and verify English behavior and ordinary play. Remove only the isolated test fixture, with game closed; preserve other addons and SavedVariables backups. |

### One isolated Readables no-file reproduction

This is a proposed reversible experiment for a human tester, **not executed here**.
The offline failure is already conclusive at Lua-function level; this experiment
checks the actual client UI/error path. Do not deploy it into the user's current
AddOns/profile or distribute it as a supported pack.

1. Close the game; make a separate test installation/profile and back up its
   SavedVariables. Copy only the reviewed unmodified player/modules into that
   isolated environment. Record versions and enUS; disable ClassicUA initially.
2. Select an existing canonical readable page verified in that client's corpus.
   Do not use this suite's synthetic number as if it were an actual game page.
3. Prepare a disposable diagnostic addon depending on `Spoken, Spoken_Readables`,
   declaring `X-SpokenReadables-Language: ukUA`, the language name/native metadata,
   and registering **only in this isolated experiment** a format-1 `pages[verifiedID]`
   entry `{ text = "Синтетична діагностична сторінка." }`. No `file`, duration,
   dummy MP3, copied translation or player changes. Review its two small files
   before installing. This intentionally exercises the known unsafe baseline.
4. Start the isolated client, enable errors, select UK voice and Stay Silent.
   Inspect `HasAudio(verifiedID)` and independently `PackPageText(verifiedID,"ukUA")`.
   Expect true and synthetic text, respectively. Record the Compendium page's
   still-English title/body and whether it exposes an inaccurate Play control.
5. Trigger one `PlayFrom(verifiedID,true,true)` request in this environment (or its
   visible Play control). Expect a nil-`file` concatenation error before narration.
   Capture the stack trace and exact call surface, then stop; no repeated probing
   or installation into the normal game is needed.
6. Close the isolated client, remove only that disposable fixture and restore its
   SavedVariables/enable states. Reopen and verify ordinary English and no new
   error. Repeat safe native-surface observations with ClassicUA enabled, recording
   its version, without reinstalling the unsafe fixture into the live environment.

For a future upstream fix, rerun the same experiment against its reviewed revision:
expect `HasAudio=false`, no exception and the agreed text-selection/fallback
contract. Record that separately from the unchanged baseline characterization.

## Review and release boundaries

Review the changed files under the repo's `code-reviewer` workflow:
provenance, unmodified pins, synthetic fixtures, no fake audio, truthful enUS,
absent production/TTS operations and retained Stage 1/2A behavior. The local
implementation report recorded no actionable code defect. Residual limits remain
the pending manual Forever checks, symbolic audio and bounded upstream issue
search; a passing characterization test does not prove a blocked capability works.

**Remote verification (2026-11-16):** the Stage 2B implementation was committed and
pushed to `feat/spoken-runtime-compatibility` at commit
[`261e8bee544eb5ec90f167850009b82eb20ac9b0`](https://github.com/korwin4games/spoken-ukrainian/commit/261e8bee544eb5ec90f167850009b82eb20ac9b0).
[GitHub Actions run 43880649210](https://github.com/korwin4games/spoken-ukrainian/actions/runs/43880649210)
**passed for that commit**. Subsequent documentation corrections and branch
synchronization require their own CI status check on the final PR head; this earlier
run does not establish the result of later commits.

No translated packs, source corpora, source updater or mappings were created.
No project version bump, upstream player modification, tag or content release
was performed. Stage 3 remains a separate authorized task with its own
canonical-identity and review gates. Check GitHub for the current pull-request
and merge state rather than relying on this time-stamped test record.

# Spoken Ukrainian licensing and attribution

Stage 0 evidence register, checked 2026-11-16. These findings distinguish documented grants from permission still needed. No ClassicUA translations have been imported into this project or distributed in these deliverables.

## Sources and grants

| Source | Inspected revision / evidence | Finding and action |
| --- | --- | --- |
| Spoken code | `3c896874e27ec9e07d51a3578c0b9fa8545c9ac7`; [LICENSE](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/LICENSE) | MIT covers code written by Spoken. Preserve copyright and permission notice in copies or substantial portions. Referencing an external player does not require bundling it. Include notices when reusing helpers. |
| Spoken third-party material | Same revision; [THIRD_PARTY.md](https://github.com/rusty-key/spoken-wow/blob/3c896874e27ec9e07d51a3578c0b9fa8545c9ac7/THIRD_PARTY.md) | The MIT grant expressly excludes third-party libraries and game text, lore and artwork. Do not assign one blanket MIT license to Ukrainian content or future audio. |
| ClassicUA | `1770d208ad853d23d61105cf510d53804770d916`; [repository](https://github.com/greenya/ClassicUA/tree/1770d208ad853d23d61105cf510d53804770d916), README, TOC and inspected source headers | No LICENSE/COPYING/copyright/notice filename was found in the inspected recursive tree. README credits contributors and links terminology/Crowdin; inspected entry headers identify generated files without a redistribution grant. Permission for translation redistribution, adaptation and TTS remains unestablished. Public source visibility is not permission. |
| ClassicUA permission request | [issue 100](https://github.com/greenya/ClassicUA/issues/100) and its comments, read 2026-11-16 | Open, zero comments at inspection. The request mentions text reuse and AI narration; the request itself grants neither. Recheck before any content release. |
| Spoken coordination | [issue 1123](https://github.com/rusty-key/spoken-wow/issues/1123#issuecomment-6906425492) and subsequent question | Collaborator directs the project to Community Packs. This establishes the intended integration route, not rights to ClassicUA, game or wiki material. No maintainer answer to the subsequent Readables text-only question was present at inspection. |
| Spoken French | [project page](https://www.curseforge.com/wow/addons/spoken-french), read 2026-11-16 | A product/dependency reference. Its MIT label does not grant permissions for another project's translations. |

ClassicUA's attribution evidence names Greenya, Jakanis and other contributors in its TOC and an extensive contributor list in README. Preserve the upstream author list and source link in a future attribution file, with scoped translator credits where known. Exact required wording, contributor authority and downstream license remain unresolved. Credits alone do not cure missing permission.

## Content rights differ from code rights

Spoken documents game quest/gossip/readable text and names as Blizzard material. It documents Places lore derived from Warcraft Wiki under CC BY-SA 4.0 and mixed sources for Bosses, including Adventure Guide text, Warcraft Wiki, Forever quests and EG Link output. EG Link output carries CC BY 4.0 in the upstream source register. Those statements identify obligations to investigate for each chosen input; they do not establish ownership of every downstream derivative.

For wiki-derived lore, record article URL, revision where available, author/history attribution route, source license, modifications and translated derivative license. Preserve applicable attribution, license link, change indication and share-alike obligations. A new Ukrainian rendering of a Spoken story still needs the story's source provenance. ClassicUA zone/NPC terms do not supply or license that story.

For any future bundled font, verify its own license and notices. Do not copy ClassicUA fonts, logos, icons, screenshots or UI art merely because they are available. Newly authored Stage 1 diagnostic prose and metadata avoid ClassicUA content redistribution, and the test package should use no borrowed art or fonts unless independently cleared.

## Permissions to resolve

Before importing publishable ClassicUA-derived content, obtain a documented answer covering:

1. Copying and redistributing translated text in separate Spoken Community Packs and source/build artifacts.
2. Adapting grammar templates, editing wording, creating summaries, and preserving contributor credits.
3. Whether maintainers can grant rights for the relevant contributors and whether Crowdin or other contribution terms impose conditions.
4. Sending translated text to an external TTS provider, storing inputs and takes, and distributing generated narration, including commercial/provider restrictions and permitted downstream reuse.
5. Whether a code grant, a translation grant and an audio grant differ; their scope, revisions, license, required notices and revocation/version implications.

Also evaluate underlying game/server text rights and the selected provider's applicable terms before TTS. Text redistribution permission must not be interpreted as automatic permission for provider processing or audio derivatives. Provider choice and audio licensing are undecided.

## Publication gates

| Gate | Current status | Evidence required to clear |
| --- | --- | --- |
| Metadata and original diagnostic pack | Technically feasible for local testing; no publication requested | Original authorship record, dependency and artifact validation, no borrowed content |
| ClassicUA-derived text pack | Blocked for publication; no import in Stage 0 | Explicit applicable grant or license with authority and attribution requirements recorded |
| Wiki/Spoken-derived lore | Separate content review required | Per-story source/license/attribution trail and derivative obligations satisfied |
| Generated Ukrainian audio | Deferred and blocked pending rights and design decisions | TTS derivative/processing rights, provider terms, source review, approved generation infrastructure and budget |
| Public Community Pack listing | Deferred | All content gates plus compliant release asset, checksum, size and site administrative approval |

Do not choose a permissive content license on behalf of upstream authors. An independent repository may license its original tooling separately while marking upstream-derived content according to its actual terms.

## Proposed provenance records

Maintain `sources.lock.json` for repository URL, exact commit, file SHA-256, observed license evidence, adapter version and target client profile. For every mapped unit, derive a sidecar with source path/key/field, layer and overridden predecessors, source hash, canonical target ID, matching evidence, transformations, AI/review status and permission reference. Record page-chain and ambiguity evidence where applicable.

Use source text hashes and references in review metadata when copied text is unnecessary. Rebuild Ukrainian text from pinned sources after permission is settled; keep only small mapping decisions and review outcomes under hand maintenance. Never turn provenance into a second editable translation corpus.

Generated artifacts should carry source/revision and attribution manifests, license notices, and a content inventory. Release validation must reject unresolved permission states and unsupported content licenses. No release, source translation snapshot, audio take or public asset was created during this stage.

# Ukrainian Quest page fonts in Spoken 3.10.1

[Українська](SPOKEN_3101_COMPENDIUM_FONT.uk.md)

On WoW: Forever, Ukrainian was reported available under **Text Language**, with
readable Quest titles in the left list and squares in the selected Quest's title
and body on the right. The two sides share translated title lookup but select
fonts independently. The audited source is `spoken/v3.10.1` at
`db5669b0a39815dd38568f0e871f4ced82bc9229`.

| Surface | Behavior at the pin |
| --- | --- |
| Text Language | The language probe can fall back to the font declared by the Text Pack. `Spoken_Quest_UA` already declares and ships Noto Sans. [Text font resolver](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/Texts.lua#L183-L238) |
| Left Quest list | Quest rows use `GameFontHighlight`; titles come from the same lookup used by the right page. [Quest title lookup](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Quests/UI/QuestsTab.lua#L152-L180), [list font](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/Compendium.lua#L1613) |
| Right Quest page | The Quest tab gives the shared page its addon namespace, which has no `FontFor` method. The page therefore uses `QuestTitleFont` for the title, and the parchment body uses `QuestFont`. The configured skin may supply another face. Neither path routes Quest text through `Spoken:FontForLanguage`. [Quest page creation](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Quests/UI/QuestsTab.lua#L1642-L1644), [title font](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/Compendium.lua#L2054-L2059), [body font](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/TextView.lua#L88-L94) |

The public `Spoken:FontForLanguage(fontObject, code, cache)` API returns a
font path for a caller to apply. The Quest Compendium needs an upstream change
to route its title, part headings and body through that resolver. Places
already forwards its page owner's `FontFor` to the public resolver. An
equivalent Quest implementation should use the effective text language, keep
stock fonts for English fallback, and handle stock and skinned pages.
[Public API](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/API.lua#L746-L750),
[Places example](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Places/Language.lua#L168-L175)

## Verify in WoW: Forever

1. Install and enable official `Spoken` and `Spoken_Quests` 3.10.1 and the
   Ukrainian Quest Text Pack. Select Ukrainian under **Text Language** and
   run `/reload`.
2. In the Compendium, open a translated quest with a visible description or
   completion. Compare the left title with the right title and body. Record
   the client locale, active skin and whether **і ї є ґ І Ї Є Ґ** render.
3. With squares visible, run the read-only resolver probe below and record the
   two paths. A valid path returned for a widget that still shows squares is
   consistent with the page failing to apply the resolved face.
4. Set **Text Language** to English and reload to check the English page. After
   an official font fix, repeat for both languages with the default and any
   active skin.

```lua
/run print(Spoken:FontForLanguage(QuestTitleFont,"ukUA"),Spoken:FontForLanguage(QuestFont,"ukUA"))
```

The automated test runs the pinned resolver with simulated client font support.
Right-page glyph acceptance remains open in [issue #38](https://github.com/korwin4games/spoken-ukrainian/issues/38).


## Strict no-modification policy

Spoken Ukrainian must **not modify, patch, replace, or monkey-patch** the
installed official Spoken player or `Spoken_Quests`, including through build
or installation tools. No upstream code patch is part of this repository's
implementation. The public Text Pack and font-resolver APIs in Spoken 3.10.1
cannot change the Quest Compendium page's font owner from an independent
Ukrainian pack. The right-hand glyph issue therefore remains **blocked**, not
fixed by the existing Quest Text Pack.

Retain the supported `X-Spoken-LanguageFont` metadata and existing native Quest
translation. Do not globally override WoW fonts, reach private Compendium
objects, spoof the client locale, or ship a modified player. Retest only when
a newer **official unmodified** Spoken version exposes the needed font handling;
updating the pin requires its own verification. An optional, independent
Ukrainian display window is a separate design choice and cannot be represented
as a fix for the built-in Compendium.

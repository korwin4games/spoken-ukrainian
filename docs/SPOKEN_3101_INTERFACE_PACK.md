# Ukrainian interface for Spoken 3.10.1

[Українська](SPOKEN_3101_INTERFACE_PACK.uk.md)

`Spoken_Interface_UA` is an optional addon in Spoken Ukrainian. It translates
common settings, playback controls and Compendium labels, with interface
strings for Spoken, Quests, Places, Readables, Bosses and Developer. Keys the
pack omits use Spoken's built-in locale, then English. Quest and Gossip
wording comes from separately installed Text Packs.

## Install and select Ukrainian

1. Install official Spoken 3.10.1. With the game closed, copy
   `addons/Spoken_Interface_UA` from this repository into
   `_forever_/Interface/AddOns/`. The folder must directly contain
   `Spoken_Interface_UA.toc` and `Interface.lua`.
2. Enable **Spoken Ukrainian: Interface** in the game's AddOns list.
3. Open `/sp settings` → **Language** → **Interface Language**, select
   **Українська**, and run `/reload`. This setting is account-wide.
4. Check that `/sp settings` shows **Мова інтерфейсу** and the Compendium's
   Quest tab shows **Завдання** if official `Spoken_Quests` is installed.

**Text Language** controls content. Use it separately if you install a Ukrainian
Quest or Gossip Text Pack. Voice choices are independent of both settings.
To switch back, select **Автоматично** under **Мова інтерфейсу** and reload.
You can also disable the Interface Pack and reload to use the client's language.

## If Ukrainian is missing

Check the installed Spoken version, addon folder and enabled state first.
Spoken 3.10.1 also requires its settings font to draw the pack's native name
before offering Ukrainian under **Interface Language**. The **Text Language**
menu can use a font supplied by a Text Pack, so Ukrainian may appear there
even when the interface check fails. Verify the choice and readable glyphs in
WoW: Forever. Automated checks exercise the discovery, language gate, load
and fallback logic with simulated client fonts.

Upstream contract at the audited `spoken/v3.10.1` pin.
[Spoken Interface Packs](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/docs/contributors/INTERFACE-PACKS.md)

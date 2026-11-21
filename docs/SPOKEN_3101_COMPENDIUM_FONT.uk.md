# Шрифти українських завдань у Компендіумі Spoken 3.10.1

[English](SPOKEN_3101_COMPENDIUM_FONT.md)

У WoW: Forever українська доступна в меню **Мова тексту**. За спостереженням
у грі, назви завдань у списку ліворуч читаються, а назва й текст вибраного
завдання праворуч відображаються квадратиками. Обидві частини беруть переклад
назви з одного джерела, але шрифти вибирають окремо. Перевірена ревізія
`spoken/v3.10.1` — `db5669b0a39815dd38568f0e871f4ced82bc9229`.

| Де | Поведінка в перевіреній ревізії |
| --- | --- |
| Мова тексту | Під час перевірки Spoken може використати шрифт із текстового пакета. `Spoken_Quest_UA` уже містить Noto Sans і вказує його в метаданих. [Вибір шрифту тексту](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/Texts.lua#L183-L238) |
| Список завдань ліворуч | Рядки завдань використовують `GameFontHighlight`. Назви беруться з того самого джерела, що й на правій сторінці. [Пошук назв](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Quests/UI/QuestsTab.lua#L152-L180), [шрифт списку](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/Compendium.lua#L1613) |
| Сторінка завдання праворуч | Вкладка завдань передає спільній сторінці простір імен аддона, де відсутній метод `FontFor`. Заголовок використовує `QuestTitleFont`, а основний текст на пергаменті — `QuestFont`. Тема оформлення може задати інший шрифт. Жоден із цих шляхів не викликає `Spoken:FontForLanguage` для тексту завдання. [Створення сторінки](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Quests/UI/QuestsTab.lua#L1642-L1644), [шрифт заголовка](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/Compendium.lua#L2054-L2059), [шрифт тексту](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/UI/TextView.lua#L88-L94) |

Публічний метод `Spoken:FontForLanguage(fontObject, code, cache)` повертає
шлях до шрифту, який має застосувати сам викликач. Потрібна зміна в
офіційному Spoken, щоб заголовок, назви частин і текст завдання використовували
цей метод. Вкладка Places уже викликає його через `FontFor`. Аналогічна
реалізація для завдань має враховувати фактичну мову тексту, зберігати
стандартні шрифти для англійського тексту й працювати з темами оформлення.
[Публічний API](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken/API.lua#L746-L750),
[приклад Places](https://github.com/rusty-key/spoken-wow/blob/db5669b0a39815dd38568f0e871f4ced82bc9229/addons/Spoken_Places/Language.lua#L168-L175)

## Перевірка у WoW: Forever

1. Увімкніть офіційні `Spoken` і `Spoken_Quests` 3.10.1 та український
   текстовий пакет завдань. Виберіть українську в меню **Мова тексту** й
   виконайте `/reload`.
2. Відкрийте в Компендіумі перекладене завдання з видимим описом або текстом
   завершення. Порівняйте назву ліворуч із заголовком і текстом праворуч.
   Запишіть мову клієнта, активну тему оформлення та чи видно **і ї є ґ І Ї Є Ґ**.
3. Якщо видно квадратики, виконайте команду нижче й запишіть обидва шляхи.
   Якщо шлях є, а квадратики залишилися, це узгоджується з тим, що сторінка
   не застосувала підібраний шрифт.
4. Виберіть англійську як **Мову тексту** й перезавантажте інтерфейс для
   перевірки англійської сторінки. Після офіційного виправлення повторіть
   перевірку обох мов зі стандартним та активним оформленням.

```lua
/run print(Spoken:FontForLanguage(QuestTitleFont,"ukUA"),Spoken:FontForLanguage(QuestFont,"ukUA"))
```

Автоматичний тест перевіряє метод Spoken на імітованому клієнті. Перевірка
літер на правій сторінці залишається відкритою в [issue #38](https://github.com/korwin4games/spoken-ukrainian/issues/38).


## Підготовлене виправлення для upstream

У межах [PR #43](https://github.com/korwin4games/spoken-ukrainian/pull/43) додано
[мінімальний патч для офіційного Spoken](upstream/spoken-quests-compendium-font.patch).
Патч **не встановлюється нашим аддоном** і не змінює локальні файли WoW.
Він призначений для прийняття супроводжувачами Spoken або ізольованої перевірки
на тимчасовій копії закріпленого джерела.

Зміни тільки в `addons/Spoken_Quests/UI/QuestsTab.lua`:
- `QuestsTab:FontFor(fontObject)` використовує фактичну `Text Language`
  через `VO.Language:GetTextLanguage()` і публічний
  `Spoken:FontForLanguage(fontObject, language, self)`.
- `C.NewPage(holder, QuestsTab)` надає цей метод штатній сторінці.
  `Compendium.lua` і `TextView.lua` уже підтримують `FontFor` власника,
  зокрема для заголовка, основного тексту, назв частин і тем оформлення.
- За відсутності нового API застосовується звичайний шрифт клієнта.
  Англійська `Text Language` використовує вибір шрифту офіційного Spoken.

Перевірка патча відбувається **без зміни upstream checkout**: тест копіює
файл закріпленої ревізії в тимчасовий каталог, виконує
`git apply --check` і `git apply` до копії та перевіряє Lua-метод.
Запуск із локально доступним checkout `spoken-wow`:

```sh
uv run --locked python -m unittest discover -s tests -p 'test_spoken_upstream_quest_font_patch.py' -v
```

**Не вважайте виправлення доступним у грі**, поки воно не потрапить до
офіційного релізу Spoken. Після цього потрібно окремо оновити закріплену
версію, повторити тести й перевірити кирилицю у WoW: Forever. Issue #38
залишається відкритим.

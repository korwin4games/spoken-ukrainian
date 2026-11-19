# Командний рядок Spoken Ukrainian

[English](CLI.md)

## Підготовка й закріплені ревізії

Встановіть Git, uv і Python 3.12: uv може встановити версію з `.python-version`. Для тестів потрібна спільна бібліотека Lua 5.4 (у CI на Ubuntu це `liblua5.4-0`). Node потрібен лише для перевірки синтаксису JavaScript. Клонуйте сусідні репозиторії та перейдіть у detached HEAD на ревізії з [sources.lock.json](../sources.lock.json). Команди підготовки завантажують репозиторії з мережі. Команди проєкту читають чисті локальні копії й завершуються помилкою, якщо ревізія або хеш перевіреного файла відрізняється. Виконуйте приклади з кореня проєкту й замінюйте значення на кшталт `CANDIDATE_ID` дійсними ідентифікаторами з локальних звітів.

```bash
git clone https://github.com/korwin4games/spoken-ukrainian.git
cd spoken-ukrainian
uv python install 3.12
uv sync --locked
git clone https://github.com/rusty-key/spoken-wow.git ../spoken-wow
git clone https://github.com/greenya/ClassicUA.git ../ClassicUA
SPOKEN_PIN=$(uv run --locked python -c 'import json; print(json.load(open("sources.lock.json"))["spoken"]["revision"])')
CLASSICUA_PIN=$(uv run --locked python -c 'import json; print(json.load(open("sources.lock.json"))["classicua"]["revision"])')
git -C ../spoken-wow switch --detach "$SPOKEN_PIN"
git -C ../ClassicUA switch --detach "$CLASSICUA_PIN"
export SPOKEN_SOURCE="$(realpath ../spoken-wow)"
export CLASSICUA_SOURCE="$(realpath ../ClassicUA)"
```

## База даних, середовище і статистика

`SPOKEN_TRANSLATION_DB` задає сталий файл SQLite для всіх команд. Типове розташування — `$XDG_DATA_HOME/spoken-ukrainian` або `~/.local/share/spoken-ukrainian`. Параметр `--db` має пріоритет там, де його підтримано; `SPOKEN_SOURCE` задає копію для тестів. CI також використовує `CLASSICUA_SOURCE` у параметрах команд. `UV_CACHE_DIR` дозволяє перенести кеш uv до каталогу з правом запису.

`status` показує файл і лічильники журналів без створення бази. `init` створює або мігрує схему; звичайні команди перевірки також переносять валідовані старі журнали. `backup` створює знімок SQLite з історією схвалень, оцінок агента й імпортів. `--output` діє для резервної копії: шлях має бути новим і без символічних посилань. Якщо даних бракує, спочатку знайдіть попередню базу. `imports` виводить окремі JSON-розділи для машинних, людських і агентських імпортів, явних виборів і фактичного вмісту останнього ZIP. Див. [сховище SQLite](SQLITE_TRANSLATION_STORE.md) і [статистику імпорту](IMPORT_STATISTICS.md).

```bash
uv run --locked python tools/translation_db.py status
uv run --locked python tools/translation_db.py init
uv run --locked python tools/translation_db.py backup --output /tmp/spoken-translations-backup.sqlite3
uv run --locked python tools/translation_db.py imports
```

## Політика джерел і локальні аудити

Редагуйте [translation_sources.json](../config/translation_sources.json) за [правилами ланцюжка джерел](TRANSLATION_SOURCE_CHAIN.md). Порядок визначає локальну черговість провайдерів. Для порожнього списку чи об’єкта аудит потребує фактичної мови клієнта. Заглушки та макети провайдерів не дають справжніх перекладів. Правила зберігання й обробки позначок ШІ діють окремо від черговості та схвалення. Якщо команда повідомляє про помилку шляху чи ревізії, перевірте локальну копію перед повтором.

`classicua_audit.py` приймає закріплений `--source` і необов’язковий `--output` для метаданих фактичних записів. `stage3_report.py` читає обидві ревізії і виводить метадані; `--reviews` передає незалежно перевірені відповідності, а `--candidate` разом із `--candidate-manifest` перевіряють окремо підготовлене оновлення. `stage4_coverage.py` приймає `--spoken`, необов’язкові `--policy`, `--client-locale` та `--output`; звіт охоплює кандидатів і повний канонічний інвентар. `gossip_coverage.py` записує ігноровані JSON і CSV NPC. Зберігайте результати в `build/`. Див. [етап 3](STAGE_3_IMPLEMENTATION.md), [етап 4A](STAGE_4A_INVENTORY_COVERAGE.md) та [покриття Gossip](GOSSIP_COVERAGE_AUDIT.md).

```bash
uv run --locked python tools/classicua_audit.py --source "$CLASSICUA_SOURCE" --output build/classicua-audit.json
uv run --locked python tools/stage3_report.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --output build/stage3-report.json
uv run --locked python tools/stage4_coverage.py --spoken "$SPOKEN_SOURCE" --policy config/examples/client-language.json --client-locale enUS
uv run --locked python tools/gossip_coverage.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
```

## Ідентичність квестів, перевірка і машинний імпорт

Workbench записує чергу з метаданими в JSON і таблицю CSV. Доступні `--faction alliance|horde`, `--offset`, `--limit`, `--output`, `--worksheet-output` і необов’язковий `--reviews`. З `--decisions` повний набір `--source-id --target-id --decision --reason --reviewer` записує відхилення чи відкладення; `--help` показує точні коди причин. Замість цього `--approve-request` перевіряє незалежно підготовлений Stage 3 JoinProof від двох людей. Застаріле рішення, доказ чи невідповідну ідентичність буде відхилено. Див. [опис workbench](STAGE_4B_REVIEW_WORKBENCH.md).

Локальний сервер приймає `--port` (типово 8765), необов’язкові `--decisions`, `--reviews`, `--local-reviews`, `--translations` і `--policy`. У Translation Review перевірте оригінал, відредагуйте текст, запишіть рішення людини й окремо імпортуйте. `--import-approved` виконує явний імпорт схвалених квестів без HTTP-сервера. `--auto-import-one-to-one` запускає машинний імпорт квестів. Прапорці взаємовиключні. Машинні кандидати залишаються попередніми; чинні перевірки відсіюють непідтверджені або неоднозначні докази. Див. [людське схвалення](TRANSLATION_APPROVALS.md).

```bash
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --faction horde --limit 40
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --decisions build/stage4b-decisions.json --source-id SOURCE_ID --target-id TARGET_ID --decision deferred --reason insufficient_evidence --reviewer REVIEWER
uv run --locked python tools/stage4b_workbench.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --approve-request build/join-proof.json
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --port 8765
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --import-approved
uv run --locked python tools/review_ui_server.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --auto-import-one-to-one
```

## Перевірка Gossip, чернетки Codex і машинний імпорт

`queue` створює приватні дедупліковані групи й пакети без заміни чернеток; `--batch-size` приймає 1–100. Відредагуйте приватний пакет, далі `propose --input` додасть версію на розгляд від `manual` або `own_translator`. `status` показує журнал. Для `review` потрібні точна `--version`, рев’ювер і рішення; схвалення потребує всіх п’яти перевірок. `import-approved` окремо записує чинні схвалені групи. Застарілі або суперечливі переклади та неповні підтвердження відхиляються. Допоміжна команда Codex типово лише перевіряє вхідні дані; `--apply` явно запускає Codex один раз для обраного пакета й може витратити квоту моделі. Результат є чернеткою. Див. [ручну перевірку Gossip](GOSSIP_TRANSLATION_REVIEW.md).

Окрема команда `gossip_machine_import.py status|import` показує лічильники або записує чинні точні попередні збіги ClassicUA. Спільні репліки рахуються один раз; змінені докази переходять в очікування оновлення. Див. [машинний імпорт](GOSSIP_MACHINE_IMPORT.md).

```bash
uv run --locked python tools/gossip_translation_review.py queue --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --batch-size 40
uv run --locked python tools/gossip_translate_codex.py --input build/gossip-batches/batch-0001.json
uv run --locked python tools/gossip_translate_codex.py --input build/gossip-batches/batch-0001.json --apply
uv run --locked python tools/gossip_translation_review.py propose --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --provider manual --input build/gossip-batches/batch-0001.json
uv run --locked python tools/gossip_translation_review.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_translation_review.py review --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --version VERSION_ID --reviewer REVIEWER --decision approved --checked-text --checked-grammar --checked-ai --checked-rights --checked-all-contexts
uv run --locked python tools/gossip_translation_review.py import-approved --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_machine_import.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/gossip_machine_import.py import --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
```

## Порівняння ревізій і провайдерів

`capture` зберігає поточний перевірений знімок ClassicUA. `template` записує приватний пакет із `--provider`, `--revision`, `--output`, `--offset`, `--limit`; заповніть український текст і посилання на джерело, далі виконайте `ingest --input`. Файл кандидата не може видавати інше джерело за ClassicUA або міняти закріплену англійську. Ревізії знімків незмінні. `revisions` показує збережені джерела й ревізії. `diff` порівнює ревізії одного провайдера. `compare-providers` потребує справді іншого `--other-provider`. Обидві команди приймають `--before`, `--after`, `--change all|added|removed|changed|unchanged`, `--offset` та `--limit` (1–100). Відсутній знімок спочатку додайте через capture або ingest. Звіти містять тексти й походження, тому зберігайте їх приватно.

`conflicts` підсумовує версії. Для `review` потрібні `--candidate`, `--decision approved|rejected|deferred`, `--reviewer`, а для схвалення — усі п’ять прапорців. `activate` явно вибирає схваленого чинного кандидата. Для `clear` потрібні `--domain quest|gossip`, `--target` і `--reviewer`. `active` повторно перевіряє чинні вибори, за потреби лише для одного домену. `selection-history` показує попередні активації й скасування для цілі. `--db` задає спільну базу. Передавайте закріплені копії для capture, template, ingest, review, activate, clear і active. Див. [перевірку джерел](SOURCE_REVISION_REVIEW.md).

```bash
uv run --locked python tools/source_revision_review.py capture --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/source_revision_review.py template --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --provider another --revision SOURCE_B_REV --output build/source-b.json --limit 40
uv run --locked python tools/source_revision_review.py ingest --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --input build/source-b.json
uv run --locked python tools/source_revision_review.py revisions
uv run --locked python tools/source_revision_review.py diff --provider classicua --before PRIOR_CLASSICUA_REV --after "$CLASSICUA_PIN" --change changed
uv run --locked python tools/source_revision_review.py compare-providers --provider classicua --other-provider another --before "$CLASSICUA_PIN" --after SOURCE_B_REV --change all
uv run --locked python tools/source_revision_review.py conflicts
uv run --locked python tools/source_revision_review.py review --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --reviewer REVIEWER --decision approved --checked-text --checked-grammar --checked-ai --checked-rights --checked-all-contexts
uv run --locked python tools/source_revision_review.py activate --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --reviewer REVIEWER
uv run --locked python tools/source_revision_review.py active --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --domain gossip
uv run --locked python tools/source_revision_review.py clear --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --domain gossip --target TARGET_ID --reviewer REVIEWER
uv run --locked python tools/source_revision_review.py selection-history --domain gossip --target TARGET_ID
```

## Агент перевірки перекладів

`status` і `report` показують лічильники та сторінки кандидатів. `history` показує часові позначки оцінок, зокрема застарілих. `review one` приймає один точний `--candidate`; для `review batch` цей параметр можна повторити. `review pending` явно обробляє наступний обмежений пакет кандидатів без оцінки. Спільні параметри: `--module all|quests|gossip`, `--status`, `--limit 1..100`, `--offset`, `--db`; `--json` дає структурований вивід. `--dry-run` під час перевірки обчислює оцінки без їх збереження. Необов’язковий `--model-assessment build/model-notes.json` для одного запису додає окремо отримані поради. Інструмент сам не запускає модель. Див. [схему та правила оцінювання](REVIEW_ASSISTANT_AGENT.md).

`import-verified` потребує `--dry-run` або `--confirm`. Попередній перегляд і запис показують кількість придатних, запланованих, імпортованих, уже імпортованих, пропущених і конфліктних записів, а також ідентифікатори й коди причин. Підтверджена команда типово розглядає весь вибраний модуль; `--candidate` може звузити набір. `--limit` обмежує пакети перевірки, сторінки результатів і явні списки ID. Успішні дії, зокрема попередній перегляд із пропусками, повертають 0; помилки даних, доказів або сховища — 1; помилки синтаксису argparse — 2. Оновіть застарілі ID через status, а конфлікти розгляньте вручну. Імпорт робить записи придатними для приватної збірки, яка повторно перевіряє докази.

```bash
uv run --locked python tools/translation_agent.py status --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module gossip --status unreviewed --json
uv run --locked python tools/translation_agent.py review one --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --dry-run
uv run --locked python tools/translation_agent.py review one --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --model-assessment build/model-notes.json
uv run --locked python tools/translation_agent.py review batch --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --candidate SECOND_CANDIDATE_ID
uv run --locked python tools/translation_agent.py review pending --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module quests --limit 25
uv run --locked python tools/translation_agent.py report --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --status needs_human_review --json
uv run --locked python tools/translation_agent.py history --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --candidate CANDIDATE_ID --json
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --dry-run --json
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module quests --confirm
uv run --locked python tools/translation_agent.py import-verified --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE" --module gossip --confirm
```

## Локальна збірка, встановлення й перевірки

`build_ukrainian.py` повторно перевіряє закріплені копії, автоматично оновлює машинні імпорти Quest і Gossip і перевіряє наявні імпорти агента перед створенням приватного відтворюваного ZIP і SHA-256 у `dist/`. Відсутня чи змінена копія, застарілі людські докази або відсутність безпечних моментів квесту можуть зупинити збірку. `install_addon.py` приймає точний каталог WoW Forever через `--addons` і необов’язковий `--archive`; `--dry-run` показує план. Звичайне встановлення записує дві папки приватних аддонів і зберігає офіційний Spoken. Небезпечні шляхи чи архіви блокують встановлення. Див. [локальну збірку та перевірку в грі](QUEST_LOCAL_TEST_BUILD.md).

`build.py` не приймає параметрів і збирає окремий історичний діагностичний архів із контрольною сумою. Тести перевіряють закріплені дані й виконують симуляції Lua. `version.py show` показує версію проєкту, `check [--tag vX.Y.Z]` перевіряє узгодженість метаданих і тега, а `bump patch|minor|major --dry-run` показує заплановану зміну. Справжній bump записує VERSION і потребує синхронізації метаданих, lock-файла й журналу змін. Перша стабільна major-версія потребує `--approve-stable`. Див. [правила версій](VERSIONING.md).

Для діагностики звірте ревізії й чистоту копій, переконайтеся, що команди перевірки та збірки використовують той самий файл SQLite, і перезапустіть UI після зміни ревізій або політики. Відсутнього провайдера треба явно додати через capture або ingest. Зберігайте резервні копії, пропозиції, модельні поради, порівняння з текстами й згенеровані архіви приватно. Статуси агента й машинного імпорту є рекомендаційними та дозволяють тільки приватне тестування. Публічне поширення, офіційне озвучення та субтитри Spoken потребують окремих перевірок. Див. [архітектуру](ARCHITECTURE_UNMODIFIED_SPOKEN.md).

```bash
uv run --locked python tools/build_ukrainian.py --classicua "$CLASSICUA_SOURCE" --spoken "$SPOKEN_SOURCE"
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --dry-run
uv run --locked python tools/install_addon.py --addons "/path/to/Forever/Interface/AddOns" --archive dist/Spoken_Quest_UA_Local_Test.zip
uv run --locked python tools/build.py
uv run --locked python -m unittest discover -s tests -v
node --test tests/manager_frontend.test.cjs
uv run --locked python tools/version.py show
uv run --locked python tools/version.py check
uv run --locked python tools/version.py bump patch --dry-run
```

## Єдиний менеджер перекладів

`translation_manager.py reimport` виконує ту саму операцію, що й локальний
менеджер. Доступні модулі `Spoken_Quest_UA` та `Spoken_Gossip_UA`. Передайте чисті закріплені
копії джерел. `--db` дозволяє вибрати приватну SQLite. `--dry-run` збирає
ізольований пробний ZIP, а `--confirm` застосовує перевірений стан і ZIP.
`--reset-test-data` очищає лише тестові історії перевірки й імпорту та ручні
вибори джерел цього модуля. Підсумок розрізняє записи в базі, фактичні
етапи Quest, входження Gossip і спільні записи ZIP. Він окремо показує стани
зіставлення, перекладу й імпорту, доступність черги перевірки, зауваження
агента за версіями й непідтверджені збіги Gossip за входженнями NPC/hash.
Конфлікти кандидатів (`conflicts`) і записи з кількома перевіреними
англійськими оригіналами (`multiple_originals`) рахуються окремо.
Зареєструйте кандидата ClassicUA, створіть чернетку Quest або підтвердьте
вибрану версію в менеджері. Підтвердження зберігає п’ять людських перевірок
і звіряє вибраний текст із фактичним Quest ZIP. Для кількох оригіналів одне
схвалення охоплює точний закріплений набір формулювань і контекстів. Зміна
версії або варіанта потребує нового перегляду. Quest-команда `reimport`
застосовує чинні рішення без змін до Gossip ZIP і запису останньої збірки.
[Приклад у менеджері](TRANSLATION_MANAGER.md#приклад-перевірки-quest) показує
вибір між перекладами та перевірку журналу квестів і шрифту у WoW: Forever.
`--json` показує
детальні результати й коди помилок. Код 0 означає успішний перегляд або
застосування, 1 — помилку операції, 2 — помилку синтаксису.
Див. [посібник менеджера](TRANSLATION_MANAGER.md).

```bash
uv run --locked python tools/translation_manager.py reimport --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow --reset-test-data --dry-run --json
uv run --locked python tools/translation_manager.py reimport --module Spoken_Quest_UA --classicua ../ClassicUA --spoken ../spoken-wow --confirm
uv run --locked python tools/translation_manager.py reimport --module Spoken_Gossip_UA --classicua ../ClassicUA --spoken ../spoken-wow --confirm
```

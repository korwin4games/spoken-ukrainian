# Stage 4B.2 — локальний Quest Review UI

Локальний інтерфейс має окремі **Mapping Review** та **Translation Review**.
Потрібні Python 3.12+, Linux/POSIX, Git, Lua 5.4 shared library та чисті checkout
ClassicUA і Spoken на точних ревізіях із `sources.lock.json`. Залежностей pip,
зовнішніх API чи WoW для роботи UI не потрібно. **Реальних схвалених joins і
перекладів у цьому PR немає.**

## Запуск

Із кореня репозиторію:

```sh
python3 tools/review_ui_server.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow
```

Відкрийте **http://127.0.0.1:8765/** на цьому комп'ютері. `Ctrl+C` завершує
роботу; `--port 8766` змінює порт. Прив'язка — лише `127.0.0.1`.
`--policy config/translation_sources.json` обирає політику джерел. Для наявних
незалежних Stage 3 proofs додайте `--reviews build/my-stage3-reviews.json`;
цей вхідний файл UI не перезаписує.

## Процедура reviewer

1. У **Mapping Review** оберіть faction, сторінку, source та окремий target/voice.
   Числовий Quest ID/event — лише підказка. Порівняйте фактичні UA/EN тексти,
   NPC, speaker, voice, gender, faction та hashes. Непідтверджений English явно
   позначено недоступним, заміни іншим варіантом немає.
2. Для негативного рішення вкажіть reviewer і причину, натисніть Reject/Defer.
   Зберігаються лише метадані schema v2. Відхилена пара не може бути схвалена;
   deferred можна схвалити лише з повним незалежним proof.
3. Для **Approve mapping** підготуйте повний approve-request JSON за
   [Stage 4B процедурою](STAGE_4B_REVIEW_WORKBENCH.md), вставте його в поле
   `JoinProof` та натисніть кнопку. JSON має відповідати вибраній парі. Потрібні
   реальні незалежні evidence reviewer і mapping reviewer. UI не генерує proof
   чи attestations; перевіряє їх через ті самі Stage 3 gates, що й CLI.
4. У **Translation Review** натисніть «Зберегти поточних кандидатів / оновити».
   Лише перевірені joins можуть дати кандидата. Політика провайдера
   `store_locally=false` залишає текст тільки у RAM/браузері й блокує збереження
   та approval/import. Поточні кандидати доступні для перегляду окремо від історії.
5. Оберіть збережену версію. Порівняйте UA/EN, номер версії, source/target,
   provenance, hashes, editor і попередні рішення. Редагування → «Зберегти нову
   ручну версію» створює pending-версію; воно не змінює upstream і не переносить
   approval. Введений незбережений текст не можна схвалити.
6. Вкажіть content reviewer. Для **Approve translation** особисто перевірте та
   позначте всі чотири пункти: текст, граматика/шаблони, AI, права/attribution.
   Reject/Defer доступні окремо; повторний розгляд додає рішення до історії.
   Жоден content approval не є approval аудіо або runtime.
7. Натисніть **«Явно імпортувати схвалені»**. Сервер повторно перевіряє proof,
   ефективний текст, оригінал, контекст, політику й рішення. Імпорт — локальний
   інертний snapshot посилань на версії; він нічого не активує та не публікує.
   `approved` і `imported` показані окремо. Повторний імпорт ідемпотентний.

Еквівалентна CLI-процедура явного імпорту без запуску HTTP:

```sh
python3 tools/review_ui_server.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow \
  --import-approved
```

Для нестандартних файлів передавайте ті самі `--reviews`, `--local-reviews`,
`--translations`, `--decisions` та `--policy`, що й при запуску UI.

## Зберігання, оновлення та відновлення

- `build/stage4b-decisions.json`: сумісні metadata-only відмови/відкладення v2.
- `build/stage3-ui-reviews.json`: Stage 3 proofs, metadata-only v1.
- `build/translation-reviews.json`: приватний журнал v1 із локальними текстами,
  історією, reviewer, provenance та `imports`; `0600`, атомарний запис, fsync і
  захист від конфліктних процесів. Усі ці файли ігнорує Git.

Зміна лише ревізії/файлу може зберегти approval після незалежного аудиту й
перевірки mapping. Зміна UA, English, grammar або identity context робить стару
версію непридатною для імпорту. Ручний текст залишається в історії й не
перезаписується оновленням джерела. Суперечливі схвалені ручні версії блокують
імпорт, доки reviewer явно не відкличе зайве схвалення.

Наявні коректні v2 рішення завантажуються без міграції; Stage 3 proofs не стають
content approval. Для старої v1 workbench-схеми, stale/corrupt файла зупиніть UI,
збережіть приватну копію у `build/`, оберіть новий шлях і повторіть review;
відсутні hashes не можна домислювати. Для конфлікту перезапустіть сервер із
актуальним файлом. Деталі схеми, порівняння версій і recovery:
[архітектура persistent approvals](TRANSLATION_APPROVALS.md).

## Безпека та обмеження

Host, same-origin Origin, per-run CSRF token, JSON type/size та неоднозначні
Content-Length/Transfer-Encoding перевіряються для всіх змін. CSP, no-store,
no-CORS, відсутність access logs/CDN і безпечні `textContent`/`value` збережені.
Тексти дозволені тільки в RAM/локальному HTTP та приватному ігнорованому журналі;
**не додавайте їх у Git, CI artifacts чи публічні звіти**. Не відкривайте порт
через публічний proxy або port-sharing.

Це однокористувацький локальний інструмент: reviewer ID не є автентифікацією.
Автоматичного pin updater немає, історичні mapping baselines не завантажуються
самі. `another` залишається stub, `own_translator` — mock. Empty policy не викликає
провайдерів; UI не має справжнього `GetLocale()` і не вигадує локалізований текст.
Підтримано тільки Quests; інші content flows, TTS, пакети й runtime — поза scope.
Stage 4A discovery CLI не підключено до журналу approval/import.

## Тести

Усі committed fixtures — синтетичні. Запуск із кореня (потрібні локальні сокети):

```sh
python3 tools/version.py check
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

Тести охоплюють незалежні mapping proofs, content attestations, редагування,
версії, декілька synthetic providers, пріоритет, повторне збереження/імпорт,
застарілі докази, схеми, конфлікти, symlinks та HTTP Host/Origin/CSRF/size.

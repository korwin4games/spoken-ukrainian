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
3. Для **Approve mapping** розкрийте форму `JoinProof`: виберіть **один**
   фактично перевірений контекст/voice, внесіть ID реального **evidence reviewer**
   та **іншого незалежного mapping reviewer**, після особистої перевірки обох
   pinned джерел поставте два підтвердження й натисніть кнопку. UI формує
   request з уже аудованих SHA/refs і одного точного набору facts, але **не**
   підтверджує особу й **не** може довести, що люди прочитали джерела.
   Backend повторно перевіряє request тими самими Stage 3 gates, що й CLI.
   Для зовнішнього CLI спосіб подання JSON лишається доступним.
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

## Step-by-Step: перше ручне тестування (користувач UI)

1. Переконайтеся, що ви на гілці `feat/local-quest-review-ui`; перевірте Python 3.12+,
   Git та Lua 5.4. Клонуйте **ClassicUA** і **spoken-wow** поруч з основним repo.
   Виконайте `git checkout <revision>` у **кожному** джерелі, де `revision`
   береться з відповідного поля `sources.lock.json`. Перевірте `git status --short`
   у всіх трьох репозиторіях.
2. Запустіть сервер командою вище й відкрийте `http://127.0.0.1:8765/`.
   У вкладці **Mapping Review** виберіть фракцію, Quest і конкретний Spoken
   voice-варіант. Порівняйте UA/EN текст та provenance. Якщо англійський
   текст не підтверджено, mapping не схвалюйте.
3. Якщо кандидат неправильний, введіть reviewer ID, виберіть причину й
   натисніть **Відхилити**. Якщо є сумніви — **Відкласти**. Запис потрапить
   тільки до `build/stage4b-decisions.json`.
4. Якщо пара правильна, **перший реальний reviewer** незалежно відкриває
   вказані pinned файли й перевіряє повну відповідність; **другий реальний
   reviewer** повторно перевіряє її незалежно. Розкрийте **JoinProof**,
   виберіть точно один контекст (NPC, faction, gender, voice, event),
   внесіть різні ID обох осіб, поставте підтвердження й натисніть
   **Підтвердити Mapping**. Якщо доказів бракує — **Відкласти**, а не вигадувати.
   Успіх створить metadata-only proof у `build/stage3-ui-reviews.json`.
5. Перейдіть до **Translation Review** і натисніть **Зберегти поточних
   кандидатів / оновити**. Це лише discovery: тепер видно кандидати від
   дозволених джерел (кожен доступний provider — окремо), але вони ще
   не схвалені. `store_locally=false` забороняє їх збереження.
6. Виберіть версію в списку, звірте оригінал, переклад, provenance й історію.
   Щоб змінити текст, відредагуйте його й натисніть **Зберегти нову ручну
   версію**. Нова версія буде Pending і не змінить ClassicUA.
7. Заповніть **Content reviewer**. Лише після реальної перевірки позначте
   текст, граматику, AI та права/attribution і натисніть **Approve translation**.
   Відхилення й відкладення не створюють approval.
8. Перезапустіть сервер та перевірте, що approved version та історія
   залишилися. До імпорту її статус буде `approved`, але не `imported`.
9. Натисніть **Явно імпортувати схвалені** або запустіть CLI із
   `--import-approved`. Перевірте `imported (inert)`; повторіть дію й
   пересвідчіться, що `changed=false`. Імпорт **не** змінює WoW.
10. Подивіться локальні файли в `build/`, **не** додавайте їх у Git.
    Завершіть сервер через `Ctrl+C`. Не тестуйте на публічному сервері.

**Важливо:** із чистими офіційними source checkouts реальних approvals немає,
тому Translation Review спочатку може бути порожнім. Для першого позитивного
mapping потрібні *дві фактичні незалежні людські перевірки*.

## Контрольоване оновлення джерел

Поточні pins не змінюються автоматично: зміна ClassicUA або Spoken вимагає
окремого аудиту й перевірки Stage 3 proofs. Безпечний порядок:

1. Зробіть приватну резервну копію `build/`; зупиніть UI.
2. Підготуйте чисті нові source checkouts і **окремий** commit на оновлення
   `sources.lock.json`/маніфестів із перевіреними actual file SHA-256.
3. Запустіть повний source audit/тести для нових pins. Старі proof-файли не
   потрібно «підправляти» хешами; stale identity proof вимагає нового
   незалежного Stage 3 review.
4. Після нового перевіреного mapping натисніть Refresh, звірте provenance,
   переконайтеся, що еквівалентний текст/оригінал/контекст перевикористовує
   approval, а змінений має Pending/STALE.
5. Тільки після цієї перевірки виконайте явний Import. Без валідного proof
   він має відмовити. У цьому PR **немає автоматичного pin migration**.

## Термінальні логи та підтвердження Mapping

Після натискання **Підтвердити Mapping** сервер друкує структуровані
метадані подій у термінал (timestamp, рівень, назва дії та результат):

```text
INFO [review-ui] mapping.approve requested
INFO [review-ui] mapping.approve succeeded
```

Якщо Stage 3 відхилив доказ, побачите `mapping.approve failed reason=...`.
Дозволені лише безпечні коди помилок: тексти оригіналу/перекладу, дані
рев'юверів, повний JoinProof, CSRF-токени та HTTP access logs **ніколи
не друкуються**. Для оновлення перекладів аналогічно логуються
`translation.refresh`, `translation.decision`, `translation.edit`
та `translation.import`. Некоректні HTTP-запити відхиляються без
детального access logging.

Після **успішного** mapping approval пара **виходить із Pending-черги**,
а в окремому розділі **Approved mappings** стає видно її повний
source → target ID. Тому наступний вибраний Quest може бути Pending:
це **інший запис**, а не втрата схвалення. Перевірити можна також у
`build/stage3-ui-reviews.json` (лише метадані, без перекладів).
У разі помилки повідомлення в браузері містить безпечний код причини,
який можна порівняти з терміналом. Не натискайте Reject для вже
схваленої пари, щоб «виправити» статус.

## Якщо Approve translation залишає Pending

Перевірте, що в **Translation Review** вибрано потрібну **збережену**
версію, вказано **Content reviewer** і *особисто перевірено* всі чотири
пункти: текст, граматику, AI-обмеження й права/attribution. Ці прапорці
не встановлюються автоматично; без усіх чотирьох схвалення відхиляється.

Після натискання **Approve translation** UI тепер показує конкретні
відсутні підтвердження або безпечний серверний код помилки.
У терміналі успіх виглядає як
`translation.decision requested` → `translation.decision succeeded`,
відмова — `translation.decision failed reason=...`.

У разі успіху вибрана версія повинна показувати `approved` у списку
**Версії та історія**, але `not imported` до явного імпорту.
Не плутайте `approved` із `imported`. Якщо статус не оновився, звірте
ID вибраної версії, оновіть UI та перевірте термінальні логи.

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

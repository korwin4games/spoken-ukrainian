# Stage 4B.2 — локальний Quest Review UI

**Статус:** MVP локального UI для **ручної** перевірки Quest source→target mapping. Код зберігається в **цьому ж репозиторії**, використовує наявні адаптери ClassicUA/Spoken, інвентаризацію Stage 3 та правила Stage 4B. Цей сервер **не** призначений для публічного розгортання чи багатокористувацької роботи.

## Передумови

- Python 3.12 або новіший, Git і спільна бібліотека Lua 5.4 (як для Stage 2A).
- Два **чисті** локальні checkout: [Spoken](https://github.com/rusty-key/spoken-wow) та [ClassicUA](https://github.com/greenya/ClassicUA).
- Обидва checkout мають відповідати **точним повним commit SHA** з [sources.lock.json](../sources.lock.json). Для Spoken додатково перевіряється публічний файл-маніфест [tests/stage3_sources.json](../tests/stage3_sources.json).
- Жодні pip-пакети, зовнішні API, облікові записи чи встановлений клієнт WoW для перегляду UI не потрібні.

У корені \`spoken-ukrainian\`:

\`\`\`sh
python3 tools/review_ui_server.py \
  --classicua /absolute/path/to/clean-pinned-ClassicUA \
  --spoken /absolute/path/to/clean-pinned-spoken-wow
\`\`\`

Відкрийте **http://127.0.0.1:8765/** на тому самому комп'ютері. Завершення — \`Ctrl+C\`. Якщо порт зайнятий, додайте \`--port 8766\`. Сервер прив'язується **лише до 127.0.0.1**; аргументів для доступу із LAN/Інтернету немає.

## Робота reviewer

1. Виберіть **Horde** або **Alliance**, кількість записів (12/20/40), сторінку та конкретний \`source_id\`. Черга збудована за **Quest ID + event**; це *кандидати*, а не mappings.
2. Ліва панель показує **ефективний український текст ClassicUA** після правила \`classic → sod → forever\` і faction/shared fallback. Перед показом перевіряються фактичний UTF-8 SHA-256 поля та ревізія/файл/шар походження з аудиту.
3. Права панель показує **один підтверджений англійський оригінал Spoken** із закріпленого корпусу. Відображення можливе лише за збігу SHA-256 тексту з canonical target context. Якщо оригіналу немає або є неоднозначність, UI явно показує це і нічого не підставляє.
4. Перемикайте **окремі target/voice-варіанти**. Порівняйте реальний Quest moment, NPC/speaker, event, faction, gender, voice, оригінальний English-зміст та український текст; оцініть, чи це **одна** репліка, а не просто той самий числовий Quest ID.
5. Для негативного/невизначеного рішення введіть *справжній reviewer ID*, виберіть обґрунтовану причину й натисніть **Відхилити** або **Відкласти**. Запис зберігається тільки в \`build/stage4b-decisions.json\` (можна змінити через \`--decisions\` на інший файл **всередині** ігнорованого \`build/\`). Відхилений варіант прибирається з черги, відкладений — залишається видимим.
6. Для **позитивної** відповідності UI **не має кнопки Approve**. Потрібно окремо з другим незалежним реальним reviewer підготувати \`JoinProof\` з **одним цілісним контекстом**, потім використати CLI \`tools/stage4b_workbench.py --approve-request ... --reviews ...\` за [процедурою Stage 4B](STAGE_4B_REVIEW_WORKBENCH.md).

**Схвалення canonical identity ≠ схвалення українського тексту**. Граматика, AI, права, аудіо та підтримка runtime перевіряються окремо. UI не генерує pack, TTS, масові approvals або відібрані переклади.

## Дані та безпека

- Українські й англійські тексти залишаються **в RAM процесу та локальному HTTP-відповіді/браузері**. У JSON/CSV-звіт, файл рішень, Git, CI artifacts і логи тексти **не записуються**.
- Manual decision ledger — сувора **Stage 4B schema v2**: source/target ID, reviewer, причина, source/target revisions, file/field/context/blob SHA-256. Стара відмова після зміни доказів **не застосовується автоматично**, потрібно переглянути заново. Запис — атомарна заміна файлу.
- Сервер слухає тільки **loopback**; перевіряє HTTP Host, origin для змін, per-run CSRF token, JSON content type та розмір POST. Вбудований HTML/CSS/JS не звертається до CDN; діють CSP, no-store, no-CORS і відсутність access logs.
- Це **не** захищений багатокористувацький додаток. Той, хто має доступ до цього локального браузера/сеансу, може взаємодіяти з UI. **Не** виставляйте порт через публічні reverse proxy, відкритий SSH port forwarding або хмарні port-sharing сервіси.
- ID reviewer — локальна позначка, а не криптографічне підтвердження особи/незалежності. Справжнє підтвердження відбувається **поза UI**.

## Перевірки та обмеження

Тести \`tests/test_review_ui.py\` використовують **вигадані** UA/EN-тексти та синтетичні source/target contexts. Перевіряють дві панелі, різні voice-варіанти, недоступний English, схему рішень, збереження **тільки метаданих**, захист шляхів, origin/CSRF/Host HTTP, заборону approvals.

Початкова версія підтримує **лише Quests**. Gossip, Readables, Places та Bosses потребують власних правил proof/review. Проєкт наразі **не має реальних незалежно схвалених source→Spoken joins**, а UI не підключає новий переклад до гри автоматично.

Точні джерела й обмеження описано в [Stage 3 implementation](STAGE_3_IMPLEMENTATION.md), [Stage 4A coverage](STAGE_4A_INVENTORY_COVERAGE.md), [Stage 4B Workbench](STAGE_4B_REVIEW_WORKBENCH.md) і [Stage 2B compatibility](STAGE_2B_COMPATIBILITY.md).

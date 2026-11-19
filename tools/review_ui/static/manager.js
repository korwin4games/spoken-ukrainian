"use strict";

const el = id => document.getElementById(id);
const number = new Intl.NumberFormat("uk");
const labels = {
  ready: "Готовий", missing: "Немає перекладу", review: "Потрібна перевірка",
  conflict: "Конфлікт кандидатів", rejected: "Відхилено / відкладено", invalid: "Не пройшов перевірку", stale: "Застарів",
  multiple_originals: "Кілька перевірених оригіналів",
};
const mappingLabels = {
  mapping_verified: "Зіставлено вручну", mapping_provisional: "Попереднє зіставлення",
  mapping_pending: "Зіставлення потребує перевірки", mapping_conflict: "Неоднозначне зіставлення",
  mapping_rejected: "Зіставлення відхилено або відкладено", invalid_context: "Непідтримуваний контекст",
  stale: "Докази застаріли",
};
const translationLabels = {
  translation_available: "Переклад доступний", translation_missing: "Немає перекладу",
  translation_pending: "Переклад на перевірці", translation_approved: "Переклад схвалено",
  translation_rejected: "Переклад відхилено або відкладено",
};
const queueLabels = {
  quest_mapping: "Зіставлення Quest", quest_translation: "Перевірка перекладу Quest",
  gossip_translation: "Переклад Gossip", agent: "Оцінки агента",
};
const problems = {
  quest_mapping_rejected_or_deferred: "Рев’юер відхилив або відклав зіставлення. Перегляньте рішення.",
  conflicting_quest_runtime_variants: "Для цієї події є різні чинні схвалення. Перегляньте попередні рішення.",
  quest_runtime_review_stale: "Докази спільного рішення змінилися. Звірте актуальні оригінали й підтвердьте переклад знову.",
  quest_multiple_verified_originals: "Перегляньте кожен оригінал окремо. Для цієї події автоматичний імпорт заблоковано.",
  quest_original_missing: "У закріпленому корпусі немає підтвердженого оригіналу.",
  quest_mapping_unverified: "Для цього кандидата бракує доказів фракції, відповідності контексту або незалежної перевірки AI.",
  gossip_context_unsupported: "Для цього типу співрозмовника локальний ZIP не підтримує підстановку тексту.",
  gossip_original_missing: "У закріпленому корпусі немає підтвердженої репліки.",
};
const checkLabels = {
  line_breaks: "кількість переносів рядків",
  placeholder_correspondence: "відповідність змінних і позначок форматування",
  canonical_context: "підтвердження контексту",
};
const routes = {
  machine_1to1: "Машинний збіг 1:1", reviewed: "Перевірено вручну",
  source_selected: "Вибране джерело", agent_verified: "Перевірено агентом",
};
const errors = {
  manager_confirmation_required: "Підтвердіть переімпорт.",
  manager_reimport_already_running: "Інший переімпорт уже триває. Дочекайтеся його завершення.",
  manager_state_changed_retry_reimport: "Дані змінилися під час збірки. Оновіть список і повторіть.",
  no_unambiguous_quest_imports_for_local_test_pack: "Для збірки бракує однозначних перекладів квестів.",
  manager_reimport_timed_out_check_build: "Час очікування минув. Оновіть список, щоб перевірити стан збірки.",
  manager_reimport_worker_unavailable: "Не вдалося запустити збірку. Перезапустіть локальний менеджер.",
  manager_reimport_worker_terminated: "Збірку перервано. Оновіть список, перевірте стан ZIP і повторіть.",
  manager_reimport_worker_empty_response: "Збірка не повернула результат. Перевірте стан ZIP і повторіть через CLI.",
  manager_reimport_worker_invalid_response: "Не вдалося прочитати результат збірки. Повторіть через CLI.",
  manager_reimport_failed: "Не вдалося завершити переімпорт. Запустіть збірку через CLI, щоб побачити причину.",
  manager_classicua_checkout_invalid: "Потрібна чиста копія ClassicUA на закріпленій ревізії.",
  manager_spoken_checkout_invalid: "Потрібна чиста копія Spoken на закріпленій ревізії.",
};
let csrf, offset = 0, selected = null, listSeq = 0, detailSeq = 0, busy = false;
let loading = 0;
const pageSize = 30;

function make(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function badge(text, state) { return make("span", text, "badge " + state); }
Object.assign(errors, {
  manager_invalid_review_request: "Перевірте вибраний запис і підтвердження.",
  manager_review_checks_required: "Підтвердьте всі п’ять перевірок.",
  manager_review_context_blocked: "Цей контекст не можна безпечно зіставити з ігровим записом.",
  manager_invalid_translation_format: "Перевірте підстановки та форматування за англійським оригіналом.",
  manager_candidate_unavailable: "Кандидат застарів, відхилений або відсутній. Оновіть запис.",
  manager_candidate_not_built: "Текст не ввійшов до ZIP. Перевірте конфлікти та чинні схвалення.",
  conflicting_quest_runtime_variants: "Спершу відкличте суперечливе чинне схвалення або вибір джерела.",
  invalid_quest_runtime_review: "У локальній базі є недійсний запис перевірки Quest. Перевірте резервну копію бази.",
  source_quest_selection_requires_approved_stage3_mapping: "Спершу підтвердьте зіставлення Quest доказом Stage 3.",
  source_candidate_pinned_context_mismatch: "Доказ кандидата змінився. Звірте його з поточним оригіналом.",
});
function errorMessage(error) {
  return errors[error.message] || "Помилка застосунку. Оновіть сторінку й повторіть дію.";
}

function domain() { return el("module").value === "Spoken_Quest_UA" ? "quest" : "gossip"; }
function domainName() { return domain() === "quest" ? "Quest" : "Gossip"; }

async function whileLoading(work) {
  loading += 1;
  el("loading-bar").hidden = false;
  try {
    return await work();
  } finally {
    loading -= 1;
    el("loading-bar").hidden = loading === 0;
  }
}

async function call(action, payload) {
  return whileLoading(async () => {
    const response = await fetch("/api/manager/" + action, {
      method: "POST", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-Review-Token": csrf},
      body: JSON.stringify({module: el("module").value, ...payload}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.reason || result.error || "manager_request_failed");
    return result;
  });
}

function metrics(summary, build) {
  const tally = key => summary[domain()][key];
  const cells = [
    ["Усього записів", "total"], ["Імпортовано в ZIP", "included"], ["Не в ZIP", "not_included"],
    ["Конфлікти кандидатів", "conflicts"], ["Кілька перевірених оригіналів", "multiple_originals"],
    ["Без перекладу", "missing"], ["Готові до імпорту", "ready"],
    ["Зауваження агента", "agent_warnings"], ["Непідтверджені збіги Gossip", "unverified_alternatives"],
  ];
  el("metrics").replaceChildren(...cells.map(([label, key]) => {
    const card = make("div", undefined, "metric");
    card.append(make("span", label), make("strong", number.format(tally(key))));
    return card;
  }));
  const prefix = build ? "Останній дійсний ZIP · " + build.built_at + " UTC · SHA-256 " + build.sha256 : "Дійсної локальної збірки ще немає.";
  el("build-state").textContent = prefix + " · Покрито записаними імпортами: " + number.format(tally("recorded"));
}

function renderList(data) {
  metrics(data.summary, data.build);
  const rows = data.items.map(item => {
    const tr = make("tr");
    if (selected === item.id) tr.className = "current";
    const name = make("button", item.label, "name");
    name.type = "button";
    name.setAttribute("aria-pressed", String(selected === item.id));
    name.addEventListener("click", () => detail(item.id, name));
    const parts = item.id.split(":");
    const id = (item.type === "quest" || parts[0] === "gossip") ? parts[1] : item.id;
    tr.append(make("td", item.type === "quest" ? "Quest" : "Gossip"), make("td", id));
    tr.appendChild(make("td")).append(name);
    tr.appendChild(make("td")).append(
      badge(item.built ? "У ZIP" : item.recorded ? "Лише в базі" : "Не імпортовано", item.built ? "built" : ""));
    const statuses = tr.appendChild(make("td"));
    if (item.type === "quest") {
      statuses.append(badge(item.built ? "У ZIP" : item.candidate_conflict ?
        "Оберіть переклад" : item.status === "missing" ? "Додайте переклад" :
        "Готовий до імпорту", item.built ? "built" : ""));
    } else {
      statuses.append(badge(translationLabels[item.translation_state] || labels[item.status], item.status));
    }
    if (item.type !== "quest" && item.candidate_conflict) statuses.append(make("div", labels.conflict));
    if (item.type !== "quest" && item.status === "multiple_originals") statuses.append(make("div", labels.multiple_originals));
    if (item.type !== "quest" && item.mapping_state) statuses.append(make("div", mappingLabels[item.mapping_state], "muted"));
    const problem = item.type !== "quest" && (item.status !== "ready" || item.agent_warning);
    const flag = make("td", problem ? "⚑" : "—");
    flag.title = item.agent_warning ? "Є зауваження агента" : labels[item.status];
    if (problem) flag.setAttribute("aria-label", flag.title);
    tr.append(flag);
    return tr;
  });
  el("rows").replaceChildren(...rows);
  el("list-message").hidden = rows.length > 0;
  el("list-message").textContent = rows.length ? "" : "За цими фільтрами записів немає.";
  el("match-count").textContent = number.format(data.total) + " записів";
  el("page").textContent = data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} з ${data.total}` : "0 записів";
  el("prev").disabled = offset === 0;
  el("next").disabled = offset + pageSize >= data.total;
}

async function list() {
  const seq = ++listSeq;
  el("list-message").hidden = false;
  el("list-message").textContent = "Оновлюємо список…";
  try {
    const result = await call("list", {
      query: el("query").value, filter_by: el("filter").value,
      status: el("translation-status").value, offset, limit: pageSize,
    });
    if (seq === listSeq) renderList(result);
  } catch (error) {
    if (seq === listSeq) el("list-message").textContent = errorMessage(error);
  }
}

const eligibilityHelp = {
  selectable: "Можна вибрати для підтвердження.",
  register: "Додайте до журналу як чернетку, щоб вибрати для перевірки.",
  source_review: "Потрібен запис у журналі джерел. Перевірте походження й додайте кандидат через CLI.",
  mapping_required: "Спершу перевірте й підтвердьте зіставлення Stage 3.",
  context_blocked: "Контекст заблоковано. Звірте оригінал та ідентичність запису.",
  stale: "Докази застаріли. Оновіть джерело і повторіть незалежну перевірку.",
  review_blocked: "Є рішення відхилити або відкласти. Перегляньте його в журналі перевірки.",
  rights_blocked: "Права або походження не підтверджено. Перевірте дозвіл та джерело тексту.",
  format_blocked: "Формат або підстановки не відповідають оригіналу. Виправте текст у дозволеній чернетці.",
};

function simpleQuestControls(row) {
  const panel = make("section");
  const message = make("p");
  message.setAttribute("role", "status");
  panel.append(message);
  const options = new Map();
  for (const candidate of row.candidates) {
    if (!options.has(candidate.sha256)) options.set(candidate.sha256, candidate);
  }
  const editable = Boolean(row.review_binding && row.originals.length);
  const run = async (action, data) => {
    if (busy) return;
    busy = true;
    message.textContent = "Збираємо Quest ZIP…";
    for (const id of ["preview", "reimport", "module"]) el(id).disabled = true;
    try {
      const result = await call(action, {...data, identity: row.id,
        binding: row.review_binding, confirm: true});
      el("run-summary").hidden = true;
      el("operation-status").textContent = "Переклад застосовано та перевірено у ZIP.";
      await list();
      if (selected === row.id) await detail(row.id);
    } catch (error) {
      message.textContent = errorMessage(error);
    } finally {
      busy = false;
      for (const id of ["preview", "reimport", "module"]) el(id).disabled = false;
    }
  };
  panel.append(make("h3", options.size > 1 ? "Оберіть переклад" :
    options.size === 1 ? "Доступний переклад" : "Немає перекладу"));
  if (options.size) {
    const select = make("select");
    select.setAttribute("aria-label", "Оберіть український переклад");
    for (const candidate of options.values()) {
      const item = make("option", candidate.provider + " · " + candidate.text.slice(0, 100));
      item.value = candidate.sha256;
      if (row.built?.text_sha256 === candidate.sha256) item.selected = true;
      select.append(item);
    }
    const preview = make("pre");
    const first = options.keys().next().value;
    const update = () => { preview.textContent = options.get(select.value || first)?.text || ""; };
    select.addEventListener("change", update);
    update();
    const apply = make("button", "Використати переклад");
    apply.type = "button";
    apply.disabled = !editable;
    apply.addEventListener("click", () => {
      const key = select.value || first;
      if (key && window.confirm("Застосувати цей переклад до квесту та оновити Quest ZIP?")) {
        run("choose_quest", {candidate: key});
      }
    });
    panel.append(select, preview, apply);
  }
  const field = make("textarea");
  field.maxLength = 60000;
  field.setAttribute("aria-label", "Власний український переклад");
  field.placeholder = "Введіть свій український переклад…";
  const save = make("button", "Зберегти й застосувати");
  save.type = "button";
  save.disabled = !editable;
  save.addEventListener("click", () => {
    if (field.value.trim()) run("save_quest", {text: field.value});
  });
  const codex = make("button", "Скопіювати запит для Codex");
  codex.type = "button";
  codex.addEventListener("click", async () => {
    const prompt = "Translate these WoW: Forever Quest texts to natural Ukrainian. " +
      "Preserve all variables, placeholders, gender markers and formatting exactly. " +
      "Use Ukrainian Warcraft terminology, not Russian localization. " +
      "One Ukrainian translation must work for ALL English variants. " +
      "Return ONLY the Ukrainian translation:\n\n" + row.originals.join("\n\n---\n\n");
    try {
      await navigator.clipboard.writeText(prompt);
      message.textContent = "Запит скопійовано. Вставте в Codex, а переклад — у поле.";
    } catch (_) {
      message.textContent = "Не вдалося скопіювати. Перевірте доступ до буфера обміну.";
    }
  });
  panel.append(make("h3", "Додати переклад"), field, save, codex);
  if (!editable) panel.append(make("p", "Немає перевіреного англійського оригіналу для цього квесту."));
  return panel;
}

function reviewControls(row) {
  const panel = make("section");
  const status = make("p");
  status.setAttribute("role", "status");
  panel.append(status);
  const run = async (action, payload) => {
    if (busy) return;
    busy = true;
    const controls = ["preview", "reimport", "reset", "module"];
    controls.forEach(id => { el(id).disabled = true; });
    status.textContent = action === "confirm_candidate" ?
      "Перевіряємо докази та збираємо ZIP…" : "Перевіряємо докази та зберігаємо запис…";
    try {
      const binding = row.type === "quest" && action !== "review_mapping" ? {binding: row.review_binding} : {};
      const result = await call(action, {...payload, ...binding, identity: row.id, confirm: true});
      if (result.build !== "review_saved") renderResult(result);
      el("operation-status").textContent = action === "confirm_candidate" ?
        "Вибраний переклад перевірено в ZIP." : "Рішення збережено. Перевірте статус запису.";
      await list();
      if (selected === row.id) await detail(row.id);
    } catch (error) {
      status.textContent = errorMessage(error);
    } finally {
      busy = false;
      controls.forEach(id => { el(id).disabled = false; });
    }
  };
  const candidates = row.candidates.filter(c =>
    (c.review_id && (c.eligibility === "selectable" || c.draft_editable)) ||
    (c.registration_key && c.eligibility === "register"));
  const canAdd = row.draft_available || row.type === "gossip" && row.review_queue === "gossip_translation";
  if ((row.type === "quest" || row.originals.length === 1 && (candidates.length || canAdd)) &&
      !["invalid_context", "mapping_conflict", "mapping_rejected", "stale"].includes(row.mapping_state)) {
    const field = make("fieldset");
    const reviewer = make("input");
    reviewer.maxLength = 120;
    const name = make("label", "Ім’я рецензента ");
    name.append(reviewer);
    field.append(make("legend", "Рішення рецензента"), name);
    const select = make("select");
    select.setAttribute("aria-label", "Кандидат перекладу");
    const placeholder = make("option", "Виберіть один варіант");
    placeholder.value = "";
    select.append(placeholder);
    for (const candidate of candidates) {
      const option = make("option", candidate.provider + " · " + candidate.text.slice(0, 90));
      option.value = candidate.review_id || candidate.registration_key;
      select.append(option);
    }
    const context = make("pre");
    const checks = {};
    if (candidates.length || row.type === "quest") {
      field.append(select, context);
      for (const [key, label] of Object.entries({
        text: "Текст відповідає оригіналу", grammar: "Мову та форматування перевірено",
        ai: "Походження та використання ШІ перевірено", rights: "Права перевірено",
        all_contexts: row.type === "quest" ?
          "Цей переклад підходить для всіх наведених оригіналів і контекстів" : "Усі контексти перевірено",
      })) {
        const input = make("input");
        input.type = "checkbox";
        const check = make("label", undefined, "check");
        check.append(input, make("span", label));
        checks[key] = input;
        field.append(check);
      }
    }
    const draft = make("textarea");
    draft.maxLength = 60000;
    draft.setAttribute("aria-label", "Українська чернетка");
    const approve = make("button", "Підтвердити переклад");
    const save = make("button", "Зберегти чернетку");
    const register = make("button", "Додати кандидат до журналу");
    const withdraw = make("button", "Відкликати схвалення Quest");
    approve.type = save.type = register.type = withdraw.type = "button";
    const choice = () => candidates.find(c => (c.review_id || c.registration_key) === select.value);
    const update = () => {
      approve.disabled = choice()?.eligibility !== "selectable" || !reviewer.value.trim() ||
        Object.values(checks).some(input => !input.checked);
      register.disabled = choice()?.eligibility !== "register" || !reviewer.value.trim();
      withdraw.disabled = !choice()?.runtime_approval || !reviewer.value.trim();
      save.disabled = !reviewer.value.trim() || !draft.value.trim() ||
        !(canAdd || choice()?.review_kind === "quest");
    };
    select.addEventListener("change", () => {
      context.textContent = choice() ? row.originals.join("\n\n") + "\n\n" + choice().text : "";
      if (["quest", "runtime"].includes(choice()?.review_kind)) draft.value = choice().text;
      for (const input of Object.values(checks)) input.checked = false;
      update();
    });
    field.addEventListener("input", update);
    approve.addEventListener("click", () => {
      if (window.confirm("Зберегти рішення та перебудувати ZIP для " + domainName() + "?")) {
        run("confirm_candidate", {candidate: select.value, reviewer: reviewer.value,
          checks: Object.fromEntries(Object.entries(checks).map(([key, input]) => [key, input.checked]))});
      }
    });
    save.addEventListener("click", () => run("save_translation",
      {candidate: ["quest", "runtime"].includes(choice()?.review_kind) ? select.value : "",
        text: draft.value, reviewer: reviewer.value}));
    register.addEventListener("click", () => run("register_candidate",
      {candidate: select.value, reviewer: reviewer.value}));
    withdraw.addEventListener("click", () => {
      if (!withdraw.disabled && window.confirm("Записати відкликання схвалення? Поточний ZIP зміниться під час нової збірки.")) {
        run("withdraw_quest_approval", {candidate: select.value, reviewer: reviewer.value});
      }
    });
    if (row.type === "quest" || candidates.some(c => c.eligibility === "selectable")) field.append(approve);
    if (row.type === "quest" || candidates.some(c => c.eligibility === "register")) field.append(register);
    if (row.type === "quest" && candidates.some(c => c.runtime_approval)) field.append(withdraw);
    if (row.type === "quest" || canAdd || candidates.some(c => c.review_kind === "quest")) field.append(draft, save);
    if (row.type === "quest" && !candidates.length) {
      field.append(make("p", canAdd ? "Створіть власну чернетку або перевірте зіставлення Stage 3 для ClassicUA."
        : "Для редагування потрібен перевірений оригінал для кожного контексту."));
    }
    panel.append(field);
    update();
  }
  if (row.type === "quest" && ["invalid_context", "mapping_conflict", "mapping_rejected", "stale"].includes(row.mapping_state)) {
    panel.append(make("p", "Перевірте стан зіставлення та докази джерела перед збереженням рішення."));
  }
  if (row.mapping_options?.length) panel.append(mappingControls(row.mapping_options, run));
  return panel;
}

function mappingControls(options, run) {
  const controls = make("details");
  const form = make("fieldset");
  const select = make("select");
  select.setAttribute("aria-label", "Пара ClassicUA і Spoken");
  const empty = make("option", "Виберіть точну пару і контекст");
  empty.value = "";
  select.append(empty);
  options.forEach((option, index) => {
    const f = option.facts;
    const entry = make("option", [option.source_id, option.target_id, f.faction, f.npc_id,
      f.voice, f.player_gender].filter(value => value != null).join(" · "));
    entry.value = String(index);
    select.append(entry);
  });
  const evidence = make("pre");
  const reviewers = [];
  const checks = [];
  form.append(select, evidence);
  for (const [name, attestation] of [
    ["Рецензент доказів", "Я звірив точні файли, ID, етап, фракцію, NPC, голос, стать і текст."],
    ["Другий рецензент", "Я незалежно звірив джерела, оригінал і той самий контекст."],
  ]) {
    const input = make("input");
    input.maxLength = 120;
    const check = make("input");
    check.type = "checkbox";
    const label = make("label", name + " ");
    label.append(input);
    const attested = make("label", undefined, "check");
    attested.append(check, make("span", attestation));
    form.append(label, attested);
    reviewers.push(input);
    checks.push(check);
  }
  const submit = make("button", "Підтвердити зіставлення");
  submit.type = "button";
  const selectedOption = () => select.value === "" ? null : options[Number(select.value)];
  const reviewerNames = () => reviewers.map(input => input.value.trim());
  const update = () => {
    const [first, second] = reviewerNames();
    submit.disabled = !selectedOption() || !first || !second || first === second ||
      checks.some(check => !check.checked);
  };
  select.addEventListener("change", () => {
    const item = selectedOption();
    evidence.textContent = item ? [item.facts.english_original, item.source_text,
      item.evidence.source_reference, item.evidence.target_reference].join("\n\n") : "";
    checks.forEach(check => { check.checked = false; });
    update();
  });
  form.addEventListener("input", update);
  submit.addEventListener("click", () => {
    const item = selectedOption();
    if (submit.disabled || !item || !window.confirm("Зберегти рішення двох незалежних рецензентів?")) return;
    const [evidenceReviewer, mappingReviewer] = reviewerNames();
    const fields = ["npc_id", "npc_type", "voice", "faction", "wording_sha256",
      "source", "quest_id", "player_gender"];
    run("review_mapping", {join: {
      schema_version: 1, source_id: item.source_id, target_id: item.target_id,
      mapping_reviewer: mappingReviewer, proof: {...item.evidence,
        facts: Object.fromEntries(fields.map(key => [key, item.facts[key]])),
        evidence_reviewer: evidenceReviewer, greeting: false},
    }});
  });
  form.append(submit);
  controls.append(make("summary", "Перевірка зіставлення Stage 3"),
    make("p", "Виберіть пару й звірте наведені посилання із закріпленими файлами. Для рішення потрібні двоє різних рецензентів."),
    form);
  update();
  return controls;
}

function renderDetail(row) {
  if (row.type === "quest") {
    const english = make("section");
    english.append(make("h3", "Англійський оригінал"));
    for (const text of row.originals) english.append(make("p", text, "original"));
    const status = row.built ? "У ZIP" : row.candidates.length > 1 ?
      "Оберіть переклад" : row.candidates.length ? "Переклад знайдено" : "Немає перекладу";
    el("selected").replaceChildren(make("h3", row.label), make("p", row.id, "muted"),
      badge(status, row.built ? "built" : ""), english, simpleQuestControls(row));
    return;
  }
  const title = make("h3", row.label);
  const blocks = [title, make("p", row.id, "muted")];
  const identity = row.type === "quest" ?
    "Квест " + row.quest_id + " · етап " + row.event : "NPC " + (row.npc_id ?? "—");
  blocks.push(make("p", identity));
  const built = row.built ? "У ZIP · " + (routes[row.built.route] || row.built.route) + " · " + row.built.source :
    row.recorded ? "Записано в базі, до ZIP не ввійшло" : "Не імпортовано";
  blocks.push(badge(built, row.built ? "built" : ""), make("p", row.help));
  if (row.approved_variant_count) blocks.push(make("p", "Спільний переклад схвалено для оригіналів: " + row.approved_variant_count));
  if (row.type === "quest" && row.built) blocks.push(make("p", row.built.text_sha256, "muted"));
  blocks.push(make("p", [mappingLabels[row.mapping_state], translationLabels[row.translation_state]].filter(Boolean).join(" · ")));
  blocks.push(make("p", row.review_queue ? "Черга: " + queueLabels[row.review_queue] : "У черзі перевірки запису немає.", "muted"));
  const en = make("section");
  en.append(make("h3", "Англійський оригінал"));
  if (row.original_variants?.length) {
    for (const variant of row.original_variants) {
      en.append(make("p", variant.text, "original"));
      en.append(make("p", [variant.revision, variant.fingerprint].filter(Boolean).join(" · "), "muted"));
      if (variant.source_ids?.length) en.append(make("p", variant.source_ids.join(" · "), "muted"));
      for (const context of variant.contexts) {
        en.append(make("p", [variant.target_id, context.npc_id != null ? "NPC " + context.npc_id : "",
          context.npc_type, context.faction, context.voice, context.player_gender].filter(Boolean).join(" · "), "muted"));

      }
    }
  } else {
    en.append(...((row.originals.length ? row.originals : ["Перевірений оригінал недоступний."])
      .map(text => make("p", text, "original"))));
  }
  const uk = make("section");
  uk.append(make("h3", "Український переклад"));
  if (!row.candidates.length) uk.append(make("p", "Перекладу немає.", "muted"));
  for (const item of row.candidates) {
    const details = make("details", undefined, "candidate");
    details.open = row.type === "quest" || row.candidates.length === 1 || row.status === "conflict" ||
      row.built?.text_sha256 === item.sha256 || Boolean(item.validation && item.validation !== "agent_verified");
    details.append(make("summary", item.provider + " · " + item.review),
      make("pre", item.text),
      make("p", [item.reference, item.revision].filter(Boolean).join(" · "), "muted"),
      make("p", eligibilityHelp[item.eligibility] || eligibilityHelp.source_review));
    if (row.type === "quest" && row.built?.text_sha256 === item.sha256) {
      details.append(badge("У ZIP", "built"));
    }
    if (item.validation === "stale") details.append(make("p", "Оцінка агента застаріла.", "muted"));
    if (item.shared_bindings) details.append(make("p", "Спільний запис ClassicUA для Альянсу й Орди.", "muted"));
    if (item.checks) {
      const failed = Object.keys(item.checks).filter(key => !item.checks[key]);
      if (failed.length) details.append(make("p", "Зауваження агента: " +
        failed.map(key => checkLabels[key] || key).join(", "), "muted"));
    }
    uk.append(details);
  }
  const evidence = make("details");
  evidence.append(make("summary", "Контекст джерела"), make("pre", JSON.stringify(row.contexts, null, 2)));
  blocks.push(en);
  if (row.type === "quest") blocks.push(reviewControls(row));
  blocks.push(uk, evidence);
  if (row.problem && problems[row.problem]) blocks.push(make("p", problems[row.problem]));
  if (row.unverified_alternatives?.length) {
    blocks.push(make("p", "Є збіг за обробленим текстом Spoken. Потрібна перевірка оригіналу в грі."));
    for (const item of row.unverified_alternatives) {
      blocks.push(make("p", item.hash + " · " + (item.scope === "common" ? "спільний запис" : "запис цього NPC"), "muted"));
    }
  }
  if (row.type !== "quest") blocks.push(reviewControls(row));
  el("selected").replaceChildren(...blocks);
}

async function detail(id, button) {
  selected = id;
  const seq = ++detailSeq;
  el("selected").replaceChildren(make("p", "Завантажуємо деталі…", "muted"));
  for (const other of el("rows").querySelectorAll("button")) {
    other.setAttribute("aria-pressed", String(other === button));
    other.closest("tr").classList.toggle("current", other === button);
  }
  try {
    const row = await call("detail", {identity: id});
    if (seq !== detailSeq) return;
    renderDetail(row);
    if (button && matchMedia("(max-width: 70rem)").matches) {
      el("inspector-heading").tabIndex = -1;
      el("inspector-heading").focus();
    }
  } catch (error) {
    if (seq === detailSeq) el("selected").replaceChildren(make("p", errorMessage(error)));
  }
}

function renderResult(result) {
  const rows = [];
  for (const [key, name] of [[domain(), domainName()]]) {
    const v = result.summary[key];
    rows.push(make("p", `${name} · у ZIP ${v.included} з ${v.total} · без перекладу ${v.missing} · конфлікти кандидатів ${v.conflicts} · кілька перевірених оригіналів ${v.multiple_originals} · на перевірку ${v.pending_review}`));
  }
  const g = result.summary.gossip_archive_units;
  if (domain() === "gossip") rows.push(make("p", `Архів Gossip · пар NPC/хеш: ${g.npc_hash_pairs} · спільних реплік: ${g.common_hashes}`));
  rows.push(make("p", "Агент · придатних: " + result.agent.eligible + " · пропущено: " + result.agent.skipped));
  if (result.artifact) rows.push(make("p", result.artifact));
  rows.push(make("p", "SHA-256 " + result.sha256, "muted"));
  const reasons = make("ul");
  for (const entry of [...result.skipped, ...result.agent.reasons]) {
    reasons.append(make("li", (entry.id || entry.candidate_id) + " · " +
      (problems[entry.reason] || errors[entry.reason] || "Запис потребує перевірки.")));
  }
  if (reasons.childElementCount) rows.push(reasons);
  el("run-details").replaceChildren(...rows);
  el("run-summary").hidden = false;
  el("run-summary").open = true;
}

async function reimport(dryRun) {
  if (busy) return;
  busy = true;
  for (const id of ["preview", "reimport", "reset", "module"]) el(id).disabled = true;
  el("run-summary").hidden = true;
  el("operation-status").textContent = dryRun ? "Перевіряємо й збираємо пробний ZIP…" : "Переімпорт і збірка тривають…";
  try {
    const result = await call("reimport", {reset: el("reset").checked, dry_run: dryRun, confirm: !dryRun});
    el("operation-status").textContent = dryRun ? "Попередня збірка готова. Поточні записи й ZIP збережено." : "Нову локальну збірку створено.";
    renderResult(result);
    if (!dryRun) {
      offset = 0;
      await list();
      if (selected) await detail(selected);
    }
  } catch (error) { el("operation-status").textContent = errorMessage(error); }
  finally {
    busy = false;
    for (const id of ["preview", "reimport", "reset", "module"]) el(id).disabled = false;
  }
}

let timer;
function resetList() { offset = 0; clearTimeout(timer); list(); }
el("query").addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(resetList, 275);
});
el("filters").addEventListener("submit", event => { event.preventDefault(); resetList(); });
for (const id of ["filter", "translation-status"]) el(id).addEventListener("change", resetList);
function refreshModuleControls() {
  el("reimport").textContent = "Переімпортувати " + domainName();
  el("inventory-heading").textContent = "Переклади " + domainName();
  for (const option of document.querySelectorAll('option[value="multiple_originals"]')) {
    option.hidden = domain() !== "quest";
  }
}
el("module").addEventListener("change", () => {
  detailSeq++;
  selected = null;
  el("filter").value = el("translation-status").value = "all";
  el("reset").checked = false;
  for (const id of ["metrics", "rows", "selected", "operation-status", "build-state", "match-count", "page"])
    el(id).replaceChildren();
  el("prev").disabled = el("next").disabled = true;
  el("run-summary").hidden = true;
  refreshModuleControls();
  resetList();
});
refreshModuleControls();
el("prev").addEventListener("click", () => { offset = Math.max(0, offset - pageSize); list(); });
el("next").addEventListener("click", () => { offset += pageSize; list(); });
el("preview").addEventListener("click", () => reimport(true));
el("reimport").addEventListener("click", () => {
  el("confirm").returnValue = "";
  el("confirm-text").textContent = el("reset").checked ?
    "Після успішної збірки тестові рішення та імпорти вибраного модуля буде замінено свіжим набором. Знімки джерел збережуться." :
    "Оновити імпорти вибраного модуля та зібрати новий приватний ZIP зі збереженням чинних рішень?";
  el("confirm").showModal();
});
el("confirm").addEventListener("close", () => {
  if (el("confirm").returnValue === "commit") reimport(false);
});
whileLoading(async () => {
  const response = await fetch("/api/bootstrap", {cache: "no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "manager_request_failed");
  csrf = data.csrf_token;
  await list();
}).catch(error => { el("list-message").textContent = errorMessage(error); });

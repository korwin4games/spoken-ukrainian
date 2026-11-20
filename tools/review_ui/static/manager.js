"use strict";

const el = id => document.getElementById(id);
const number = new Intl.NumberFormat("uk");
const errors = {
  manager_confirmation_required: "Підтвердіть переімпорт.",
  manager_reimport_already_running: "Інший переімпорт уже триває. Дочекайтеся його завершення.",
  manager_state_changed_retry_reimport: "Дані змінилися або база зайнята. Оновіть список і повторіть дію.",
  no_unambiguous_quest_imports_for_local_test_pack: "Для збірки бракує однозначних перекладів квестів.",
  manager_reimport_timed_out_check_build: "Час очікування минув. Оновіть список, щоб перевірити стан збірки.",
  manager_reimport_worker_unavailable: "Не вдалося запустити збірку. Перезапустіть локальний менеджер.",
  manager_reimport_worker_terminated: "Збірку перервано. Оновіть список, перевірте стан ZIP і повторіть.",
  manager_reimport_worker_empty_response: "Збірка не повернула результат. Перевірте стан ZIP і повторіть через CLI.",
  manager_reimport_worker_invalid_response: "Не вдалося прочитати результат збірки. Повторіть через CLI.",
  manager_reimport_failed: "Не вдалося завершити переімпорт. Запустіть збірку через CLI, щоб побачити причину.",
  manager_classicua_checkout_invalid: "Потрібна чиста копія ClassicUA на закріпленій ревізії.",
  manager_spoken_checkout_invalid: "Потрібна чиста копія Spoken на закріпленій ревізії.",
  manager_install_invalid_wow_path: "Введіть повний шлях до папки World of Warcraft (без _forever_).",
  manager_install_windows_path_on_non_windows: "Windows-шлях можна використовувати лише якщо Translation Manager запущено на Windows.",
  manager_install_addons_directory_missing: "Не знайдено папку _forever_\\Interface\\AddOns. Перевірте WoW path.",
  manager_install_unsafe_wow_path: "Шлях гри містить небезпечне посилання або перенаправлення.",
  manager_install_module_not_built: "Спершу натисніть «Створити модуль», щоб отримати ZIP.",
  manager_install_archive_outdated: "ZIP змінився або застарів. Створіть модуль повторно.",
  manager_install_invalid_archive: "ZIP не пройшов перевірку цілісності. Створіть модуль повторно.",
  manager_install_dependencies_missing: "Не знайдено потрібного аддона Spoken / Spoken_Quests у папці AddOns.",
  manager_install_legacy_addon: "Виявлено старий Spoken_Quests_UA. Перемістіть його з AddOns перед встановленням.",
  manager_install_rollback_incomplete: "Помилка встановлення: відновлення не завершено. Перевірте резервні копії вручну.",
  manager_install_failed: "Не вдалося встановити модуль. Перевірте доступ до папки гри та журнал термінала.",
};
let csrf, offset = 0, selected = null, listSeq = 0, detailSeq = 0, busy = false;
let readyCount = 0;
const loading = new Map();
const recentLists = new Map();
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
  manager_invalid_translation_format: "Введіть непорожній текст до 60 000 символів без NUL.",
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

function stopLoading(lane) {
  loading.delete(lane);
  el("loading-bar").hidden = loading.size === 0;
}

async function whileLoading(work, lane = Symbol()) {
  const request = Symbol();
  loading.set(lane, request);
  el("loading-bar").hidden = false;
  try {
    return await work();
  } finally {
    if (loading.get(lane) === request) stopLoading(lane);
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
    if (!["list", "detail", "install"].includes(action) && !payload.dry_run) recentLists.clear();
    return result;
  }, action);
}

function metrics(summary, build) {
  const q = summary[domain()];
    const cards = [
      ["Імпортовано", q.quest_imported ?? 0],
      ["Готові до імпорту", q.ready ?? 0],
      ["Проблемні", q.quest_problem ?? 0],
    ];
    el("metrics").className = "metrics quest-summary";
    el("metrics").replaceChildren(...cards.map(([name, value]) => {
      const card = make("div", undefined, "metric");
      card.append(make("span", name), make("strong", number.format(value)));
      return card;
    }));
    el("build-state").textContent = build ?
      "Останній " + domainName() + " ZIP: " + build.built_at + " UTC" :
      domainName() + " ZIP ще не зібрано.";
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
    const gossip = item.type === "gossip";
    const npcID = gossip ? String(item.npc_id ?? parts[1]) : "—";
    const id = gossip ? String(item.english_hash ?? parts[2]) : parts[1] ?? item.id;
    tr.append(make("td", gossip ? "Gossip" : "Quest"),
      make("td", npcID), make("td", id));
    tr.appendChild(make("td")).append(name);
    const status = item.ready_to_import ? "Готовий до імпорту" : item.built ? "Імпортовано" : "Проблемний";
    tr.appendChild(make("td")).append(badge(status, item.built && !item.ready_to_import ? "built" : ""));
    tr.appendChild(make("td")).append(make("span", item.needs_choice ? "Потрібен вибір" :
      item.status === "invalid" || item.status === "stale" ? "Перевірте контекст" : ""));
    tr.appendChild(make("td"));
    return tr;
  });
  el("rows").replaceChildren(...rows);
  readyCount = Number(data.summary[domain()]?.ready || 0);
  el("reimport").disabled = busy || (domain() === "quest" && readyCount === 0);
  el("list-message").hidden = rows.length > 0;
  el("list-message").textContent = rows.length ? "" : "За цими фільтрами записів немає.";
  el("match-count").textContent = number.format(data.total) + " записів";
  el("page").textContent = data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} з ${data.total}` : "0 записів";
  el("prev").disabled = offset === 0;
  el("next").disabled = offset + pageSize >= data.total;
}

async function list(restore = false) {
  const seq = ++listSeq;
  const module = el("module").value;
  const payload = {
    query: el("query").value,
    filter_by: el("quest-filter").value, offset, limit: pageSize,
  };
  const key = JSON.stringify(payload);
  const previous = recentLists.get(module);
  if (restore && previous?.key === key) renderList(previous.result);
  el("list-message").hidden = false;
  el("list-message").textContent = "Оновлюємо список…";
  try {
    const result = await call("list", payload);
    if (seq === listSeq) {
      recentLists.set(module, {key, result});
      renderList(result);
    }
  } catch (error) {
    if (seq === listSeq) el("list-message").textContent = errorMessage(error);
  }
}

function simpleEditor(row) {
  const panel = make("section");
  panel.className = "quest-editor";
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
    message.textContent = "Зберігаємо переклад…";
    for (const id of ["reimport", "module", "install", "wow-path"]) el(id).disabled = true;
    try {
      const result = await call(action, {...data, identity: row.id,
        binding: row.review_binding, confirm: true});
      el("run-summary").hidden = true;
      if (result.build !== "review_saved") throw new Error("manager_reimport_worker_invalid_response");
      el("operation-status").textContent = "Збережено. Готовий до імпорту — натисніть «Створити модуль».";
      await list();
      if (selected === row.id) await detail(row.id);
    } catch (error) {
      message.textContent = errorMessage(error);
    } finally {
      busy = false;
      for (const id of ["reimport", "module", "install", "wow-path"]) el(id).disabled = false;
      el("reimport").disabled = domain() === "quest" && readyCount === 0;
    }
  };
  panel.append(make("h3", options.size > 1 ? "Оберіть переклад" :
    options.size === 1 ? "Доступний переклад" : "Перекладу немає"));
  const field = make("textarea");
  field.rows = 7;
  field.maxLength = 60000;
  field.setAttribute("aria-label", "Український переклад");
  field.placeholder = "Введіть або відредагуйте український переклад…";
  let select = null;
  if (options.size) {
    select = make("select");
    select.setAttribute("aria-label", "Оберіть український переклад");
    for (const candidate of options.values()) {
      const item = make("option", [candidate.provider, candidate.reference, candidate.text.slice(0, 100)]
        .filter(Boolean).join(" · "));
      item.value = candidate.sha256;
      select.append(item);
    }
    const first = options.keys().next().value;
    const initial = row.selected_sha256 && options.has(row.selected_sha256) ?
      row.selected_sha256 : row.built?.text_sha256 && options.has(row.built.text_sha256) ?
      row.built.text_sha256 : first;
    select.value = initial;
    const useCandidate = () => {
      const chosen = options.get(select.value);
      if (chosen) field.value = chosen.text;
    };
    select.addEventListener("change", useCandidate);
    if (row.type === "quest" || row.selected_sha256 || options.size === 1) useCandidate();
    else select.selectedIndex = -1;
    panel.append(select);
  }
  const save = make("button", "Зберегти");
  save.type = "button";
  save.disabled = !editable;
  save.addEventListener("click", () => {
    const text = field.value;
    if (!text.trim()) return;
    const chosen = select && options.get(select.value);
    if (chosen && chosen.text === text) {
      // Preserve the selected candidate's source when its text is untouched.
      run("choose_" + row.type, {candidate: chosen.sha256});
    } else {
      // Any edited/pasted text is the user's manual translation.
      run("save_" + row.type, {text});
    }
  });
  const codex = make("button", "Скопіювати запит для Codex");
  codex.type = "button";
  codex.addEventListener("click", async () => {
    const prompt = "Translate these WoW: Forever " + row.type + " texts to natural Ukrainian. " +
      "Preserve all placeholders, including $N, $C, $R, $B and both branches of $G. " +
      "One Ukrainian translation must work for all verified variants. " +
      (row.npc_id ? "NPC " + row.npc_id + " " + row.label + ". " : "") +
      "Return only the translation.\n\n" + row.originals.join("\n\n---\n\n");
    try {
      await navigator.clipboard.writeText(prompt);
      message.textContent = "Запит скопійовано. Вставте в Codex, а переклад — у поле.";
    } catch (_) {
      message.textContent = "Не вдалося скопіювати. Перевірте доступ до буфера обміну.";
    }
  });
  const actions = make("div", undefined, "quest-editor-actions");
  actions.append(save, codex);
  panel.append(make("h3", "Український переклад"), field, actions);
  if (!editable) panel.append(make("p", "Немає перевіреного англійського оригіналу для цього квесту."));
  return panel;
}

function renderDetail(row) {
  const english = make("section");
  english.append(make("h3", "Англійський оригінал"));
  for (const text of row.originals) english.append(make("p", text, "original"));
  if (row.original_variants?.length) {
    const context = make("details");
    context.append(make("summary", "Варіанти оригіналу"));
    for (const variant of row.original_variants) {
      context.append(make("p", variant.target_id), make("pre", JSON.stringify(variant.contexts, null, 2)));
    }
    english.append(context);
  }
  const status = row.ready_to_import ? "Готовий до імпорту" : row.built ? "У ZIP" :
    row.needs_choice ? "Проблемний · оберіть переклад" : "Проблемний";
  const blocks = [make("h3", row.label), make("p", row.npc_id ? "NPC " + row.npc_id + " · " + row.id : row.id, "muted"),
    badge(status, row.built && !row.ready_to_import ? "built" : ""), english, simpleEditor(row)];
  if (row.contexts?.length) {
    const context = make("details");
    context.append(make("summary", "Контекст"), make("pre", JSON.stringify(row.contexts, null, 2)));
    blocks.push(context);
  }
  if (row.unverified_alternatives?.length) {
    const evidence = make("details");
    evidence.append(make("summary", "Кандидати з аудиту · потребують перевірки"));
    for (const item of row.unverified_alternatives) {
      if (item.english) evidence.append(make("p", item.english, "original"));
      if (item.ukrainian) evidence.append(make("p", item.ukrainian));
      evidence.append(make("p", [item.kind, item.reference, item.scope, item.hash].filter(Boolean).join(" · "), "muted"));
    }
    blocks.push(evidence);
  }
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
  const q = result.summary[domain()];
  el("run-details").replaceChildren(make("p", result.module),
    make("p", "Імпортовано " + number.format(q.quest_imported ?? q.included) +
      " · Готові " + number.format(q.ready ?? 0) + " · Проблемні " + number.format(q.quest_problem ?? 0)),
    make("p", result.artifact, "muted"), make("p", "SHA-256 " + result.sha256, "muted"));
  el("run-summary").hidden = false;
  el("run-summary").open = true;
}

async function reimport() {
  if (busy) return;
  busy = true;
  const module = el("module").value;
  for (const id of ["reimport", "module", "install", "wow-path"]) el(id).disabled = true;
  el("run-summary").hidden = true;
  el("install-status").textContent = "";
  el("operation-status").textContent = "Створюємо архів модуля…";
  try {
    const result = await call("import_ready", {module, confirm: true});
    el("operation-status").textContent = "Модуль створено.";
    renderResult(result);
    await list();
    if (selected) await detail(selected);
  } catch (error) { el("operation-status").textContent = errorMessage(error); }
  finally {
    busy = false;
    for (const id of ["reimport", "module", "install", "wow-path"]) el(id).disabled = false;
    el("reimport").disabled = domain() === "quest" && readyCount === 0;
  }
}

async function installModule() {
  if (busy) return;
  busy = true;
  const module = el("module").value;
  const wow_path = el("wow-path").value;
  for (const id of ["reimport", "module", "install", "wow-path"])
    el(id).disabled = true;
  el("install-status").textContent = "Створюємо модуль та встановлюємо аддон…";
  try {
    const result = await call("install", {module, wow_path});
    recentLists.delete(module);
    if (result.build_result) renderResult(result.build_result);
    await list();
    if (selected) await detail(selected);
    const replaced = result.replaced.length ?
      " Попередні папки: " + result.replaced.join(", ") + "." : "";
    const backup = result.backup ?
      " Резервна копія: " + result.backup + "." : "";
    el("install-status").textContent = "Встановлено: " + result.installed.join(", ") +
      ". Каталог: " + result.addons + "." + replaced + backup +
      " Перезапустіть WoW: Forever, щоб застосувати зміни.";
  } catch (error) {
    el("install-status").textContent = errorMessage(error);
  } finally {
    busy = false;
    for (const id of ["reimport", "module", "install", "wow-path"])
      el(id).disabled = false;
    el("reimport").disabled = domain() === "quest" && readyCount === 0;
  }
}

let timer;
function resetList() { offset = 0; clearTimeout(timer); list(); }
el("query").addEventListener("input", () => {
  listSeq++;
  stopLoading("list");
  clearTimeout(timer);
  timer = setTimeout(resetList, 275);
});
el("filters").addEventListener("submit", event => { event.preventDefault(); resetList(); });
el("quest-filter").addEventListener("change", resetList);
function refreshModuleControls() {
  el("inventory-heading").textContent = "Переклади " + domainName();
  el("operation-heading").textContent = "Створення модуля " + domainName();
  el("reimport").textContent = "Створити модуль";
}
el("module").addEventListener("change", () => {
  if (busy) return;
  detailSeq++;
  stopLoading("detail");
  selected = null;
  el("quest-filter").value = "all";
  readyCount = 0;
  for (const id of ["metrics", "rows", "selected", "operation-status", "install-status", "build-state", "match-count", "page"])
    el(id).replaceChildren();
  el("install-status").textContent = "";
  el("prev").disabled = el("next").disabled = true;
  el("run-summary").hidden = true;
  refreshModuleControls();
  offset = 0;
  clearTimeout(timer);
  list(true);
});
refreshModuleControls();
el("prev").addEventListener("click", () => { offset = Math.max(0, offset - pageSize); list(); });
el("next").addEventListener("click", () => { offset += pageSize; list(); });
el("install").addEventListener("click", installModule);
el("reimport").addEventListener("click", reimport);
whileLoading(async () => {
  const response = await fetch("/api/bootstrap", {cache: "no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "manager_request_failed");
  csrf = data.csrf_token;
  await list();
}).catch(error => { el("list-message").textContent = errorMessage(error); });

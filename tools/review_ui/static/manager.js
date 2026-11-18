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
  manager_reimport_failed: "Переімпорт завершився помилкою. Перевірте закріплені джерела або повторіть через CLI.",
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
function errorMessage(error) { return errors[error.message] || "Перевірте локальні джерела й повторіть: " + error.message; }

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
  const selectedKind = el("kind").value;
  const tally = key => selectedKind === "all" ? summary.quest[key] + summary.gossip[key] : summary[selectedKind][key];
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
  const prefix = build ? "Останній дійсний ZIP · " + build.built_at + " UTC" : "Дійсної локальної збірки ще немає.";
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
    statuses.append(badge(translationLabels[item.translation_state] || labels[item.status], item.status));
    if (["conflict", "multiple_originals"].includes(item.status) && item.translation_state) {
      statuses.append(make("div", labels[item.status]));
    }
    if (item.mapping_state) statuses.append(make("div", mappingLabels[item.mapping_state], "muted"));
    const problem = item.status !== "ready" || item.agent_warning;
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
      query: el("query").value, kind: el("kind").value, filter_by: el("filter").value,
      status: el("translation-status").value, offset, limit: pageSize,
    });
    if (seq === listSeq) renderList(result);
  } catch (error) {
    if (seq === listSeq) el("list-message").textContent = errorMessage(error);
  }
}

function renderDetail(row) {
  const title = make("h3", row.label);
  const blocks = [title, make("p", row.id, "muted")];
  const identity = row.type === "quest" ?
    "Квест " + row.quest_id + " · етап " + row.event : "NPC " + (row.npc_id ?? "—");
  blocks.push(make("p", identity));
  const built = row.built ? "У ZIP · " + (routes[row.built.route] || row.built.route) + " · " + row.built.source :
    row.recorded ? "Записано в базі, до ZIP не ввійшло" : "Не імпортовано";
  blocks.push(badge(built, row.built ? "built" : ""), make("p", row.help));
  blocks.push(make("p", [mappingLabels[row.mapping_state], translationLabels[row.translation_state]].filter(Boolean).join(" · ")));
  blocks.push(make("p", row.review_queue ? "Черга: " + queueLabels[row.review_queue] : "У черзі перевірки запису немає.", "muted"));
  const en = make("section");
  en.append(make("h3", "Англійський оригінал"));
  if (row.original_variants?.length) {
    for (const variant of row.original_variants) {
      en.append(make("p", variant.text, "original"));
      for (const context of variant.contexts) {
        en.append(make("p", [variant.target_id, context.npc_id != null ? "NPC " + context.npc_id : "",
          context.npc_type, context.faction, context.voice, context.player_gender].filter(Boolean).join(" · "), "muted"));
        for (const faction of variant.review_factions) {
          const link = make("a", "Перевірити цей варіант · " + (faction === "alliance" ? "Альянс" : "Орда"));
          const query = new URLSearchParams({target: variant.target_id, faction,
            wording: context.wording_sha256, context: context.index});
          link.href = "/advanced?" + query + "#mapping-context";
          en.append(make("p")).appendChild(link);
        }
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
    details.open = row.candidates.length === 1 || row.status === "conflict" ||
      row.built?.text_sha256 === item.sha256 || Boolean(item.validation && item.validation !== "agent_verified");
    details.append(make("summary", item.provider + " · " + item.review),
      make("pre", item.text),
      make("p", [item.reference, item.revision].filter(Boolean).join(" · "), "muted"));
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
  blocks.push(en, uk, evidence);
  if (row.problem) blocks.push(make("p", problems[row.problem] || row.problem));
  if (row.unverified_alternatives?.length) {
    blocks.push(make("p", "Є збіг за обробленим текстом Spoken. Потрібна перевірка оригіналу в грі."));
    for (const item of row.unverified_alternatives) {
      blocks.push(make("p", item.hash + " · " + (item.scope === "common" ? "спільний запис" : "запис цього NPC"), "muted"));
    }
  }
  const link = make("a", row.status === "ready" ? "Переглянути історію та джерела" : "Відкрити розширену перевірку");
  link.href = row.type === "quest" ? "/advanced#translation-candidates" : "/advanced#gossip-stats";
  blocks.push(make("p"));
  blocks.at(-1).append(link);
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
  for (const [key, name] of [["quest", "Quest"], ["gossip", "Gossip"]]) {
    const v = result.summary[key];
    rows.push(make("p", `${name} · у ZIP ${v.included} з ${v.total} · без перекладу ${v.missing} · конфлікти кандидатів ${v.conflicts} · кілька перевірених оригіналів ${v.multiple_originals} · на перевірку ${v.pending_review}`));
  }
  const g = result.summary.gossip_archive_units;
  rows.push(make("p", `Архів Gossip · пар NPC/хеш: ${g.npc_hash_pairs} · спільних реплік: ${g.common_hashes}`));
  rows.push(make("p", "Агент · придатних: " + result.agent.eligible + " · пропущено: " + result.agent.skipped));
  if (result.artifact) rows.push(make("p", result.artifact));
  rows.push(make("p", "SHA-256 " + result.sha256, "muted"));
  const reasons = make("ul");
  for (const entry of [...result.skipped, ...result.agent.reasons]) {
    reasons.append(make("li", (entry.id || entry.candidate_id) + " · " + entry.reason));
  }
  if (reasons.childElementCount) rows.push(reasons);
  el("run-details").replaceChildren(...rows);
  el("run-summary").hidden = false;
  el("run-summary").open = true;
}

async function reimport(dryRun) {
  if (busy) return;
  busy = true;
  for (const id of ["preview", "reimport", "reset"]) el(id).disabled = true;
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
    for (const id of ["preview", "reimport", "reset"]) el(id).disabled = false;
  }
}

let timer;
function resetList() { offset = 0; clearTimeout(timer); list(); }
el("query").addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(resetList, 275);
});
el("filters").addEventListener("submit", event => { event.preventDefault(); resetList(); });
for (const id of ["module", "filter", "kind", "translation-status"]) el(id).addEventListener("change", resetList);
el("prev").addEventListener("click", () => { offset = Math.max(0, offset - pageSize); list(); });
el("next").addEventListener("click", () => { offset += pageSize; list(); });
el("preview").addEventListener("click", () => reimport(true));
el("reimport").addEventListener("click", () => {
  el("confirm").returnValue = "";
  el("confirm-text").textContent = el("reset").checked ?
    "Після успішної збірки тестові рішення та імпорти Quest і Gossip буде замінено свіжим набором. Знімки джерел збережуться." :
    "Оновити імпорти Quest і Gossip та зібрати новий приватний ZIP зі збереженням чинних рішень?";
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

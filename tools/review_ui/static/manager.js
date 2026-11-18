"use strict";

const el = id => document.getElementById(id);
const number = new Intl.NumberFormat("uk");
const labels = {
  ready: "Готовий", missing: "Немає перекладу", review: "Потрібна перевірка",
  conflict: "Конфлікт", rejected: "Відхилено / відкладено", invalid: "Не пройшов перевірку", stale: "Застарів",
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
};
let csrf, offset = 0, selected = null, listSeq = 0, detailSeq = 0, busy = false;
const pageSize = 30;

function make(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function badge(text, state) { return make("span", text, "badge " + state); }
function errorMessage(error) { return errors[error.message] || "Перевірте локальні джерела й повторіть: " + error.message; }

async function call(action, payload) {
  const response = await fetch("/api/manager/" + action, {
    method: "POST", cache: "no-store",
    headers: {"Content-Type": "application/json", "X-Review-Token": csrf},
    body: JSON.stringify({module: el("module").value, ...payload}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.reason || result.error || "manager_request_failed");
  return result;
}

function metrics(summary, build) {
  const tally = key => summary.quest[key] + summary.gossip[key];
  const cells = [
    ["Усього записів", "total"], ["Імпортовано в ZIP", "included"], ["Не в ZIP", "not_included"],
    ["Конфлікти", "conflicts"], ["Без перекладу", "missing"], ["Готові до імпорту", "ready"],
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
    tr.appendChild(make("td")).append(badge(labels[item.status], item.status));
    const problem = item.status !== "ready";
    const flag = make("td", problem ? "⚑" : "—");
    flag.title = labels[item.status];
    if (problem) flag.setAttribute("aria-label", labels[item.status]);
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
  const en = make("section");
  en.append(make("h3", "Англійський оригінал"),
    ...((row.originals.length ? row.originals : ["Перевірений оригінал недоступний."])
      .map(text => make("p", text, "original"))));
  const uk = make("section");
  uk.append(make("h3", "Український переклад"));
  if (!row.candidates.length) uk.append(make("p", "Перекладу немає.", "muted"));
  for (const item of row.candidates) {
    const details = make("details", undefined, "candidate");
    details.open = row.candidates.length === 1 || row.status === "conflict" || row.built?.text_sha256 === item.sha256;
    details.append(make("summary", item.provider + " · " + item.review),
      make("pre", item.text),
      make("p", [item.reference, item.revision, item.validation].filter(Boolean).join(" · "), "muted"));
    if (item.checks) {
      const failed = Object.keys(item.checks).filter(key => !item.checks[key]);
      if (failed.length) details.append(make("p", "Потребує уваги: " + failed.join(", "), "muted"));
    }
    uk.append(details);
  }
  const evidence = make("details");
  evidence.append(make("summary", "Контекст джерела"), make("pre", JSON.stringify(row.contexts, null, 2)));
  blocks.push(en, uk, evidence);
  if (row.problem) blocks.push(make("p", "Причина: " + row.problem));
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
    rows.push(make("p", `${name} · у ZIP ${v.included} з ${v.total} · без перекладу ${v.missing} · конфлікти ${v.conflicts} · на перевірку ${v.pending_review}`));
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
fetch("/api/bootstrap", {cache: "no-store"}).then(response => response.json()).then(data => {
  csrf = data.csrf_token;
  list();
}).catch(error => { el("list-message").textContent = errorMessage(error); });

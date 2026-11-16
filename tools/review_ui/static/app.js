"use strict";

// Every dynamic value is assigned with textContent, never innerHTML.
// English/Ukrainian texts are displayed in memory and not cached or exported.
const ui = {
  faction: document.getElementById("faction"),
  limit: document.getElementById("limit"),
  stats: document.getElementById("stats"),
  queue: document.getElementById("queue-items"),
  queueCount: document.getElementById("queue-count"),
  sourceId: document.getElementById("source-id"),
  questMeta: document.getElementById("quest-meta"),
  status: document.getElementById("candidate-status"),
  uaText: document.getElementById("ua-text"),
  enText: document.getElementById("en-text"),
  sourceRef: document.getElementById("source-ref"),
  sourceHash: document.getElementById("source-hash"),
  targetId: document.getElementById("target-id"),
  targetHash: document.getElementById("target-hash"),
  targetRef: document.getElementById("target-ref"),
  targetBlob: document.getElementById("target-blob"),
  options: document.getElementById("target-options"),
  facts: document.getElementById("facts"),
  reviewer: document.getElementById("reviewer"),
  reason: document.getElementById("reason"),
  reject: document.getElementById("reject"),
  defer: document.getElementById("defer"),
  feedback: document.getElementById("feedback"),
  prev: document.getElementById("prev"),
  next: document.getElementById("next"),
  pageLabel: document.getElementById("page-label"),
  reload: document.getElementById("reload"),
};
const state = {
  csrf: null, offset: 0, limit: 12, faction: "horde",
  report: null, selectedSourceId: null, selectedTargetId: null,
  loading: false,
};
function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function setText(node, value) {
  node.textContent = value === undefined || value === null ? "—" : String(value);
}
function selectCurrent() {
  if (!state.report) return null;
  return state.report.items.find(function(item) {
    return item.source_id === state.selectedSourceId;
  }) || null;
}
function selectedOption() {
  const item = selectCurrent();
  if (!item) return null;
  return item.target_options.find(function(o) {
    return o.target_id === state.selectedTargetId;
  }) || null;
}
function renderQueue() {
  ui.queue.replaceChildren();
  const items = state.report ? state.report.items : [];
  if (!items.length) {
    ui.queue.appendChild(make("p", "muted", "На цій сторінці немає кандидатів."));
    return;
  }
  items.forEach(function(item) {
    const id = item.source_id;
    const selected = id === state.selectedSourceId;
    const button = make("button", "queue-item" + (selected ? " selected" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", String(selected));
    button.appendChild(make("div", "queue-id", id));
    button.appendChild(make("div", "queue-meta",
      item.target_options.length + " варіант(ів) · " + item.candidate_reason));
    const deferred = item.target_options.some(function(o) {
      return o.manual_decision === "deferred";
    });
    button.appendChild(make("span", "queue-pill", deferred ? "Deferred" : "Pending"));
    button.addEventListener("click", function() {
      state.selectedSourceId = id;
      state.selectedTargetId = item.target_options[0]?.target_id || null;
      renderQueue();
      renderDetail();
    });
    ui.queue.appendChild(button);
  });
}
function renderDetail() {
  const item = selectCurrent();
  const option = selectedOption();
  ui.reject.disabled = state.loading || !option;
  ui.defer.disabled = state.loading || !option;
  if (!item || !option) {
    setText(ui.sourceId, "Оберіть запис");
    setText(ui.questMeta, "З черги ліворуч");
    setText(ui.uaText, "Немає вибраного кандидата.");
    setText(ui.enText, "Немає вибраного кандидата.");
    [ui.sourceRef, ui.sourceHash, ui.targetId, ui.targetHash,
      ui.targetRef, ui.targetBlob].forEach(function(x) {
      setText(x, "—");
    });
    ui.options.replaceChildren();
    ui.facts.replaceChildren();
    return;
  }
  setText(ui.sourceId, item.source_id);
  const parts = item.source_id.split(":");
  setText(ui.questMeta, "QUEST #" + (parts[2] || "?") +
      " / " + (parts[3] || "?").toUpperCase() +
      " / " + (parts[1] || "?").toUpperCase());
  setText(ui.uaText, item.ukrainian_text);
  setText(ui.sourceRef, item.source_reference);
  setText(ui.sourceHash, item.field_sha256);
  setText(ui.targetId, option.target_id);
  setText(ui.targetHash, option.target_context_sha256);
  setText(ui.targetRef, option.target_reference);
  setText(ui.targetBlob, option.target_blob_sha256);
  setText(ui.enText, option.english_verified
    ? option.english_original : "Оригінальний English-текст не підтверджений або неоднозначний.");
  ui.enText.classList.toggle("unverified", !option.english_verified);
  setText(ui.status, option.manual_decision === "deferred"
    ? "Відкладено" : "Потребує перевірки");
  ui.options.replaceChildren();
  item.target_options.forEach(function(o) {
    const selected = o.target_id === state.selectedTargetId;
    const button = make("button", "target-chip" + (selected ? " selected" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", String(selected));
    button.appendChild(make("strong", "", o.target_id));
    button.appendChild(make("small", "",
      o.manual_decision === "deferred" ? "Deferred" : "Pending"));
    button.addEventListener("click", function() {
      state.selectedTargetId = o.target_id;
      renderDetail();
    });
    ui.options.appendChild(button);
  });
  ui.facts.replaceChildren();
  const keys = [
    ["npc_id", "NPC"], ["npc_type", "NPC type"], ["voice", "Voice"],
    ["faction", "Faction"], ["player_gender", "Gender"],
    ["source", "Event"], ["quest_id", "Quest ID"], ["wording_sha256", "English SHA"],
  ];
  (option.variants || []).forEach(function(v, i) {
    const heading = make("span", "fact", "Контекст #" + (i + 1));
    ui.facts.appendChild(heading);
    keys.forEach(function(k) {
      if (v[k[0]] === undefined || v[k[0]] === null) return;
      const fact = make("span", "fact");
      fact.appendChild(make("span", "", k[1]));
      fact.appendChild(make("b", "", v[k[0]]));
      ui.facts.appendChild(fact);
    });
  });
}
function render() {
  if (!state.report) return;
  const summary = state.report.summary;
  setText(ui.stats, "У черзі: " + summary.queued_source_units.toLocaleString("uk-UA") +
    " · AI виключено: " + summary.ai_marked_excluded_from_queue.toLocaleString("uk-UA") +
    " · Identity approvals створено: 0");
  setText(ui.queueCount, summary.page_count + " цього разу");
  setText(ui.pageLabel, (state.offset + 1) + "–" +
    (state.offset + summary.page_count) + " з " + summary.queued_source_units);
  ui.prev.disabled = state.loading || state.offset === 0;
  ui.next.disabled = state.loading || !summary.has_more;
  if (!state.report.items.some(function(x) {
    return x.source_id === state.selectedSourceId;
  })) {
    state.selectedSourceId = state.report.items[0]?.source_id || null;
    state.selectedTargetId = state.report.items[0]?.target_options[0]?.target_id || null;
  }
  // A rejected target vanishes while its source may still have alternatives.
  // Do not leave the details panel blank when another valid voice exists.
  const current = selectCurrent();
  if (current && !current.target_options.some(function(o) {
    return o.target_id === state.selectedTargetId;
  })) {
    state.selectedTargetId = current.target_options[0]?.target_id || null;
  }
  renderQueue();
  renderDetail();
}
async function loadPage() {
  if (state.loading) return;
  state.loading = true;
  ui.prev.disabled = true;
  ui.next.disabled = true;
  ui.reload.disabled = true;
  setText(ui.feedback, "");
  try {
    const query = new URLSearchParams({
      faction: state.faction, offset: String(state.offset), limit: String(state.limit),
    });
    const response = await fetch("/api/queue?" + query.toString(), {cache: "no-store"});
    if (!response.ok) throw new Error("queue");
    state.report = await response.json();
    render();
  } catch (_) {
    setText(ui.feedback, "Помилка отримання черги. Перевірте pinned-репозиторії та рішення.");
  } finally {
    state.loading = false;
    ui.reload.disabled = false;
    if (state.report) render();
  }
}
async function sendDecision(decision) {
  const item = selectCurrent();
  const option = selectedOption();
  if (!item || !option || state.loading) return;
  const reviewer = ui.reviewer.value.trim();
  if (!reviewer) {
    setText(ui.feedback, "Вкажіть reviewer ID перед збереженням.");
    ui.reviewer.focus();
    return;
  }
  if (decision === "rejected" &&
      !window.confirm("Відхилити саме цю пару source ↔ target? Рішення збережеться локально.")) {
    return;
  }
  state.loading = true;
  ui.reject.disabled = true;
  ui.defer.disabled = true;
  const payload = {
    source_id: item.source_id, target_id: option.target_id,
    decision: decision, reason: ui.reason.value, reviewer: reviewer,
  };
  try {
    const response = await fetch("/api/decisions", {
      method: "POST", headers: {
        "Content-Type": "application/json", "X-Review-Token": state.csrf,
      }, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("decision");
    state.loading = false;
    await loadPage();
    setText(ui.feedback, "Збережено: " + decision +
      " (лише рішення reviewer, без approval).");
  } catch (_) {
    setText(ui.feedback, "Не збережено: повторна пара, застарілий контекст або некоректне рішення.");
  } finally {
    state.loading = false;
    if (state.report) render();
  }
}
ui.faction.addEventListener("change", function() {
  state.faction = ui.faction.value;
  state.offset = 0; state.selectedSourceId = null; state.selectedTargetId = null;
  loadPage();
});
ui.limit.addEventListener("change", function() {
  state.limit = Number(ui.limit.value);
  state.offset = 0; state.selectedSourceId = null; state.selectedTargetId = null;
  loadPage();
});
ui.prev.addEventListener("click", function() {
  state.offset = Math.max(0, state.offset - state.limit);
  state.selectedSourceId = null; state.selectedTargetId = null;
  loadPage();
});
ui.next.addEventListener("click", function() {
  state.offset += state.limit;
  state.selectedSourceId = null; state.selectedTargetId = null;
  loadPage();
});
ui.reload.addEventListener("click", loadPage);
ui.reject.addEventListener("click", function() { sendDecision("rejected"); });
ui.defer.addEventListener("click", function() { sendDecision("deferred"); });
(async function initialize() {
  try {
    const response = await fetch("/api/bootstrap", {cache: "no-store"});
    if (!response.ok) throw new Error("bootstrap");
    const data = await response.json();
    state.csrf = data.csrf_token;
    await loadPage();
  } catch (_) {
    setText(ui.queue, "Не вдалося підключитися до локального Review UI.");
  }
})();

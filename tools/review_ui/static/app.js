"use strict";

// Every dynamic value is assigned with textContent, never innerHTML.
// Translation versions persist only through explicit local review actions.
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
    document.getElementById("mapping-context").replaceChildren();
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
  const contextSelect = document.getElementById("mapping-context");
  contextSelect.replaceChildren();
  (option.variants || []).forEach((variant, index) => {
    const entry = make("option", "", "Контекст #" + (index + 1) +
      " · NPC " + (variant.npc_id ?? "—") + " · Voice " + (variant.voice ?? "—") +
      " · Gender " + (variant.player_gender ?? "—"));
    entry.value = String(index);
    contextSelect.appendChild(entry);
  });
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
    " · Схвалено identity: " + summary.human_stage3_approved_joins);
  const approvedPanel = document.getElementById("approved-mappings");
  approvedPanel.replaceChildren();
  const approvedMappings = state.report.approved_mappings || [];
  if (!approvedMappings.length) {
    approvedPanel.appendChild(make("span", "small", "Для цієї фракції поки немає схвалених mappings."));
  } else {
    approvedMappings.forEach(row => {
      approvedPanel.appendChild(make("span", "approved-item",
        "✓ " + row.source_id + " → " + row.target_id + " · Approved"));
    });
  }
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

// Mapping proof input is never populated from candidate hints or invented IDs.
async function reviewPost(route, payload, notify = true) {
  const response = await fetch(route, {method: "POST", headers: {
    "Content-Type": "application/json", "X-Review-Token": state.csrf,
  }, body: JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.reason || result.error || "evidence_or_storage_conflict");
  // Read-only statistics are recomputed from authoritative SQLite imports.
  if (notify) {
    window.dispatchEvent(new Event("spoken-import-stats-refresh"));
    window.dispatchEvent(new Event("spoken-gossip-machine-refresh"));
  }
  return result;
}
function resetMappingAttestations() {
  document.getElementById("mapping-inspected").checked = false;
  document.getElementById("mapping-independent").checked = false;
}
ui.queue.addEventListener("click", resetMappingAttestations);
ui.options.addEventListener("click", resetMappingAttestations);
document.getElementById("mapping-context").addEventListener("change", resetMappingAttestations);
document.getElementById("mapping-approve").addEventListener("click", async function() {
  try {
    const item = selectCurrent(), option = selectedOption();
    const evidenceReviewer = document.getElementById("mapping-evidence-reviewer").value.trim();
    const mappingReviewer = document.getElementById("mapping-reviewer").value.trim();
    const inspected = document.getElementById("mapping-inspected").checked;
    const independent = document.getElementById("mapping-independent").checked;
    const contextIndex = Number(document.getElementById("mapping-context").value);
    const facts = option?.variants?.[contextIndex];
    const required = ["npc_id", "npc_type", "voice", "faction",
      "player_gender", "wording_sha256", "source", "quest_id"];
    if (!item || !option || !option.english_verified || !facts ||
        !required.every(key => Object.hasOwn(facts, key)) ||
        !evidenceReviewer || !mappingReviewer ||
        evidenceReviewer === mappingReviewer || !inspected || !independent) {
      throw new Error("independent_inspection_required");
    }
    const request = {
      schema_version: 1, source_id: item.source_id, target_id: option.target_id,
      mapping_reviewer: mappingReviewer,
      proof: {
        source_context_sha256: item.source_context_sha256,
        target_context_sha256: option.target_context_sha256,
        facts: Object.fromEntries(required.map(key => [key, facts[key]])),
        source_reference: item.source_reference,
        source_blob_sha256: item.source_blob_sha256,
        target_reference: option.target_reference,
        target_blob_sha256: option.target_blob_sha256,
        evidence_reviewer: evidenceReviewer,
        greeting: false,
      },
    };
    if (!window.confirm("Підтвердити, що два незалежні реальні reviewer перевірили цю точну пару?")) return;
    const approvedSource = item.source_id, approvedTarget = option.target_id;
    await reviewPost("/api/mapping/approve", request);
    resetMappingAttestations();
    await loadPage();
    const approved = (state.report?.approved_mappings || []).some(row =>
      row.source_id === approvedSource && row.target_id === approvedTarget);
    setText(ui.feedback, approved
      ? "✓ Approved: " + approvedSource + " → " + approvedTarget +
        ". Запис переміщено до Approved mappings. Переклад ще не схвалено."
      : "Approval записано сервером, але чергу не вдалося підтвердити. Оновіть сторінку.");
    await loadTranslations();
  } catch (error) {
    setText(ui.feedback, "Mapping не схвалено: " + error.message +
      ". Перевірте термінал сервера та докази.");
  }
});
const translations = {rows: [], selected: null, busy: false, autoAllowed: false};
const t = id => document.getElementById("translation-" + id);
function renderTranslation() {
  const row = translations.rows.find(r => r.id === t("versions").value);
  translations.selected = row || null;
  t("text").value = row ? row.text : "";
  setText(t("english"), row?.english_original || "Перевірений поточний оригінал недоступний.");
  setText(t("provenance"), row ? JSON.stringify({
    source_id: row.source_id, target_id: row.target_id, version_id: row.id,
    status: row.status, imported: row.imported, editor: row.editor,
    original_sha256: row.original_sha256, text_sha256: row.text_sha256,
    base_sha256: row.base_sha256, provenance: row.provenance, decisions: row.decisions,
  }, null, 2) : "");
  ["text", "grammar", "ai", "rights"].forEach(k => {
    document.getElementById("check-" + k).checked = false;
  });
  updateTranslationButtons();
}
function updateTranslationButtons() {
  const row = translations.selected;
  ["edit", "approved", "rejected", "deferred"].forEach(k => {
    t(k).disabled = translations.busy || !row || !row.current;
  });
  t("auto-import").disabled = translations.busy || !translations.autoAllowed;
}
async function loadTranslations() {
  const response = await fetch("/api/translations", {cache: "no-store"});
  if (!response.ok) throw new Error("translation_evidence");
  const data = await response.json();
  const previous = t("versions").value;
  translations.rows = data.versions;
  translations.autoAllowed = (data.auto_approve_one_to_one || []).includes("classicua");
  t("versions").replaceChildren();
  data.versions.sort((a, b) => a.target_id.localeCompare(b.target_id) || b.number - a.number);
  data.versions.forEach(row => {
    const option = make("option", "", row.source_id + " → " + row.target_id + " / " +
      "#" + row.number + " / " + row.kind + " / " + row.id.slice(0, 10) + " / " + row.status + " / " +
      (row.imported ? "imported (inert)" : "not imported"));
    option.value = row.id;
    t("versions").appendChild(option);
  });
  if (data.versions.some(row => row.id === previous)) t("versions").value = previous;
  setText(t("candidates"), "Джерела: " + data.source_policy.join(" → ") +
    ". Автоапрув 1:1 (після підтвердженого mapping review): " +
    (data.auto_approve_one_to_one?.join(", ") || "вимкнено") +
    ". Поточних кандидатів після mapping review: " + data.current_candidates.length +
    ". Збережених версій: " + data.versions.length + ". " +
    (data.import_conflict ? "Конфлікт схвалених версій: імпорт заблоковано. " : "") +
    data.current_candidates.map(row => row.target_id + ": " +
      (row.stored_locally ? "локальне зберігання дозволене" : "store_locally=false; лише RAM")).join("; "));
  const preview = t("previews");
  preview.replaceChildren();
  data.current_candidates.forEach(row => {
    const detail = make("details");
    detail.appendChild(make("summary", "", row.source_id + " → " + row.target_id +
      (row.stored_locally ? " / кандидат" : " / RAM only")));
    detail.appendChild(make("pre", "", row.english_original));
    detail.appendChild(make("pre", "", row.text));
    detail.appendChild(make("pre", "", JSON.stringify(row.provenance, null, 2)));
    preview.appendChild(detail);
  });
  renderTranslation();
}
function renderImportReport(report) {
  const target = t("import-report");
  target.hidden = false;
  target.replaceChildren();
  target.appendChild(make("h3", "", "Підсумок імпорту · Spoken Ukrainian"));
  const table = make("table", "import-report-table");
  const header = make("thead");
  const headings = make("tr");
  ["Джерело", "Кандидатів", "Імпортовано / перекладено", "Із них машинні 1:1"].forEach(title =>
    headings.appendChild(make("th", "", title)));
  header.appendChild(headings);
  table.appendChild(header);
  const body = make("tbody");
  report.by_source.forEach(entry => {
    const row = make("tr");
    [entry.source, entry.candidate_translations, entry.imported_translations, entry.machine_provisional_imports || 0]
      .forEach(value => row.appendChild(make("td", "", String(value))));
    body.appendChild(row);
  });
  table.appendChild(body);
  target.appendChild(table);
  const totals = [
    ["Всього записів Spoken", report.total_spoken_records],
    ["Можливі 1:1 без підтвердження", report.unreviewed_one_to_one_candidates],
    ["Перевірені відповідності з перекладом", report.verified_source_to_target_bindings],
    ["Автоматично схвалено за цей запуск", report.auto_approved_now],
    ["Всього імпортовано", report.imported_total],
    ["Із них автоматичні 1:1 (ще без human mapping review)", report.machine_one_to_one_imported || 0],
    ["Залишилося без імпорту", report.untranslated_total],
    ["Покриття", report.coverage_percent + "%"],
  ];
  const summary = make("table", "import-report-table");
  const summaryBody = make("tbody");
  totals.forEach(([name, value]) => {
    const row = make("tr");
    row.appendChild(make("th", "", String(name)));
    row.appendChild(make("td", "", String(value)));
    summaryBody.appendChild(row);
  });
  summary.appendChild(summaryBody);
  target.appendChild(summary);
  target.appendChild(make("p", "muted",
    "Імпорт — тільки приватне локальне сховище build/. Машинні 1:1 є попередніми до human mapping review; нічого не записано в Git чи активний аддон."));
}

async function translationAction(action, payload) {
  if (translations.busy) return;
  translations.busy = true;
  updateTranslationButtons();
  try {
    const result = await reviewPost("/api/translations/" + action, payload);
    await loadTranslations();
    if (result.version_id) { t("versions").value = result.version_id; renderTranslation(); }
    if (result.report) renderImportReport(result.report);
    let message = action === "import"
      ? "Явний inert import: " + result.imported + "; changed=" + result.changed + ". Активації немає."
      : "Збережено локально: " + action + ". Імпорт — окрема дія.";
    if (action === "refresh") {
      message = "Збережено кандидатів. Автоматично схвалено 1:1: " +
        result.auto_approved + ". Збережено лише приватно, імпорт — окрема дія.";
    }
    if (action === "auto_import_one_to_one") {
      message = "Автоімпорт 1:1 завершено. Підтверджених автоапрувів за запуск: " +
        result.auto_approved + "; попередніх машинних 1:1: " + result.machine_imported +
        "; імпортовано загалом: " + result.imported +
        ". Таблиця нижче. Активації у WoW немає.";
    }
    if (action === "decide") {
      const reviewed = translations.rows.find(row => row.id === payload.identity);
      if (!reviewed || reviewed.status !== payload.decision) {
        message = "Рішення збережено, але список версій не підтвердив статус. Оновіть сторінку.";
      } else {
        message = "✓ " + reviewed.source_id + " → " + reviewed.target_id +
          ": " + reviewed.status.toUpperCase() + ". Імпорт — окрема дія.";
      }
    }
    setText(t("feedback"), message);
  } catch (error) {
    setText(t("feedback"), "Не збережено: " + error.message +
      ". Перевірте термінал сервера та актуальність доказів.");
  } finally { translations.busy = false; updateTranslationButtons(); }
}
t("versions").addEventListener("change", renderTranslation);
t("refresh").addEventListener("click", () => translationAction("refresh", {}));
t("import").addEventListener("click", () => translationAction("import", {}));
t("auto-import").addEventListener("click", () =>
  translationAction("auto_import_one_to_one", {source: "classicua"}));
t("edit").addEventListener("click", () => {
  if (translations.selected) translationAction("edit", {identity: translations.selected.id,
    text: t("text").value, reviewer: t("reviewer").value.trim()});
});
["approved", "rejected", "deferred"].forEach(decision => {
  t(decision).addEventListener("click", () => {
    const row = translations.selected;
    if (!row) return;
    if (t("text").value !== row.text) {
      setText(t("feedback"), "Спочатку збережіть відредагований текст як нову версію.");
      return;
    }
    const reviewer = t("reviewer").value.trim();
    if (!reviewer) {
      setText(t("feedback"), "Вкажіть Content reviewer перед збереженням рішення.");
      t("reviewer").focus();
      return;
    }
    const checks = {};
    ["text", "grammar", "ai", "rights"].forEach(k => {
      checks[k] = document.getElementById("check-" + k).checked;
    });
    if (decision === "approved") {
      const unchecked = Object.entries(checks).filter(([, checked]) => !checked)
        .map(([key]) => key);
      if (unchecked.length) {
        setText(t("feedback"), "Approve translation не виконано: перевірте всі 4 пункти " +
          "(text, grammar, ai, rights). Не позначайте їх без фактичної перевірки. " +
          "Не підтверджено: " + unchecked.join(", ") + ".");
        return;
      }
    }
    translationAction("decide", {identity: row.id, decision,
      reviewer, checks});
  });
});
loadTranslations().catch(() => setText(t("feedback"), "Не вдалося перевірити translation evidence."));


// Gossip Translation Review is independent of Quest Stage 3 mappings.
// All data is inserted via textContent; CSRF comes from the existing bootstrap.
(function() {
  const g = id => document.getElementById("gossip-" + id);
  const gs = {items: [], selectedGroup: null, selectedVersion: null,
              offset: 0, limit: 12, total: 0, busy: false};
  const checks = ["text", "grammar", "ai", "rights", "all_contexts"];
  const currentGroup = () => gs.items.find(x => x.group_id === gs.selectedGroup) || null;
  const currentVersion = () => currentGroup()?.versions.find(x => x.id === gs.selectedVersion) || null;

  function render() {
    const row = currentGroup();
    setText(g("stats"), "Унікальних реплік для перекладу: " + gs.total +
      " · 12 на сторінці");
    setText(g("page"), gs.total ?
      (gs.offset + 1) + "–" + (gs.offset + gs.items.length) + " / " + gs.total : "0");
    g("prev").disabled = gs.busy || gs.offset === 0;
    g("next").disabled = gs.busy || gs.offset + gs.items.length >= gs.total;
    g("items").replaceChildren();
    gs.items.forEach(item => {
      const button = make("button", "queue-item" +
        (gs.selectedGroup === item.group_id ? " selected" : ""));
      button.type = "button";
      button.appendChild(make("div", "queue-id", item.english.slice(0, 100)));
      button.appendChild(make("div", "queue-meta", item.occurrence_count +
        " NPC · версій: " + item.versions.length));
      const imported = item.versions.some(x => x.imported);
      button.appendChild(make("span", "queue-pill",
        imported ? "Imported" : item.versions.some(x => x.status === "approved")
          ? "Approved · not imported" : item.versions.length ? "Pending / reviewed" : "Untranslated"));
      button.addEventListener("click", () => {
        gs.selectedGroup = item.group_id;
        gs.selectedVersion = null;
        checks.forEach(k => { g("check-" + k).checked = false; });
        render();
      });
      g("items").appendChild(button);
    });
    setText(g("group"), row ? row.group_id.slice(0, 16) + " · " +
      row.occurrence_count + " NPC" : "Оберіть репліку");
    setText(g("english"), row?.english || "Немає записів на цій сторінці.");
    setText(g("contexts"), row ? row.contexts.map(x =>
      "NPC #" + x.npc_id + " · " + x.npc_name +
      " · English hash " + x.english_hash).join("\n") : "");
    g("versions").replaceChildren();
    const versions = row?.versions || [];
    if (!versions.some(x => x.id === gs.selectedVersion))
      gs.selectedVersion = versions.length ? versions[versions.length - 1].id : null;
    versions.forEach(v => {
      const option = make("option", "", v.provider + " · " + v.id.slice(0, 12) +
        " · " + v.status + (v.imported ? " · IMPORTED" : ""));
      option.value = v.id;
      g("versions").appendChild(option);
    });
    if (gs.selectedVersion) g("versions").value = gs.selectedVersion;
    const v = currentVersion();
    g("ukrainian").value = v ? v.text : "";
    setText(g("status"), v?.status || "Untranslated");
    ["propose", "approved", "rejected", "deferred"].forEach(name => {
      g(name).disabled = gs.busy || !row ||
        (name !== "propose" && (!v || v.status === "stale"));
    });
    g("import").disabled = gs.busy;
  }

  async function reload() {
    if (gs.busy) return;
    gs.busy = true;
    try {
      const resp = await fetch("/api/gossip?offset=" + gs.offset +
        "&limit=" + gs.limit, {cache: "no-store"});
      if (!resp.ok) throw new Error("gossip_queue_unavailable");
      const data = await resp.json();
      gs.total = data.total;
      gs.items = data.items;
      if (!gs.items.some(x => x.group_id === gs.selectedGroup)) {
        gs.selectedGroup = gs.items[0]?.group_id || null;
        gs.selectedVersion = null;
      }
      setText(g("feedback"), "Версій: " + data.versions +
        " · явно імпортовано груп: " + data.imports);
    } catch (error) {
      setText(g("feedback"), "Gossip не завантажено: " + error.message);
    } finally {
      gs.busy = false;
      render();
    }
  }

  async function mutate(route, payload, message) {
    if (gs.busy) return;
    gs.busy = true;
    render();
    try {
      if (!state.csrf) throw new Error("review_session_not_ready");
      const result = await reviewPost("/api/gossip/" + route, payload);
      gs.busy = false;
      if (result.version_id) gs.selectedVersion = result.version_id;
      await reload();
      setText(g("feedback"), message + (result.imported !== undefined
        ? " Груп імпортовано: " + result.imported : "") +
        ". Жодних релізів або озвучення.");
    } catch (error) {
      gs.busy = false;
      setText(g("feedback"), "Не збережено: " + error.message +
        ". Перевірте оригінал, provenance і термінал.");
      render();
    }
  }
  g("prev").addEventListener("click", () => {
    gs.offset = Math.max(0, gs.offset - gs.limit); gs.selectedVersion = null; reload();
  });
  g("next").addEventListener("click", () => {
    if (gs.offset + gs.limit >= gs.total) return;
    gs.offset += gs.limit; gs.selectedVersion = null; reload();
  });
  g("refresh").addEventListener("click", reload);
  g("versions").addEventListener("change", () => {
    gs.selectedVersion = g("versions").value;
    checks.forEach(k => { g("check-" + k).checked = false; });
    render();
  });
  g("propose").addEventListener("click", () => {
    const row = currentGroup(), text = g("ukrainian").value.trim();
    if (!row || !text) {
      setText(g("feedback"), "Введіть український текст для вибраної репліки.");
      return;
    }
    mutate("propose", {group_id: row.group_id,
      english_sha256: row.english_sha256, context_sha256: row.context_sha256,
      ukrainian_text: text, provider: "manual"},
      "Нова версія збережена як pending. Потрібне окреме схвалення.");
  });
  ["approved", "rejected", "deferred"].forEach(decision => {
    g(decision).addEventListener("click", () => {
      const version = currentVersion(), reviewer = g("reviewer").value.trim();
      if (!version || !reviewer) {
        setText(g("feedback"), "Оберіть версію та вкажіть Content reviewer.");
        return;
      }
      if (g("ukrainian").value !== version.text) {
        setText(g("feedback"), "Текст змінено. Спочатку збережіть нову pending-версію.");
        return;
      }
      const attestations = Object.fromEntries(checks.map(k => [k, g("check-" + k).checked]));
      if (decision === "approved" && !Object.values(attestations).every(Boolean)) {
        setText(g("feedback"), "Для Approve перевірте всі п'ять пунктів, особливо ВСІ NPC-контексти.");
        return;
      }
      mutate("decide", {version_id: version.id, decision, reviewer, checks: attestations},
        "Рішення " + decision + " збережено.");
      checks.forEach(k => { g("check-" + k).checked = false; });
    });
  });
  g("import").addEventListener("click", () => {
    if (!window.confirm("Імпортувати лише вручну схвалені Gossip-версії в локальне build/?")) return;
    mutate("import", {}, "Явний локальний імпорт завершено.");
  });
  reload();
})();


// Immutable source revisions and independently reviewed explicit selection.
// Dynamic strings are deliberately rendered via textContent only.
(function() {
  const e = name => document.getElementById("source-" + name);
  const flags = ["text", "grammar", "ai", "rights", "all_contexts"];
  const sr = {items: [], offset: 0, limit: 20, total: 0, conflicting: 0,
              revisions: [], key: null, candidate: null, busy: false};
  const keyOf = x => [x.domain, x.target_id, x.english_sha256, x.context_sha256].join(":");
  const current = () => sr.items.find(x => keyOf(x) === sr.key) || null;
  const candidate = () => current()?.candidates.find(x => x.id === sr.candidate) || null;

  function render() {
    const group = current();
    setText(e("stats"), "Кандидатів/контекстів: " + sr.total +
      " · конфліктів: " + sr.conflicting +
      " · ревізій: " + sr.revisions.length);
    setText(e("page"), sr.total ?
      (sr.offset + 1) + "–" + (sr.offset + sr.items.length) + " / " + sr.total : "0");
    e("prev").disabled = sr.busy || sr.offset === 0;
    e("next").disabled = sr.busy || sr.offset + sr.items.length >= sr.total;
    e("items").replaceChildren();
    sr.items.forEach(item => {
      const b = make("button", "queue-item" +
        (sr.key === keyOf(item) ? " selected" : ""));
      b.type = "button";
      b.appendChild(make("div", "queue-id", item.target_id));
      b.appendChild(make("div", "queue-meta", item.candidates.length +
        " версій · " + (item.different ? "тексти відрізняються" : "без розбіжностей")));
      b.appendChild(make("span", "queue-pill", item.selected_candidate_id ?
        (item.selected_is_latest_source_revision ? "ACTIVE" : "ACTIVE · OLD REVISION") :
        item.different ? "CONFLICT · REVIEW" : "NOT SELECTED"));
      b.addEventListener("click", () => {
        sr.key = keyOf(item);
        sr.candidate = null;
        flags.forEach(x => { e("check-" + x).checked = false; });
        render();
      });
      e("items").appendChild(b);
    });
    setText(e("target"), group?.target_id || "Оберіть контекст");
    setText(e("current"), group
      ? "Активна версія: " + (group.selected_candidate_id?.slice(0, 12) || "відсутня") +
        (group.selected_is_latest_source_revision === false
          ? " · джерело оновилося, попередній ручний вибір збережено" : "")
      : "Спочатку виконайте source_revision_review.py capture / ingest.");
    setText(e("variants"), group?.candidates.map(c =>
      c.provider + " @ " + c.revision.slice(0, 10) +
      " [" + c.status + "]\n" + c.ukrainian_text +
      "\nsource: " + c.source_ref + "\n").join("\n") || "");
    e("candidate").replaceChildren();
    if (!group?.candidates.some(c => c.id === sr.candidate))
      sr.candidate = group?.selected_candidate_id ||
        group?.candidates[0]?.id || null;
    for (const v of group?.candidates || []) {
      const opt = make("option", "", v.provider + " · " +
        v.revision.slice(0, 10) + " · " + v.status +
        (v.id === group.selected_candidate_id ? " · ACTIVE" : ""));
      opt.value = v.id;
      e("candidate").appendChild(opt);
    }
    if (sr.candidate) e("candidate").value = sr.candidate;
    const version = candidate();
    setText(e("text"), version ?
      version.ukrainian_text + "\n\nRevision: " + version.revision +
      "\nSource: " + version.source_ref +
      "\nSHA-256: " + version.text_sha256 : "Оберіть версію");
    for (const action of ["approved", "rejected", "deferred", "activate"])
      e(action).disabled = sr.busy || !version ||
        (action === "activate" && version.status !== "approved");
    e("clear").disabled = sr.busy || !group?.selected_candidate_id;
  }
  async function reload() {
    if (sr.busy) return;
    sr.busy = true;
    try {
      const resp = await fetch("/api/source-reviews?offset=" + sr.offset +
        "&limit=" + sr.limit, {cache: "no-store"});
      if (!resp.ok) throw new Error("source_review_list_unavailable");
      const data = await resp.json();
      sr.items = data.items;
      sr.total = data.total;
      sr.conflicting = data.conflicts;
      sr.revisions = data.revisions;
      if (!sr.items.some(x => keyOf(x) === sr.key)) {
        sr.key = sr.items[0] ? keyOf(sr.items[0]) : null;
        sr.candidate = null;
      }
      setText(e("feedback"), "Список джерел оновлено. Ручне схвалення необхідне.");
    } catch (error) {
      setText(e("feedback"), "Помилка Source Review: " + error.message);
    } finally { sr.busy = false; render(); }
  }
  async function mutate(route, payload, message) {
    if (sr.busy) return;
    sr.busy = true;
    render();
    try {
      if (!state.csrf) throw new Error("review_session_not_ready");
      await reviewPost("/api/source-reviews/" + route, payload);
      sr.busy = false;
      await reload();
      setText(e("feedback"), message);
    } catch (error) {
      sr.busy = false;
      render();
      setText(e("feedback"), "Не збережено: " + error.message);
    }
  }
  e("refresh").addEventListener("click", reload);
  e("prev").addEventListener("click", () => {
    sr.offset = Math.max(0, sr.offset - sr.limit);
    sr.key = null; reload();
  });
  e("next").addEventListener("click", () => {
    if (sr.offset + sr.limit >= sr.total) return;
    sr.offset += sr.limit; sr.key = null; reload();
  });
  e("candidate").addEventListener("change", () => {
    sr.candidate = e("candidate").value;
    flags.forEach(x => { e("check-" + x).checked = false; });
    render();
  });
  for (const decision of ["approved", "rejected", "deferred"]) {
    e(decision).addEventListener("click", () => {
      const c = candidate(), reviewer = e("reviewer").value.trim();
      if (!c || !reviewer) {
        setText(e("feedback"), "Оберіть версію і вкажіть рев’ювера.");
        return;
      }
      const checks = Object.fromEntries(flags.map(x => [x, e("check-" + x).checked]));
      if (decision === "approved" && !Object.values(checks).every(Boolean)) {
        setText(e("feedback"), "Для Approve необхідні всі 5 ручних підтверджень.");
        return;
      }
      mutate("decide", {candidate_id: c.id, decision, reviewer, checks},
        "Рішення збережено. Активація — окремою кнопкою.");
      flags.forEach(x => { e("check-" + x).checked = false; });
    });
  }
  e("activate").addEventListener("click", () => {
    const c = candidate(), reviewer = e("reviewer").value.trim();
    if (!c || !reviewer) {
      setText(e("feedback"), "Оберіть схвалену версію і вкажіть рев’ювера.");
      return;
    }
    if (!window.confirm("Зробити цю перевірену версію активною для локального тестового ZIP?")) return;
    mutate("activate", {candidate_id: c.id, reviewer}, "Активну версію збережено.");
  });
  e("clear").addEventListener("click", () => {
    const c = current(), reviewer = e("reviewer").value.trim();
    if (!c || !reviewer) {
      setText(e("feedback"), "Вкажіть рев’ювера.");
      return;
    }
    mutate("clear", {domain: c.domain, target_id: c.target_id, reviewer},
      "Активний вибір прибрано; джерела збережено.");
  });
  reload();
})();


// Import statistics are metadata only. No unreviewed translation bodies,
// SQL, model drafts, or private source text are exposed by this panel.
(function() {
  const root = id => document.getElementById("import-stats-" + id);
  const names = {
    quests: "Quests", gossip: "Gossip (NPC)",
    gossip_common: "Gossip (common)", gossip_titles: "Gossip Quest Titles",
    places: "Places", readables: "Books & Notes", bosses: "Bosses",
    compendium: "Compendium UI"
  };
  const routes = {
    agent_verified: "Перевірено агентом · локальний тест",
    machine_1to1: "Machine 1:1 (provisional)",
    reviewed: "Human Review",
    source_selected: "Active Source Selection",
    pinned_source: "Pinned audited source"
  };
  let loading = false;

  function renderTable(target, group) {
    const container = root(target);
    container.replaceChildren();
    for (const entry of group?.rows || []) {
      const row = make("tr");
      for (const value of [
        names[entry.category] || entry.category,
        entry.source, routes[entry.route] || entry.route,
        entry.text_records + " / unique texts: " + entry.unique_translation_texts +
          (entry.unknown_text_fingerprints ? " (без fingerprint: " + entry.unknown_text_fingerprints + ")" : ""),
        entry.unique_entities
      ]) row.appendChild(make("td", "", value));
      container.appendChild(row);
    }
    if (!container.children.length) {
      const row = make("tr"), cell = make("td", "", "Немає записів");
      cell.colSpan = 5;
      row.appendChild(cell);
      container.appendChild(row);
    }
  }
  function totals(summary) {
    return Object.entries(names).map(([key, name]) =>
      name + ": " + (summary?.categories?.[key] || 0)).join(" · ");
  }
  async function loadImportStatistics() {
    if (loading) return;
    loading = true;
    root("refresh").disabled = true;
    try {
      const response = await fetch("/api/import-stats", {cache: "no-store"});
      if (!response.ok) throw new Error("import_statistics_unavailable");
      const data = await response.json();
      renderTable("reviewed", data.recorded_imports);
      renderTable("selected", data.selected_not_necessarily_built);
      renderTable("build", data.latest_successful_build);
      setText(root("review-totals"), totals(data.recorded_imports));
      setText(root("build-totals"), totals(data.latest_successful_build));
      setText(root("build-info"), data.latest_successful_build
        ? "Snapshot #" + data.latest_successful_build.snapshot_id +
          " · " + data.latest_successful_build.built_at +
          " · ZIP SHA-256: " + data.latest_successful_build.artifact_sha256
        : "Ще немає успішної SQLite-інвентаризованої збірки. Запустіть tools/build_ukrainian.py.");
      setText(root("status"), "Поточних Review-імпортів: " +
        data.recorded_imports.total_text_records +
        " · Source selections: " +
        data.selected_not_necessarily_built.total_text_records +
        " · в останньому ZIP: " +
        (data.latest_successful_build?.total_text_records ?? 0));
    } catch (error) {
      setText(root("status"), "Не вдалося отримати статистику: " + error.message);
    } finally {
      loading = false;
      root("refresh").disabled = false;
    }
  }
  root("refresh").addEventListener("click", loadImportStatistics);
  window.addEventListener("spoken-import-stats-refresh", loadImportStatistics);
  loadImportStatistics();
})();

(function() {
  const el = id => document.getElementById("gm-" + id);
  let offset = 0, busy = false;
  async function load() {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch("/api/gossip-machine?status=" +
        encodeURIComponent(el("filter").value) + "&offset=" + offset + "&limit=40", {cache: "no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.reason || data.error);
      const s = data.statuses_npc_wordings;
      setText(el("summary"), "Canonical NPC/hash: " + data.total_canonical_npc_wordings +
        " · Unique English: " + data.unique_english_wordings +
        " · Eligible import units: " + data.eligible_1to1_candidates +
        " · Machine imports (common рахується один раз): " + data.machine_imported_records +
        " · Human approved NPC/hash: " + (s.approved || 0) +
        " · Human imported groups: " + data.human_imported_groups +
        " · Pending: " + ((s.pending || 0) + (s.pending_update || 0) + (s.deferred || 0)) +
        " · Rejected: " + (s.rejected || 0) + " · Conflicts: " + (s.conflict || 0) +
        " · Untranslated: " + (s.untranslated || 0) + " · Unknown context rows: " + data.unknown_context_rows);
      el("items").replaceChildren();
      for (const item of data.items) {
        const row = make("tr");
        for (const value of [item.npc_id, item.english_hash, item.status, item.target_id])
          row.appendChild(make("td", "", value));
        el("items").appendChild(row);
      }
      el("prev").disabled = offset === 0;
      el("next").disabled = offset + 40 >= data.total;
    } catch (error) {
      setText(el("feedback"), "Помилка: " + error.message +
        ". Перевірте pinned checkouts і SQLite; після змін перезапустіть UI. Pending update потребує окремого ручного Source Review.");
    } finally { busy = false; }
  }
  el("import").addEventListener("click", async () => {
    el("import").disabled = true;
    try {
      await reviewPost("/api/gossip-machine/import", {});
      setText(el("feedback"), "Provisional імпорт збережено. Людське схвалення та ZIP включення — окремі стани.");
      await load();
    } catch (error) { setText(el("feedback"), "Імпорт відхилено: " + error.message + ". Перевірте джерела та перезапустіть UI."); }
    finally { el("import").disabled = false; }
  });
  el("filter").addEventListener("change", () => { offset = 0; load(); });
  el("refresh").addEventListener("click", load);
  el("prev").addEventListener("click", () => { offset = Math.max(0, offset - 40); load(); });
  el("next").addEventListener("click", () => { offset += 40; load(); });
  window.addEventListener("spoken-gossip-machine-refresh", load);
  load();
})();

(function () {
  const el = id => document.getElementById("agent-" + id);
  const checked = () => Array.from(el("items").querySelectorAll("input:checked"), node => node.value);
  let offset = 0, total = 0, busy = false, selected = null;

  function render(data) {
    total = data.total;
    el("items").replaceChildren();
    for (const row of data.items) {
      const item = row.candidate;
      const entry = make("div", "actions");
      const box = make("input");
      box.type = "checkbox";
      box.value = item.id;
      box.setAttribute("aria-label", "Позначити " + item.target_id);
      const label = make("button", "secondary", item.target_id + " · " + item.provider + " · " + row.status);
      label.type = "button";
      label.addEventListener("click", () => {
        selected = item.id;
        setText(el("details"), JSON.stringify(row, null, 2));
      });
      entry.append(box, label);
      el("items").appendChild(entry);
    }
    el("prev").disabled = offset === 0;
    el("next").disabled = offset + Number(el("limit").value) >= total;
    setText(el("message"), "Записів: " + total + " · " + JSON.stringify(data.counts));
  }

  async function run(action, extra = {}) {
    if (busy) return;
    busy = true;
    try {
      const isImport = action === "import-verified";
      const options = {action, module: el("module").value, limit: Number(el("limit").value)};
      if (!isImport && el("status").value && action !== "history") options.status = el("status").value;
      const data = await reviewPost("/api/agent", {...options, ...extra}, isImport && !extra.dry_run);
      if (action === "status") render(data);
      else {
        setText(el("result"), JSON.stringify(data, null, 2));
        if (action !== "history" && !isImport && !extra.dry_run) {
          render(await reviewPost("/api/agent", {...options, action: "status", offset}, false));
        }
      }
    } catch (error) {
      setText(el("message"), "Не вдалося виконати дію. Оновіть перелік і перевірте pinned джерела: " + error.message);
    } finally { busy = false; }
  }
  const list = () => run("status", {offset});
  for (const id of ["module", "status", "limit"]) {
    el(id).addEventListener("change", () => { offset = 0; selected = null; });
  }
  el("list").addEventListener("click", () => { offset = 0; list(); });
  el("prev").addEventListener("click", () => { offset = Math.max(0, offset - Number(el("limit").value)); list(); });
  el("next").addEventListener("click", () => { offset += Number(el("limit").value); list(); });
  el("one").addEventListener("click", () => {
    if (!selected) return setText(el("message"), "Виберіть запис у переліку.");
    try {
      const model = el("model").value.trim();
      run("one", {candidate_ids: [selected], dry_run: el("dry").checked,
                  ...(model ? {model: JSON.parse(model)} : {})});
    } catch (_) { setText(el("message"), "Вставте коректний JSON з порадами моделі."); }
  });
  el("batch").addEventListener("click", () => run("batch", {candidate_ids: checked(), dry_run: el("dry").checked}));
  el("pending").addEventListener("click", () => run("pending", {dry_run: el("dry").checked, status: "unreviewed"}));
  el("history").addEventListener("click", () => {
    if (selected) run("history", {candidate_ids: [selected]});
    else setText(el("message"), "Виберіть запис для перегляду історії.");
  });
  el("preview").addEventListener("click", () => run("import-verified", {dry_run: true}));
  el("import").addEventListener("click", () => {
    if (window.confirm("Імпортувати всі придатні записи вибраного модуля для приватного тестування?")) {
      run("import-verified", {confirm: true});
    }
  });
})();

(function () {
  const el = id => document.getElementById("comparison-" + id);
  let offset = 0, total = 0, busy = false;
  const limit = 10;

  async function compare(load = false) {
    if (busy) return;
    busy = true;
    try {
      if (load) {
        const data = await reviewPost("/api/source-comparison", {}, false);
        for (const side of ["left", "right"]) {
          const select = el(side);
          const previous = select.value;
          select.replaceChildren(make("option", "", "Оберіть знімок"));
          select.firstChild.value = "";
          for (const row of data.revisions) {
            const option = make("option", "", row.provider + " · " + row.revision);
            option.value = row.provider + ":" + row.revision;
            select.appendChild(option);
          }
          if (Array.from(select.options).some(opt => opt.value === previous)) select.value = previous;
        }
        setText(el("message"), data.revisions.length ? "Оберіть два знімки." :
          "Знімків немає. Виконайте capture або ingest у CLI.");
        return;
      }
      const [left_provider, before] = el("left").value.split(":");
      const [right_provider, after] = el("right").value.split(":");
      const mode = el("mode").value;
      if (!before || !after || (left_provider === right_provider) !== (mode === "revision")) {
        return setText(el("message"), "Оберіть знімки потрібних джерел. Відсутній знімок додайте через capture або ingest.");
      }
      const data = await reviewPost("/api/source-comparison", {
        mode, left_provider, right_provider, before, after, offset, limit,
        change_filter: el("filter").value
      }, false);
      total = data.total;
      setText(el("message"), "Записів: " + total + " · " + JSON.stringify(data.counts));
      el("results").replaceChildren();
      for (const row of data.changes) {
        const card = make("section");
        card.appendChild(make("h3", "", row.target_id + " · " + row.change));
        const pair = make("div", "comparison");
        for (const version of [row.before, row.after]) {
          const content = make("div");
          content.appendChild(make("pre", "story-text", version ?
            version.provider + " · " + version.revision + " · " + version.status + "\n\n" +
            version.ukrainian_text + "\n\n" + version.source_ref + "\n" + version.text_sha256 :
            "У цьому знімку запис відсутній."));
          if (version?.status === "approved") {
            const button = make("button", "secondary", "Активувати схвалену версію");
            button.type = "button";
            button.addEventListener("click", async () => {
              const reviewer = document.getElementById("source-reviewer").value.trim();
              if (!reviewer) {
                setText(el("message"), "Вкажіть рев’ювера в розділі Source Revision Review.");
                document.getElementById("source-reviewer").focus();
                return;
              }
              if (!window.confirm("Зробити цей схвалений переклад активним для " + row.target_id + "?")) return;
              try {
                await reviewPost("/api/source-reviews/activate", {candidate_id: version.id, reviewer});
                document.getElementById("source-refresh").click();
                setText(el("message"), "Активовано схвалену версію " + version.id);
              } catch (error) { setText(el("message"), "Активацію відхилено: " + error.message); }
            });
            content.appendChild(button);
          }
          pair.appendChild(content);
        }
        card.appendChild(pair);
        el("results").appendChild(card);
      }
      el("prev").disabled = offset === 0;
      el("next").disabled = offset + limit >= total;
    } catch (error) {
      setText(el("message"), "Не вдалося порівняти знімки: " + error.message);
    } finally { busy = false; }
  }
  el("load").addEventListener("click", () => compare(true));
  el("run").addEventListener("click", () => { offset = 0; compare(); });
  el("prev").addEventListener("click", () => { offset = Math.max(0, offset - limit); compare(); });
  el("next").addEventListener("click", () => { if (offset + limit < total) { offset += limit; compare(); } });
})();

const {readFileSync} = require("node:fs");
const {runInNewContext} = require("node:vm");
const assert = require("node:assert/strict");
const {test} = require("node:test");

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.events = {};
    this.value = "";
    this.textContent = "";
  }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.append(item); return item; }
  replaceChildren(...items) { this.children = items; }
  get childElementCount() { return this.children.length; }
  addEventListener(name, callback) { this.events[name] = callback; }
  setAttribute() {}
  querySelectorAll() { return []; }
  all() { return [this, ...this.children.flatMap(child => child.all())]; }
}

const quest = "Spoken_Quest_UA";
const gossip = "Spoken_Gossip_UA";
const script = readFileSync("tools/review_ui/static/manager.js", "utf8");
const response = body => ({ok: !body.error, json: async () => body});
const flush = () => new Promise(resolve => setImmediate(resolve));

function browser(handler) {
  const elements = new Map();
  const el = id => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };
  el("module").value = quest;
  const requests = [];
  const vm = {
    navigator: {clipboard: {writeText: async value => { el("copied").textContent = value; }}},
    document: {getElementById: el, createElement: tag => new Element(tag), querySelectorAll: () => []},
    fetch: async (url, options) => {
      if (url === "/api/bootstrap") return response({csrf_token: "token"});
      const body = JSON.parse(options.body);
      const action = url.split("/").pop();
      requests.push({action, ...body});
      return response(await handler(action, body));
    },
    setTimeout, clearTimeout, window: {confirm: () => true},
  };
  runInNewContext(script, vm);
  return {el, vm, requests, run: code => runInNewContext(code, vm)};
}

const fixture = {
  id: "q:42:accept", type: "quest", label: "Fixture", status: "conflict",
  originals: ["Hello."], contexts: [], help: "Review",
  candidates: [{text: "Вітаю.", provider: "manual", review: "pending",
    review_id: "candidate", review_kind: "quest", eligibility: "selectable"}],
};

test("Shared status filter and module heading follow Quest and Gossip", async () => {
  const html = readFileSync("tools/review_ui/static/manager.html", "utf8");
  assert.match(html, /<label id="quest-filter-control">Стан/);
  const b = browser((action, body) => listing(body.module));
  await flush();
  assert.equal(b.el("operation-heading").textContent, "Створення модуля Quest");
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("operation-heading").textContent, "Створення модуля Gossip");
  b.el("quest-filter").value = "quest_ready";
  b.el("quest-filter").events.change();
  await flush();
  assert.equal(b.requests.at(-1).module, gossip);
  assert.equal(b.requests.at(-1).filter_by, "quest_ready");
});

test("Gossip table shows separate NPC ID and English text hash ID", async () => {
  const html = readFileSync("tools/review_ui/static/manager.html", "utf8");
  assert.match(html, /<th scope="col">npcID<\/th><th scope="col">ID<\/th>/);
  const b = browser((action, body) => listing(body.module));
  await flush();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  const row = {
    id:"gossip:68:107874079", type:"gossip", npc_id:68, english_hash:107874079,
    label:"Innkeeper", ready_to_import:true, status:"ready", built:null,
  };
  b.run("renderList(" + JSON.stringify({items:[row], total:1, build:null,
    summary:{gossip:{total:1, ready:1, quest_imported:0, quest_problem:0}}}) + ")");
  const columns = b.el("rows").children[0].children;
  assert.deepEqual(columns.slice(0, 3).map(x => x.textContent),
    ["Gossip", "68", "107874079"]);
  assert.equal(columns[4].children[0].textContent, "Готовий до імпорту");
  assert.equal(b.el("metrics").children[1].children[1].textContent, "1");
  b.run("renderList(" + JSON.stringify({items:[{...row, built:{source:"classicua"},
    ready_to_import:false}], total:1, build:{built_at:"2026-11-20"},
    summary:{gossip:{total:1, ready:0, quest_imported:1, quest_problem:0}}}) + ")");
  assert.equal(b.el("rows").children[0].children[4].children[0].textContent, "Імпортовано");
  assert.match(b.el("build-state").textContent, /Останній Gossip ZIP/);
  b.run("renderDetail(" + JSON.stringify({...row, built:{source:"classicua"},
    ready_to_import:false, review_binding:"pinned-binding", originals:["Hello."],
    candidates:[], help:"Переклад включений"}) + ")");
  assert.equal(b.el("selected").all().find(x => x.textContent === "Імпортовано")?.textContent,
    "Імпортовано");

  b.el("module").value = quest;
  b.el("module").events.change();
  await flush();
  b.run("renderList(" + JSON.stringify({items:[{
    id:"q:42:accept", type:"quest", label:"Quest", ready_to_import:true, built:null,
  }], total:1, build:null,
    summary:{quest:{total:1, ready:1, quest_imported:0, quest_problem:0}}}) + ")");
  assert.deepEqual(b.el("rows").children[0].children.slice(0,3)
    .map(x => x.textContent), ["Quest", "—", "42"]);
});

test("Gossip selects through the shared editor and does not build on save", async () => {
  const row = {...fixture, type: "gossip", id: "gossip:42:4", npc_id: 42, review_binding: "pin",
    candidates: [{text: "Вітаю.", sha256: "a", provider: "classicua"},
                 {text: "Привіт.", sha256: "b", provider: "classicua"}]};
  const b = browser((action, body) => action === "detail" ? row : action === "choose_gossip" ?
    {module: gossip, build: "review_saved"} : listing(body.module));
  await flush();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  await b.run('detail("gossip:42:4")');
  const nodes = b.el("selected").all();
  const field = nodes.find(node => node.tag === "textarea");
  const options = nodes.find(node => node.tag === "select");
  assert.equal(field.value, "");
  options.value = "b";
  options.events.change();
  assert.equal(field.value, "Привіт.");
  nodes.find(node => node.textContent === "Зберегти").events.click();
  await flush();
  assert.equal(b.requests.find(request => request.action === "choose_gossip").candidate, "b");
  assert.equal(b.requests.some(request => request.action === "import_ready"), false);
});

test("Gossip audit alternatives populate the editor but save as manual choices", async () => {
  const row = {...fixture, type: "gossip", id: "gossip:295:934080707",
    npc_id: 295, review_binding: "pinned-evidence", originals: [
      "When you give love tokens to townsfolk, you'll receive different gifts in return."
    ], candidates: [], selected_sha256: null, unverified_alternatives: [
      {kind: "corpus_alternate_candidate", english: "When you give love tokens...",
        ukrainian: "Даруючи знаки любові, ви отримаєте подарунки.",
        scope: "!common", hash: 100, reference: "entries/gossip.lua:50"},
      {kind: "same_template", english: "When you give love tokens ...",
        ukrainian: "Подарунки за знаки любові.",
        scope: 295, hash: 200, reference: "entries/innkeepers.lua:60"},
      {kind: "wrong_npc_scope", english: "English-only hint",
        ukrainian: null, scope: 42, hash: 300, reference: "entries/gossip.lua:70"},
    ]};
  const b = browser((action, body) => {
    if (action === "list") return listing(body.module);
    if (action === "detail") return row;
    if (action === "save_gossip") return {module: gossip, build: "review_saved"};
    throw new Error("Unexpected action: " + action);
  });
  await flush();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  await b.run('detail("gossip:295:934080707")');
  const nodes = b.el("selected").all();
  const select = nodes.find(node => node.tag === "select");
  const field = nodes.find(node => node.tag === "textarea");
  assert.ok(select);
  assert.equal(select.children.length, 3);
  assert.ok(select.children[0].textContent.includes("Аудит 1"));
  assert.ok(select.children[1].textContent.includes("Подарунки за знаки любові."));
  assert.ok(select.children.every(option => option.textContent.length <= 75));
  assert.ok(select.children.every(option => !option.textContent.includes("entries/")));
  assert.equal(select.children[2].disabled, true);
  assert.match(select.children[2].textContent, /Українського перекладу немає/);
  assert.equal(field.value, ""); // no automatic acceptance of audit-only leads
  select.value = "audit:1";
  select.events.change();
  assert.equal(field.value, "Подарунки за знаки любові.");
  assert.equal(b.requests.some(request => request.action === "save_gossip"), false);
  nodes.find(node => node.textContent === "Зберегти").events.click();
  await flush();
  const saved = b.requests.find(request => request.action === "save_gossip");
  assert.equal(saved.text, "Подарунки за знаки любові.");
  assert.equal(saved.identity, row.id);
  assert.equal(saved.binding, "pinned-evidence");
  assert.equal(b.requests.some(request => request.action === "choose_gossip"), false);
  assert.equal(b.requests.some(request => request.action === "import_ready"), false);
});

test("Gossip same-template auto-ready candidate is not duplicated by its audit lead", async () => {
  const text = "Срібнокрилим стражам потрібна допомога, {Ім'я}.";
  const row = {...fixture, type:"gossip", id:"gossip:68:1978831227",
    review_binding:"pinned-guard", ready_to_import:true,
    selected_sha256:"template-verified",
    candidates:[{text, sha256:"template-verified", provider:"classicua",
      reference:"entries/classic/gossip.lua:12", match_type:"same_template"}],
    unverified_alternatives:[{kind:"same_template", ukrainian:text,
      reference:"entries/classic/gossip.lua:12",
      english:"The Silverwing Sentinels need your help. <name>, visit Stormwind Keep."}]};
  const b = browser((action, body) => action === "detail" ? row : listing(body.module));
  await flush();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const nodes = b.el("selected").all();
  const select = nodes.find(node => node.tag === "select");
  const field = nodes.find(node => node.tag === "textarea");
  assert.equal(select.children.length, 1);
  assert.equal(field.value, text);
  assert.ok(select.children[0].textContent.length <= 60);
});

test("Verified Gossip candidates retain source provenance when audit alternatives exist", async () => {
  const row = {...fixture, type: "gossip", id: "gossip:68:107874079",
    review_binding: "pin", selected_sha256: "verified-a",
    candidates: [{text: "Вітаю.", sha256: "verified-a", provider: "classicua",
      reference: "entries/gossip.lua:17"}],
    unverified_alternatives: [{kind: "wrong_npc_scope",
      english: "Hello.", ukrainian: "Привіт.",
      reference: "entries/gossip.lua:33", scope: 42, hash: 4}]};
  const b = browser((action, body) =>
    action === "choose_gossip" ? {module: gossip, build: "review_saved"} :
    action === "detail" ? row : listing(body.module));
  await flush();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const nodes = b.el("selected").all();
  const field = nodes.find(node => node.tag === "textarea");
  const select = nodes.find(node => node.tag === "select");
  assert.equal(field.value, "Вітаю.");
  assert.equal(select.children.length, 2);
  nodes.find(node => node.textContent === "Зберегти").events.click();
  await flush();
  assert.equal(b.requests.find(request => request.action === "choose_gossip").candidate, "verified-a");
  assert.equal(b.requests.some(request => request.action === "save_gossip"), false);
});

test("Gossip uses the selected module and retains the shared path during operation", async () => {
  let complete;
  const pending = new Promise(resolve => { complete = resolve; });
  const b = browser((action, body) => action === "install" ? pending :
    action === "import_ready" ? {module: gossip, sha256: "digest", summary: {gossip: {included: 1}}} :
    listing(body.module));
  await flush();
  b.el("wow-path").value = "D:\\Games\\Custom WoW\\";
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  await b.run("reimport()");
  assert.equal(b.requests.find(r => r.action === "import_ready").module, gossip);
  b.el("install").events.click();
  b.el("install").events.click();
  await flush();
  assert.equal(b.requests.filter(r => r.action === "install").length, 1);
  assert.equal(b.requests.find(r => r.action === "install").wow_path, b.el("wow-path").value);
  assert.equal(b.el("module").disabled, true);
  complete({module: gossip, installed: [gossip], replaced: [], addons: "fixture"});
  await flush();
  assert.equal(b.el("module").disabled, false);
});

function listing(module) {
  return {items: [], total: 100, build: null, summary: module === quest ?
    {quest: {total: 100, ready: 1}} : {gossip: {total: 70, quest_imported: 0, quest_problem: 70}}};
}

test("worker timeout shows Ukrainian recovery instructions and no success summary", async () => {
  const b = browser((action, body) => ["reimport", "import_ready"].includes(action) ? {
    error: "invalid_or_duplicate_review_decision",
    reason: "manager_reimport_timed_out_check_build",
  } : listing(body.module));
  await flush();
  for (const module of [quest, gossip]) {
    b.el("module").value = module;
    b.el("module").events.change();
    await flush();
    for (const dryRun of [true, false]) {
      await b.run(`reimport(${dryRun})`);
      assert.equal(b.requests.at(-1).module, module);
      assert.equal(b.el("operation-status").textContent,
        "Час очікування минув. Оновіть список, щоб перевірити стан збірки.");
      assert.equal(b.el("run-summary").hidden, true);
      assert.equal(b.el("reimport").disabled, false);
    }
  }
});

test("detail renders multiple originals, contextual evidence, candidates and missing text", async () => {
  const b = browser((action, body) => listing(body.module));
  await flush();
  b.vm.row = {...fixture, status: "multiple_originals", originals: ["One", "Two"], original_variants: [
    {text: "One", target_id: "q:42:accept", contexts: [{npc_id: 42, faction: "horde"}],
      review_factions: ["horde"]},
    {text: "Two", target_id: "q:42:accept", contexts: [{npc_id: 43, faction: "alliance"}],
      review_factions: ["alliance"]},
  ]};
  b.run("renderDetail(row)");
  const text = () => b.el("selected").all().map(node => node.textContent).join(" ");
  assert.match(text(), /One.*Two/s);
  assert.ok(b.el("selected").all().some(node =>
    node.tag === "textarea" && node.value === "Вітаю."));
  b.vm.row = {...fixture, type: "gossip", status: "missing", originals: [], candidates: []};
  b.run("renderDetail(row)");
  assert.match(text(), /Перекладу немає/);
});

test("switching module clears detail, resets pagination, and ignores stale responses", async () => {
  let resolveDetail;
  const oldDetail = new Promise(resolve => { resolveDetail = resolve; });
  const b = browser((action, body) => action === "detail" ? oldDetail : listing(body.module));
  await flush();
  b.el("next").events.click();
  await flush();
  assert.equal(b.requests.at(-1).offset, 30);
  const pending = b.run('detail("q:42:accept")');
  b.el("module").value = gossip;
  b.el("module").events.change();
  resolveDetail(fixture);
  await pending;
  await flush();
  assert.equal(b.requests.at(-1).module, gossip);
  assert.equal(b.requests.at(-1).offset, 0);
  assert.equal(b.el("selected").childElementCount, 0);
  assert.equal(b.el("metrics").children[2].children[1].textContent, "70");
  assert.equal(b.el("reimport").textContent, "Створити модуль");
});

test("obsolete search and detail requests do not keep the loading indicator active", async () => {
  let resolveSearch, resolveDetail;
  const search = new Promise(resolve => { resolveSearch = resolve; });
  const detail = new Promise(resolve => { resolveDetail = resolve; });
  let holdSearch = false;
  const b = browser((action, body) => action === "detail" ? detail :
    holdSearch && body.module === quest ? search : listing(body.module));
  await flush();
  holdSearch = true;
  const oldList = b.run("list()");
  const oldDetail = b.run('detail("q:42:accept")');
  assert.equal(b.el("loading-bar").hidden, false);
  b.el("query").value = "new query";
  b.el("query").events.input();
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("loading-bar").hidden, true);
  resolveSearch(listing(quest));
  resolveDetail(fixture);
  await Promise.all([oldList, oldDetail]);
  assert.equal(b.el("selected").childElementCount, 0);
  assert.equal(b.el("metrics").children[2].children[1].textContent, "70");
});

test("Install submits a single selected-module build-and-install request", async () => {
  const b = browser((action, body) => {
    if (action === "install") return {
      module: quest, installed: ["Spoken_Ukrainian", quest],
      replaced: [quest],
      backup: "D:\\Games\\World of Warcraft\\_forever_\\Interface\\AddOns\\.spoken-ukrainian-backups\\old",
      addons: "D:\\Games\\World of Warcraft\\_forever_\\Interface\\AddOns",
    };
    return listing(body.module);
  });
  await flush();
  b.el("wow-path").value = "D:\\Games\\World of Warcraft\\";
  b.el("install").events.click();
  await flush();
  const installs = b.requests.filter(request => request.action === "install");
  assert.equal(installs.length, 1);
  assert.equal(installs[0].module, quest);
  assert.equal(installs[0].wow_path, "D:\\Games\\World of Warcraft\\");
  assert.equal(b.requests.some(request =>
    ["reimport", "import_ready"].includes(request.action)), false);
  assert.match(b.el("install-status").textContent, /Встановлено: Spoken_Ukrainian, Spoken_Quest_UA/);
  assert.match(b.el("install-status").textContent, /Резервна копія:/);
  assert.match(b.el("install-status").textContent, /Перезапустіть WoW/);
  await b.run("reimport(true)");
  assert.equal(b.el("install-status").textContent, "");
  assert.equal(b.el("install").disabled, false);
  assert.equal(b.el("wow-path").disabled, false);
});

test("Install failure displays actionable guidance without touching the module UI", async () => {
  const b = browser((action, body) => action === "install" ?
    {error: "invalid_or_duplicate_review_decision",
     reason: "manager_install_module_not_built"} : listing(body.module));
  await flush();
  b.el("wow-path").value = "D:\\Games\\World of Warcraft";
  b.el("install").events.click();
  await flush();
  assert.match(b.el("install-status").textContent, /Створити модуль/);
  assert.equal(b.el("install").disabled, false);
  assert.equal(b.el("reimport").disabled, false);
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("install-status").textContent, "");
  b.el("install").events.click();
  await flush();
  assert.equal(b.requests.at(-1).module, gossip);
});

test("Quest translation editor uses a full-width multi-line field with actions below", async () => {
  const row = {...fixture, review_binding: "pinned-binding",
    candidates: [{text: "Вітаю.", provider: "classicua", sha256: "choice-a"}]};
  const b = browser((action, body) => action === "detail" ? row : listing(body.module));
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const section = b.el("selected").all().find(x => x.tag === "section" && x.className === "quest-editor");
  assert.ok(section);
  const field = section.all().find(x => x.tag === "textarea");
  assert.equal(field.rows, 7);
  assert.equal(field.value, "Вітаю.");
  const actions = section.all().find(x => x.className === "quest-editor-actions");
  assert.ok(actions);
  assert.deepEqual(actions.children.map(x => x.textContent),
    ["Зберегти", "Скопіювати запит для Codex"]);
  assert.ok(section.children.indexOf(field) < section.children.indexOf(actions));
});

test("Quest selection shows all candidates without reviewer forms or checkboxes", async () => {
  const choices = [
    {text:"Вітаю.", provider:"classicua", sha256:"choice-a", eligibility:"mapping_required"},
    {text:"Доброго дня.", provider:"classicua", sha256:"choice-b", eligibility:"source_review"},
  ];
  const row = {...fixture, originals:["Hello.", "Greetings."], review_binding:"pinned-binding", candidates:choices};
  let current = row;
  const b = browser((action, body) => {
    if (action === "list") return listing(body.module);
    if (action === "detail") return current;
    assert.equal(action, "choose_quest");
    assert.equal(body.candidate, "choice-b");
    assert.equal(body.binding, "pinned-binding");
    current = {...row, ready_to_import:true};
    return {module:quest, build:"review_saved"};
  });
  await flush();
  await b.run('detail("q:42:accept")');
  const nodes = b.el("selected").all();
  assert.equal(nodes.filter(x => x.tag === "input").length, 0);
  assert.equal(nodes.filter(x => x.tag === "fieldset").length, 0);
  const select = nodes.find(x => x.tag === "select");
  assert.equal(select.children.length, 2);
  assert.ok(select.children.some(x => x.textContent.includes("Доброго дня.")));
  const field = nodes.find(x => x.tag === "textarea");
  assert.equal(field.value, "Вітаю.");
  select.value = "choice-b";
  select.events.change();
  assert.equal(field.value, "Доброго дня.");
  nodes.find(x => x.textContent === "Зберегти").events.click();
  await flush();
  assert.equal(b.requests.find(x => x.action === "choose_quest").candidate, "choice-b");
  assert.ok(b.el("selected").all().some(x => x.textContent === "Готовий до імпорту"));
  assert.equal(b.requests.some(x => x.action === "reimport"), false);
});

test("Editing a selected Quest candidate saves a manual translation via the same button", async () => {
  const row = {...fixture, review_binding:"pinned-binding", selected_sha256:"choice-a",
    candidates:[{text:"Вітаю.", provider:"classicua", sha256:"choice-a"}]};
  const b = browser((action, body) => {
    if (action === "list") return listing(body.module);
    if (action === "detail") return row;
    assert.equal(action, "save_quest");
    assert.equal(body.text, "Вітаю, друже!");
    return {module:quest, build:"review_saved"};
  });
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const nodes = b.el("selected").all();
  const field = nodes.find(x => x.tag === "textarea");
  assert.equal(field.value, "Вітаю.");
  field.value = "Вітаю, друже!";
  nodes.find(x => x.textContent === "Зберегти").events.click();
  await flush();
  assert.equal(b.requests.filter(x => x.action === "save_quest").length, 1);
  assert.equal(b.requests.filter(x => x.action === "choose_quest").length, 0);
});

test("Quest bulk button imports all ready records and skips confirmation modal", async () => {
  const b = browser((action, body) => {
    if (action === "import_ready") return {
      module: quest, build: "success", sha256: "example",
      summary: {quest: {total: 20, ready: 0, included: 9, missing: 11,
        conflicts: 0, multiple_originals: 0, pending_review: 0}},
      agent: {eligible: 0, skipped: 0, reasons: []}, skipped: [],
    };
    return {...listing(body.module), summary: {quest: {total: 20, ready: 3}}};
  });
  await flush();
  assert.equal(b.el("reimport").textContent, "Створити модуль");
  assert.equal(b.el("reimport").disabled, false);
  b.el("reimport").events.click();
  await flush();
  const imports = b.requests.filter(req => req.action === "import_ready");
  assert.equal(imports.length, 1);
  assert.equal(imports[0].module, quest);
  assert.equal(imports[0].confirm, true);
  assert.equal(b.el("operation-status").textContent,
    "Модуль створено.");
});

test("Quest summary and filters show only imported, ready and problematic buckets", async () => {
  const b = browser((action, body) => {
    assert.equal(action, "list");
    return body.module === quest ? {
      items: [], total: 10, build: null,
      summary: {quest: {total: 10, quest_imported: 5, ready: 2, quest_problem: 3}},
    } : listing(body.module);
  });
  await flush();
  assert.equal(b.el("metrics").children.length, 4);
  assert.deepEqual(b.el("metrics").children.map(x => x.children[0].textContent),
    ["Імпортовано", "Готові до імпорту", "Проблемні", "Покриття перекладом"]);
  assert.deepEqual(b.el("metrics").children.map(x => x.children[1].textContent),
    ["5", "2", "3", "70%"]);
  assert.equal(b.el("metrics").children[3].children[2].textContent, "7 із 10 записів");
  assert.equal(b.el("reimport").textContent, "Створити модуль");
  b.el("quest-filter").value = "quest_problem";
  b.el("quest-filter").events.change();
  await flush();
  assert.equal(b.requests.at(-1).filter_by, "quest_problem");
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("quest-filter").value, "all");
});

test("Quest and Gossip coverage uses unfiltered module totals, handles rounding and empty data", async () => {
  const b = browser((action, body) => listing(body.module));
  await flush();
  b.run("renderList(" + JSON.stringify({
    items:[], total:1, build:null,
    summary:{quest:{total:3, ready:1, quest_imported:1, quest_problem:1,
      covered:2, coverage_percent:66.7}},
  }) + ")");
  assert.equal(b.el("metrics").children[3].children[1].textContent, "66,7%");
  assert.equal(b.el("metrics").children[3].children[2].textContent, "2 із 3 записів");

  // This is a filtered page (one row). Coverage still uses the entire
  // module's summary, not the visible page count or number of search hits.
  b.el("module").value = gossip;
  b.run("renderList(" + JSON.stringify({
    items:[], total:1, build:null,
    summary:{gossip:{total:4, ready:1, quest_imported:2, quest_problem:1,
      covered:3, coverage_percent:75}},
  }) + ")");
  assert.equal(b.el("metrics").children[3].children[1].textContent, "75%");
  assert.equal(b.el("metrics").children[3].children[2].textContent, "3 із 4 записів");

  b.run("renderList(" + JSON.stringify({
    items:[], total:0, build:null,
    summary:{gossip:{total:0, ready:0, quest_imported:0, quest_problem:0,
      covered:0, coverage_percent:null}},
  }) + ")");
  assert.equal(b.el("metrics").children[3].children[1].textContent, "—");
  assert.equal(b.el("metrics").children[3].children[2].textContent, "0 із 0 записів");
});

test("Quest missing translation can be entered without reviewer identity", async () => {
  const row = {...fixture, status:"missing", review_binding:"pinned-binding", candidates:[]};
  const b = browser((action, body) => {
    if (action === "list") return listing(body.module);
    if (action === "detail") return row;
    assert.equal(action, "save_quest");
    assert.equal(body.text, "Мій переклад.");
    assert.equal(body.binding, "pinned-binding");
    assert.equal(body.reviewer, undefined);
    return {module:quest, build:"review_saved"};
  });
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const nodes = b.el("selected").all();
  const field = nodes.find(x => x.tag === "textarea");
  assert.ok(field);
  field.value = "Мій переклад.";
  nodes.find(x => x.textContent === "Зберегти").events.click();
  await flush();
  assert.equal(b.requests.find(x => x.action === "save_quest").text, "Мій переклад.");
  assert.equal(b.requests.some(x => x.action === "reimport"), false);
  assert.match(b.el("operation-status").textContent, /Готовий до імпорту/);
  nodes.find(x => x.textContent === "Скопіювати запит для Codex").events.click();
  await flush();
  assert.match(b.el("copied").textContent, /Hello/);
});


test("Gossip match type filter uses server pagination and resets on module changes", async () => {
  const html = readFileSync("tools/review_ui/static/manager.html", "utf8");
  assert.match(html, /id="match-filter"/);
  assert.match(html, /value="same_template"/);
  assert.match(html, /value="whitespace_candidate"/);
  const b = browser((action, body) => listing(body.module));
  await flush();
  assert.equal(b.el("match-filter-control").hidden, true);
  b.el("module").value = gossip;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("match-filter-control").hidden, false);
  assert.equal(b.requests.at(-1).match_type, "all");
  b.el("match-filter").value = "same_template";
  b.el("match-filter").events.change();
  await flush();
  assert.equal(b.requests.at(-1).match_type, "same_template");
  const row = {
    id:"gossip:68:107874079", type:"gossip", npc_id:68, english_hash:107874079,
    label:"Innkeeper", ready_to_import:true, status:"ready", built:null,
    match_types:["same_template"],
  };
  b.run("renderList(" + JSON.stringify({items:[row], total:1, build:null,
    summary:{gossip:{total:1, ready:1, quest_imported:0, quest_problem:0}}}) + ")");
  assert.match(b.el("rows").children[0].children.at(-1).textContent, /Той самий шаблон/);
  b.el("module").value = quest;
  b.el("module").events.change();
  await flush();
  assert.equal(b.el("match-filter-control").hidden, true);
  assert.equal(b.el("match-filter").value, "all");
  assert.equal(b.requests.at(-1).match_type, undefined);
});

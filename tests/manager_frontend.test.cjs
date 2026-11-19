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

function listing(module) {
  return {items: [], total: 100, build: null, summary: module === quest ?
    {quest: {total: 100}} : {gossip: {total: 70}}};
}

test("worker timeout shows Ukrainian recovery instructions and no success summary", async () => {
  const b = browser((action, body) => action === "reimport" ? {
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
  assert.ok(b.el("selected").all().some(node => node.textContent === "Вітаю."));
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
  assert.equal(b.el("metrics").children[0].children[1].textContent, "70");
  assert.match(b.el("reimport").textContent, /Gossip/);
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
    current = {...row, built:{text_sha256:"choice-b", route:"user_selected", source:"classicua"}};
    return {module:quest, build:"success", summary:{quest:{total:1}}, agent:{eligible:0, skipped:0, reasons:[]},
      skipped:[], sha256:"fixture"};
  });
  await flush();
  await b.run('detail("q:42:accept")');
  const nodes = b.el("selected").all();
  assert.equal(nodes.filter(x => x.tag === "input").length, 0);
  assert.equal(nodes.filter(x => x.tag === "fieldset").length, 0);
  const select = nodes.find(x => x.tag === "select");
  assert.equal(select.children.length, 2);
  assert.ok(select.children.some(x => x.textContent.includes("Доброго дня.")));
  select.value = "choice-b";
  select.events.change();
  nodes.find(x => x.textContent === "Використати переклад").events.click();
  await flush();
  assert.equal(b.requests.find(x => x.action === "choose_quest").candidate, "choice-b");
  assert.ok(b.el("selected").all().some(x => x.textContent === "У ZIP"));
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
    return {module:quest, build:"success", summary:{quest:{total:1}}, agent:{eligible:0, skipped:0, reasons:[]},
      skipped:[], sha256:"fixture"};
  });
  await flush();
  b.run("renderDetail(" + JSON.stringify(row) + ")");
  const nodes = b.el("selected").all();
  const field = nodes.find(x => x.tag === "textarea");
  assert.ok(field);
  field.value = "Мій переклад.";
  nodes.find(x => x.textContent === "Зберегти й застосувати").events.click();
  await flush();
  assert.equal(b.requests.find(x => x.action === "save_quest").text, "Мій переклад.");
  nodes.find(x => x.textContent === "Скопіювати запит для Codex").events.click();
  await flush();
  assert.match(b.el("copied").textContent, /Hello/);
});

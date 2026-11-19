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
const response = body => ({ok: true, json: async () => body});
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
    review_id: "candidate", review_kind: "quest"}],
};

function listing(module) {
  return {items: [], total: 100, build: null, summary: module === quest ?
    {quest: {total: 100}} : {gossip: {total: 70}}};
}

test("detail renders multiple originals, contextual evidence, candidates and missing text", async () => {
  const b = browser((action, body) => listing(body.module));
  await flush();
  b.vm.row = {...fixture, status: "multiple_originals", original_variants: [
    {text: "One", target_id: "q:42:accept", contexts: [{npc_id: 42, faction: "horde"}],
      review_factions: ["horde"]},
    {text: "Two", target_id: "q:42:accept", contexts: [{npc_id: 43, faction: "alliance"}],
      review_factions: ["alliance"]},
  ]};
  b.run("renderDetail(row)");
  const text = () => b.el("selected").all().map(node => node.textContent).join(" ");
  assert.match(text(), /One.*NPC 42.*Two.*NPC 43/s);
  assert.match(text(), /Вітаю/);
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

test("candidate confirmation requires a selection and all explicit attestations", async () => {
  const b = browser((action, body) => action === "list" ? listing(body.module) : {
    ...listing(body.module), agent: {eligible: 1, skipped: 0, reasons: []}, skipped: [], sha256: "fixture",
  });
  await flush();
  b.vm.row = fixture;
  b.run("renderDetail(row)");
  const fields = b.el("selected").all();
  const select = fields.find(node => node.tag === "select");
  const fieldset = fields.find(node => node.tag === "fieldset");
  const inputs = fields.filter(node => node.tag === "input");
  const approve = fields.find(node => node.textContent === "Підтвердити переклад");
  assert.equal(approve.disabled, true);
  inputs[0].value = "Reviewer";
  select.value = "candidate";
  select.events.change();
  assert.equal(approve.disabled, true);
  inputs.slice(1).forEach(input => { input.checked = true; });
  fieldset.events.input();
  assert.equal(approve.disabled, false);
  approve.events.click();
  await flush();
  const request = b.requests.find(entry => entry.action === "confirm_candidate");
  assert.equal(request.module, quest);
  assert.equal(request.candidate, "candidate");
  assert.equal(request.confirm, true);
  assert.ok(Object.values(request.checks).every(Boolean));
  assert.match(b.el("operation-status").textContent, /перевірено в ZIP/);
});

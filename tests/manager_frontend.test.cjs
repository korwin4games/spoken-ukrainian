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

test("missing Quest draft and audited registration have separate controls from approval", async () => {
  const b = browser((action, body) => action === "list" ? listing(body.module) :
    {module: body.module, build: "review_saved"});
  await flush();
  const candidate = {text: "Вітаю.", provider: "classicua", review: "candidate"};
  b.vm.row = {...fixture, status: "missing", candidates: [
    {...candidate, eligibility: "mapping_required"},
    {...candidate, eligibility: "rights_blocked"},
    {...candidate, eligibility: "format_blocked"},
    {...candidate, eligibility: "stale", review_id: "stale-id"},
    {...candidate, eligibility: "source_review"},
  ]};
  b.run("renderDetail(row)");
  const fields = () => b.el("selected").all();
  const byText = label => fields().find(node => node.textContent === label);
  assert.ok(fields().some(node => /Спершу.*Stage 3/.test(node.textContent)));
  assert.ok(fields().some(node => /Права або походження/.test(node.textContent)));
  assert.ok(fields().some(node => /Формат або підстановки/.test(node.textContent)));
  assert.ok(fields().some(node => /Докази застаріли/.test(node.textContent)));
  assert.ok(fields().some(node => /журналі джерел/.test(node.textContent)));
  assert.equal(byText("Зберегти чернетку"), undefined);
  b.vm.row = {...b.vm.row, draft_available: true, candidates: [
    {...candidate, eligibility: "register", registration_key: "observation"},
  ]};
  b.run("renderDetail(row)");
  assert.ok(byText("Зберегти чернетку"));
  assert.equal(byText("Підтвердити переклад"), undefined);
  fields().find(node => node.tag === "input").value = "Reviewer";
  const select = fields().find(node => node.tag === "select");
  select.value = "observation";
  select.events.change();
  byText("Додати кандидат до журналу").events.click();
  await flush();
  assert.equal(b.requests.find(entry => entry.action === "register_candidate").candidate, "observation");
});

test("mapping form passes exact metadata only after two distinct attestations", async () => {
  const b = browser((action, body) => action === "list" ? listing(body.module) :
    {module: body.module, build: "review_saved"});
  await flush();
  const item = {
    source_id: "quest:horde:42:accept", target_id: fixture.id, source_text: "Привіт.",
    facts: {npc_id: 42, npc_type: "creature", voice: "fixture", faction: "horde",
      wording_sha256: "fingerprint", source: "accept", quest_id: 42,
      player_gender: null, english_original: "Hello."},
    evidence: {source_reference: "pinned source", target_reference: "pinned target"},
  };
  b.vm.row = {...fixture, candidates: [], mapping_options: [item]};
  b.run("renderDetail(row)");
  const fields = b.el("selected").all();
  const select = fields.find(node => node.tag === "select");
  const inputs = fields.filter(node => node.tag === "input");
  const form = fields.find(node => node.tag === "fieldset");
  const button = fields.find(node => node.textContent === "Підтвердити зіставлення");
  assert.equal(button.disabled, true);
  select.value = "0";
  select.events.change();
  inputs[0].value = inputs[2].value = "Reviewer A";
  inputs[1].checked = inputs[3].checked = true;
  form.events.input();
  assert.equal(button.disabled, true);
  inputs[2].value = "Reviewer B";
  form.events.input();
  assert.equal(button.disabled, false);
  button.events.click();
  await flush();
  const request = b.requests.find(entry => entry.action === "review_mapping");
  assert.equal(request.join.proof.evidence_reviewer, "Reviewer A");
  assert.equal(request.join.mapping_reviewer, "Reviewer B");
  assert.equal(request.join.proof.facts.npc_id, 42);
  assert.equal(request.join.proof.source_reference, "pinned source");
  assert.equal(request.join.proof.facts.english_original, undefined);
});

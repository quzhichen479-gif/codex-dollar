const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const catalog = require("../src/codex_meter/static/benchmarks.js");
const staticDir = path.join(__dirname, "../src/codex_meter/static");

test("each question can be transported to ChatGPT without answers or local data", () => {
  const ids = new Set();
  for (const question of catalog.questions) {
    assert.ok(question.id && !ids.has(question.id));
    ids.add(question.id);
    assert.ok(question.prompt.trim());
    assert.ok(question.rubric.length && question.reference);
    const url = new URL(catalog.chatgptUrl(question.prompt));
    assert.equal(url.origin, "https://chatgpt.com");
    assert.deepEqual([...url.searchParams.keys()], ["q"]);
    assert.equal(url.searchParams.get("q"), question.prompt);
    assert.ok(!question.prompt.includes(question.reference));
    assert.equal(url.hash, "");
  }
  assert.ok(ids.has("pelican-svg"));
  assert.ok(ids.has("pelican-animation"));
});

test("prompt punctuation cannot add URL parameters or fragments", () => {
  const prompt = '鹈鹕 &model=fake#fragment?next=https://example.invalid/\n"<svg>100%</svg>"';
  const url = new URL(catalog.chatgptUrl(prompt));
  assert.equal(url.origin, "https://chatgpt.com");
  assert.deepEqual([...url.searchParams.entries()], [["q", prompt]]);
  assert.equal(url.hash, "");
});

test("browser catalog loads offline and agrees with the CommonJS catalog", () => {
  const sandbox = {};
  vm.runInNewContext(fs.readFileSync(path.join(staticDir, "benchmarks.js"), "utf8"), sandbox);
  assert.deepEqual(JSON.parse(JSON.stringify(sandbox.CODEX_BENCHMARKS.questions)), catalog.questions);
  assert.equal(sandbox.CODEX_BENCHMARKS.chatgptUrl("test"), catalog.chatgptUrl("test"));
});

test("dashboard script remains valid standalone JavaScript", () => {
  assert.doesNotThrow(() => new vm.Script(fs.readFileSync(path.join(staticDir, "app.js"), "utf8")));
});

function dashboardWithFailedReport(clipboard) {
  const elements = new Map();
  for (const match of fs.readFileSync(path.join(staticDir, "index.html"), "utf8").matchAll(/id="([^"]+)"/g)) {
    const classes = new Set(["hidden"]);
    elements.set(`#${match[1]}`, {
      innerHTML: "", textContent: "", value: "", handlers: {},
      classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
      addEventListener(name, listener) { this.handlers[name] = listener; },
      focus() { this.focused = true; },
      select() { this.selected = true; },
      setSelectionRange(start, end) { this.selection = [start, end]; },
    });
  }
  const requests = [];
  vm.runInNewContext(fs.readFileSync(path.join(staticDir, "app.js"), "utf8"), {
    window: { CODEX_BENCHMARKS: catalog, setInterval() {} },
    navigator: { clipboard },
    document: { querySelector: selector => elements.get(selector), querySelectorAll: () => [] },
    fetch: async url => { requests.push(url); throw new Error("Report unavailable"); },
  });
  return { elements, requests };
}

test("questions remain usable on report failure and copy only the selected prompt", async () => {
  const copied = [];
  const { elements, requests } = dashboardWithFailedReport({ writeText: async text => copied.push(text) });
  await new Promise(resolve => setImmediate(resolve));
  assert.match(elements.get("#alert").textContent, /Report unavailable/);
  assert.match(elements.get("#benchmarkGrid").innerHTML, /鹈鹕骑自行车/);
  const button = { dataset: { copyBenchmark: "pelican-svg" }, closest() { return this; } };
  await elements.get("#benchmarkGrid").handlers.click({ target: button });
  assert.deepEqual(copied, [catalog.questions.find(q => q.id === "pelican-svg").prompt]);
  assert.match(elements.get("#benchmarkStatus").textContent, /已复制/);
  assert.equal(button.disabled, false);
  assert.deepEqual(requests, ["/api/report"]);
});

test("denied clipboard exposes a selected manual copy area and restores focus on close", async () => {
  const { elements } = dashboardWithFailedReport({ writeText: async () => { throw new Error("Denied"); } });
  const button = { dataset: { copyBenchmark: "bounded-two-lies" }, closest() { return this; }, focus() { this.focused = true; } };
  await elements.get("#benchmarkGrid").handlers.click({ target: button });
  const textarea = elements.get("#benchmarkCopyText");
  assert.equal(textarea.value, catalog.questions.find(q => q.id === "bounded-two-lies").prompt);
  assert.equal(textarea.focused, true);
  assert.deepEqual(textarea.selection, [0, textarea.value.length]);
  assert.equal(elements.get("#benchmarkManualCopy").classList.contains("hidden"), false);
  assert.equal(button.disabled, false);
  elements.get("#benchmarkCloseCopy").handlers.click();
  assert.equal(elements.get("#benchmarkManualCopy").classList.contains("hidden"), true);
  assert.equal(button.focused, true);
});

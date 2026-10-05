const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const staticDir = path.join(root, "src/codex_meter/static");
const script = fs.readFileSync(path.join(staticDir, "app.js"), "utf8");
// Exercise the real empty report schema without reading any user sessions.
const emptyReport = JSON.parse(execFileSync(process.env.CODEX_METER_PYTHON || "python", ["-c",
  "import json; from codex_meter.pricing import PriceBook; from codex_meter.report import build_report; print(json.dumps(build_report({'events': []}, PriceBook.default())))",
], { cwd: root, env: { ...process.env, PYTHONPATH: path.join(root, "src") }, encoding: "utf8" }));

function dashboard({ embedded = false, fail = false } = {}) {
  const elements = new Map();
  for (const match of fs.readFileSync(path.join(staticDir, "index.html"), "utf8").matchAll(/id="([^"]+)"/g)) {
    const classes = new Set(["hidden"]);
    elements.set(`#${match[1]}`, {
      innerHTML: "", textContent: "", value: "", handlers: {}, style: {},
      classList: {
        add: name => classes.add(name), remove: name => classes.delete(name),
        toggle(name, force) { if (force) classes.add(name); else classes.delete(name); },
        contains: name => classes.has(name),
      },
      addEventListener(name, handler) { this.handlers[name] = handler; },
    });
  }
  const requests = [], intervals = [];
  vm.runInNewContext(script, {
    window: { __CODEX_METER_REPORT__: embedded ? emptyReport : undefined,
      setInterval: (fn, ms) => intervals.push({ fn, ms }) },
    document: { querySelector: selector => elements.get(selector), querySelectorAll: () => [],
      visibilityState: "visible" },
    fetch: async url => {
      requests.push(url);
      if (fail) throw new Error("Report unavailable");
      return { ok: true, json: async () => emptyReport };
    },
  });
  return { elements, requests, intervals };
}

const tick = () => new Promise(resolve => setImmediate(resolve));

test("offline dashboard renders current ledgers with no network or question bank", async () => {
  const { elements, requests, intervals } = dashboard({ embedded: true });
  await tick();
  assert.equal(elements.get("#alert").textContent, "");
  assert.match(elements.get("#periodLabel").textContent, /无调用记录/);
  assert.match(elements.get("#apiLedger").innerHTML, /gpt-6\.1-sol/);
  assert.match(elements.get("#subscriptionLedger").innerHTML, /Ultrafast ×6/);
  assert.match(elements.get("#retrievedAt").textContent, /2026-10-05/);
  assert.equal(elements.get("#refreshButton").disabled, true);
  assert.equal(elements.has("#benchmarks"), false);
  assert.deepEqual(requests, []);
  assert.deepEqual(intervals, []);
});

test("live dashboard renders and refreshes without the removed catalog", async () => {
  const { elements, requests, intervals } = dashboard();
  await tick();
  assert.equal(elements.get("#alert").textContent, "");
  assert.equal(elements.get("#refreshButton").disabled, false);
  await elements.get("#refreshButton").handlers.click();
  assert.deepEqual(requests, ["/api/report", "/api/report?refresh=1"]);
  assert.equal(intervals[0].ms, 60000);
});

test("failed report remains retryable after removing the question UI", async () => {
  const { elements } = dashboard({ fail: true });
  await tick();
  assert.match(elements.get("#alert").textContent, /Report unavailable/);
  assert.equal(elements.get("#refreshButton").disabled, false);
});

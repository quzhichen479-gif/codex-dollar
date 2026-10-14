const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const dir = path.join(__dirname, "../src/codex_meter/static");
const tick = () => new Promise(resolve => setImmediate(resolve));

function widget(data, { fail = false, native = false } = {}) {
  const elements = new Map();
  for (const [,id] of fs.readFileSync(path.join(dir,"widget.html"),"utf8").matchAll(/id="([^"]+)"/g)) {
    elements.set(id, {textContent:"", hidden:true, handlers:{}, value:0, attributes:{},
      classList:{ toggle() {} }, addEventListener(event, fn) { this.handlers[event] = fn; },
      setAttribute(key,value) { this.attributes[key] = value; }});
  }
  const timers = [], requests = [], calls = [];
  let pinned = true;
  const api = { toggle_pin:async () => (pinned = !pinned), show_dashboard:async () => calls.push("dashboard") };
  vm.runInNewContext(fs.readFileSync(path.join(dir,"widget.js"),"utf8"), {
    document: {getElementById: id => elements.get(id)},
    window: {addEventListener() {}, pywebview: native ? {api} : undefined},
    AbortController, setTimeout:(fn,ms) => timers.push({fn,ms}), clearTimeout() {},
    fetch:async url => { requests.push(url); if (fail) throw Error("offline"); return {ok:true,json:async () => data}; },
  });
  return { elements, timers, requests, calls };
}

function fixture() {
  return {speed:{output_tokens_per_second:48.5,input_tokens_per_second:200,output_tokens:2910,active_sessions:2},
    generated_at:"2026-10-14T12:00:00Z", latest_model:"gpt-6.1-sol", scan:{},
    quota:{timestamp:"2026-10-14T12:00:00Z",stale:false,plan_type:"pro", primary:null,
      secondary:{remaining_percent:72,window_minutes:10080,resets_at:"2026-10-18T12:00:00Z",expired:false}},
    last_turn:{output_tokens_per_second:86.2,time_to_first_token_ms:1200}};
}

test("widget renders token speed and a missing primary window without inventing quota", async () => {
  const {elements:e, timers,requests} = widget(fixture());
  await tick();
  assert.equal(e.get("outputSpeed").textContent,"48.5");
  assert.equal(e.get("primaryValue").textContent,"未提供");
  assert.equal(e.get("secondaryValue").textContent,"72%");
  assert.equal(e.get("secondaryBar").value,72);
  assert.equal(e.get("firstToken").textContent,"1.2 s");
  assert.equal(e.get("pinButton").hidden,true);
  assert.deepEqual(requests,["/api/live"]);
  assert.equal(timers.at(-1).ms,2000);
});
test("stale, expired, and absent quotas stay distinct", async () => {
  const data=fixture(); data.quota.stale=true; data.quota.primary={remaining_percent:3,expired:true};
  const {elements:e}=widget(data); await tick();
  assert.equal(e.get("primaryValue").textContent,"待新快照");
  assert.equal(e.get("primaryBar").value,0);
  assert.equal(e.get("secondaryValue").textContent,"72% · 旧");
  assert.match(e.get("quotaStatus").textContent,/重置/);
});
test("disconnection clears live speed, marks quota stale and schedules retry", async () => {
  const {elements:e,timers}=widget({}, {fail:true}); await tick();
  assert.equal(e.get("outputSpeed").textContent,"—");
  assert.match(e.get("statusText").textContent,/连接中断/);
  assert.match(e.get("quotaStatus").textContent,/过时/);
  assert.equal(e.get("refreshButton").disabled,false);
  assert.equal(timers.at(-1).ms,2000);
});
test("native pin and dashboard controls use only the desktop bridge", async () => {
  const {elements:e,calls}=widget(fixture(),{native:true}); await tick();
  assert.equal(e.get("pinButton").hidden,false);
  await e.get("pinButton").handlers.click();
  assert.equal(e.get("pinButton").attributes["aria-pressed"],"false");
  await e.get("dashboardLink").handlers.click({preventDefault(){}});
  assert.deepEqual(calls,["dashboard"]);
});
test("model labels are text, and zero credit balance remains visible", async () => {
  const data=fixture(); data.latest_model='<img src=x onerror=alert(1)>'; data.quota.credits={balance:"0"};
  const {elements:e}=widget(data); await tick();
  assert.equal(e.get("modelName").textContent,data.latest_model);
  assert.equal(e.get("balance").hidden,false);
  assert.match(e.get("balance").textContent, /：0$/);
});

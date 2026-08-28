(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  let report = null;
  let chartRange = 30;
  const embedded = Boolean(window.__CODEX_METER_REPORT__);

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const compact = (value) => {
    const n = Number(value || 0);
    return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 }).format(n);
  };
  const integer = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(Number(value || 0));
  const money = (value) => {
    const n = Number(value || 0);
    const digits = n < 0.01 ? 6 : n < 1 ? 4 : 2;
    return `$${n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  };
  const credits = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 3 });
  const percent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const dateTime = (value) => value ? new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZone: "UTC", hour12: false,
  }).format(new Date(value)).replaceAll("/", "-") + " UTC" : "—";
  const shortDate = (value) => value ? value.slice(5, 10) : "—";

  function showAlert(message, kind = "warn") {
    const el = $("#alert");
    if (!message) { el.classList.add("hidden"); return; }
    el.textContent = message;
    el.className = `alert ${kind === "error" ? "error" : ""}`;
  }

  function renderSummary() {
    const s = report.summary;
    const t = s.tokens;
    const cards = [
      { index: "TOK", label: "总 Token", value: compact(t.total_tokens), unit: "tokens", foot: `${integer(s.calls)} 次模型调用 · ${integer(s.sessions)} 个脱敏会话` },
      { index: "API", label: "API 标准模式等价", value: money(s.api_standard_equivalent_usd), unit: "USD", foot: "按调用日期选历史价；不是会员账单", highlight: true },
      { index: "SUB", label: "订阅 Credits 估算", value: credits(s.subscription_credits_estimate), unit: "credits", foot: "仅统计识别为订阅的调用；独立费率" },
      { index: "HIT", label: "缓存命中率", value: percent(s.cache_hit_ratio), unit: "of input", foot: `${compact(t.cached_input_tokens)} 个缓存输入 token` },
    ];
    $("#summaryGrid").innerHTML = cards.map(card => `
      <article class="kpi ${card.highlight ? "highlight" : ""}">
        <div class="kpi-label"><span>${escapeHtml(card.label)}</span><b>${card.index}</b></div>
        <div class="kpi-value">${escapeHtml(card.value)}<small>${escapeHtml(card.unit)}</small></div>
        <div class="kpi-foot">${escapeHtml(card.foot)}</div>
      </article>`).join("");

    const first = report.period.first_event ? dateTime(report.period.first_event) : "无调用记录";
    const last = report.period.last_event ? dateTime(report.period.last_event) : "";
    $("#periodLabel").textContent = last ? `${first}  →  ${last}` : first;

    const coverage = s.api_price_coverage;
    $("#coverageBadge").textContent = `API 价格覆盖 ${percent(coverage)}`;
    $("#coverageBadge").classList.toggle("accent", coverage >= 0.9999);
    if (coverage < 0.9999) {
      const names = Object.keys(report.unknown_pricing.api || {});
      showAlert(`有 ${integer(s.unpriced_api_tokens)} tokens 未计价：${names.join("、") || "未知模型"}。系统没有用相近模型价格猜测。`);
    } else if ((report.scan.failures || []).length) {
      showAlert(`有 ${report.scan.failures.length} 个日志文件无法读取；其内容未计入。`);
    } else {
      showAlert("");
    }
  }

  function renderLimit() {
    const current = report.current || {};
    const rate = current.rate_limit || {};
    const windowInfo = rate.primary || rate.secondary;
    const plan = current.plan_reference;
    const badge = $("#planBadge");
    if (plan) {
      badge.textContent = `${plan.label} · ${money(plan.monthly_usd)}/月`;
      badge.title = `映射可信度：${plan.confidence || "未知"}`;
    } else {
      badge.textContent = current.detected_plan_type ? `日志套餐 ${current.detected_plan_type}` : "未识别套餐";
    }
    if (!windowInfo || windowInfo.remaining_percent == null) {
      $("#limitContent").innerHTML = `<div class="no-limit"><div><strong>没有可用的官方限额快照</strong><span>API Key 会话通常按用量计费；订阅会话可在 Codex 中用 /status 查看。</span></div></div>`;
      return;
    }
    const remaining = Number(windowInfo.remaining_percent);
    const reset = windowInfo.resets_at ? dateTime(windowInfo.resets_at) : "未知";
    const minutes = Number(windowInfo.window_minutes || 0);
    const windowLabel = minutes >= 10080 ? `${Math.round(minutes / 10080)} 周` : minutes >= 1440 ? `${Math.round(minutes / 1440)} 天` : `${minutes} 分钟`;
    const balance = rate.credits && rate.credits.balance != null ? rate.credits.balance : "—";
    $("#limitContent").innerHTML = `
      <div class="limit-main">
        <div class="gauge" style="--value:${remaining}%"><div class="gauge-center"><strong>${remaining.toFixed(1)}%</strong><small>窗口剩余</small></div></div>
        <div class="limit-copy">
          <h3>${escapeHtml(plan ? plan.label : (rate.plan_type || "Codex"))}</h3>
          <p>这是 Codex 日志返回的官方限额百分比，比把套餐硬换算成固定 token 包更可靠。</p>
          <div class="limit-meta">
            <div><span>窗口长度</span><strong>${escapeHtml(windowLabel)}</strong></div>
            <div><span>重置时间</span><strong>${escapeHtml(reset)}</strong></div>
            <div><span>额外 credits 余额</span><strong>${escapeHtml(balance)}</strong></div>
            <div><span>快照时间</span><strong>${escapeHtml(dateTime(rate.timestamp))}</strong></div>
          </div>
        </div>
      </div>`;
  }

  function renderComposition() {
    const t = report.summary.tokens;
    const cached = Number(t.cached_input_tokens || 0);
    const writes = Number(t.cache_write_input_tokens || 0);
    const input = Math.max(0, Number(t.input_tokens || 0) - cached - writes);
    const output = Number(t.output_tokens || 0);
    const max = Math.max(cached, input + writes, output, 1);
    const rows = [
      { label: "缓存输入", value: cached, klass: "cached" },
      { label: "非缓存 / 写缓存输入", value: input + writes, klass: "input" },
      { label: "输出（含 reasoning）", value: output, klass: "output" },
    ];
    $("#cacheBadge").textContent = `缓存命中 ${percent(report.summary.cache_hit_ratio)}`;
    $("#tokenComposition").innerHTML = rows.map(row => `
      <div class="composition-row">
        <div class="composition-label"><span>${escapeHtml(row.label)}</span><span>${integer(row.value)}</span></div>
        <div class="bar-track"><div class="bar-fill ${row.klass}" style="width:${Math.max(0.7, row.value / max * 100)}%"></div></div>
      </div>`).join("") + `<div class="composition-note">Reasoning token 已包含在 output_tokens 中，因此不会重复收费。输入总量按日志/官方 Usage 口径包含缓存与写缓存 token。</div>`;
  }

  function renderDaily() {
    const all = report.daily || [];
    const rows = chartRange === "all" ? all : all.slice(-Number(chartRange));
    const max = Math.max(...rows.map(d => Number(d.tokens.total_tokens || 0)), 1);
    if (!rows.length) {
      $("#dailyChart").innerHTML = `<div class="empty">所选区间没有调用记录</div>`;
      return;
    }
    $("#dailyChart").innerHTML = rows.map((day, index) => {
      const t = day.tokens;
      const cached = Number(t.cached_input_tokens || 0);
      const writes = Number(t.cache_write_input_tokens || 0);
      const rawInput = Math.max(0, Number(t.input_tokens || 0) - cached - writes) + writes;
      const output = Number(t.output_tokens || 0);
      const total = Math.max(1, cached + rawInput + output);
      const height = Math.max(2, total / max * 100);
      const showLabel = index === 0 || index === rows.length - 1 || (rows.length <= 12 && index % 3 === 0);
      const title = `${day.date} · ${integer(total)} tokens · ${money(day.api_equivalent_usd)} API 等价`;
      return `<div class="day-column" title="${escapeHtml(title)}">
        <div class="day-bar" style="height:${height}%">
          <div class="day-segment cached" style="height:${cached / total * 100}%"></div>
          <div class="day-segment input" style="height:${rawInput / total * 100}%"></div>
          <div class="day-segment output" style="height:${output / total * 100}%"></div>
        </div>${showLabel ? `<span class="day-label">${shortDate(day.date)}</span>` : ""}
      </div>`;
    }).join("");
  }

  function renderLedgers() {
    const apiRows = (report.pricing_ledger.api || []).filter(row => row.model.startsWith("gpt-5.6"));
    $("#apiLedger").innerHTML = apiRows.map((row, index, list) => {
      const r = row.rates;
      const nextSameModel = list.find((candidate, j) => j > index && candidate.model === row.model);
      const cut = nextSameModel ? `<span class="price-cut">后续降价</span>` : `<span>当前/最新</span>`;
      return `<div class="ledger-row">
        <strong>${escapeHtml(row.model)}</strong>
        <span>${escapeHtml(row.effective_from.slice(0, 10))}<br>${cut}</span>
        <code>in ${r.input} · cache ${r.cached_input}<br>out ${r.output}</code>
      </div>`;
    }).join("");

    const creditRows = report.pricing_ledger.subscription || [];
    $("#subscriptionLedger").innerHTML = creditRows.map(row => {
      const r = row.credits;
      return `<div class="ledger-row">
        <strong>${escapeHtml(row.model)}</strong>
        <span>独立 credits<br>Fast ×${escapeHtml(row.fast_multiplier)}</span>
        <code>in ${r.input} · cache ${r.cached_input}<br>out ${r.output}</code>
      </div>`;
    }).join("");
  }

  function renderModels() {
    const rows = report.models || [];
    if (!rows.length) {
      $("#modelRows").innerHTML = `<tr><td colspan="8" class="empty">没有模型用量</td></tr>`;
      return;
    }
    $("#modelRows").innerHTML = rows.map(row => {
      const t = row.tokens;
      const ok = row.api_priced && row.credits_priced;
      return `<tr>
        <td><span class="model-name">${escapeHtml(row.model)}</span></td>
        <td>${integer(row.calls)}</td>
        <td>${integer(t.input_tokens)}</td>
        <td class="muted">${integer(t.cached_input_tokens)}</td>
        <td>${integer(t.output_tokens)}</td>
        <td>${money(row.api_equivalent_usd)}</td>
        <td>${credits(row.subscription_credits)}</td>
        <td><span class="status ${ok ? "" : "warn"}">${ok ? "已计价" : "部分/未计价"}</span></td>
      </tr>`;
    }).join("");
  }

  function modeLabel(map) {
    return Object.entries(map || {}).sort((a, b) => b[1] - a[1]).map(([key]) => key).join(" / ");
  }

  function renderSessions() {
    const query = ($("#sessionSearch").value || "").trim().toLowerCase();
    const all = report.sessions || [];
    const filtered = all.filter(row => {
      const haystack = `${row.id} ${Object.keys(row.models || {}).join(" ")} ${modeLabel(row.billing_modes)}`.toLowerCase();
      return !query || haystack.includes(query);
    });
    const visible = filtered.slice(0, 100);
    $("#sessionRows").innerHTML = visible.length ? visible.map(row => `
      <tr>
        <td><span class="model-name">${escapeHtml(row.id)}</span></td>
        <td class="muted">${escapeHtml(dateTime(row.last_at))}</td>
        <td>${escapeHtml(Object.keys(row.models || {}).join("、"))}</td>
        <td>${integer(row.calls)}</td>
        <td>${integer(row.tokens.total_tokens)}</td>
        <td>${money(row.api_equivalent_usd)}</td>
        <td>${credits(row.subscription_credits)}</td>
      </tr>`).join("") : `<tr><td colspan="7" class="empty">没有匹配会话</td></tr>`;
    $("#sessionCount").textContent = `显示 ${visible.length} / ${filtered.length} 个匹配会话；报告最多渲染前 100 条，原始路径与会话 UUID 未导出。`;
  }

  function renderNotes() {
    $("#caveatList").innerHTML = (report.caveats || []).map(note => `<li>${escapeHtml(note)}</li>`).join("");
    $("#sourceList").innerHTML = (report.sources || []).map(source => `
      <a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(source.label)}</a>`).join("");
    const retrieved = report.pricing_ledger.retrieved_at || {};
    $("#retrievedAt").textContent = `价格表核对日期：API ${retrieved.api || "—"} · 订阅 ${retrieved.subscription || "—"}`;
  }

  function render() {
    renderSummary();
    renderLimit();
    renderComposition();
    renderDaily();
    renderLedgers();
    renderModels();
    renderSessions();
    renderNotes();
  }

  async function load(refresh = false) {
    const button = $("#refreshButton");
    button.disabled = true;
    button.textContent = refresh ? "扫描中…" : "读取中…";
    try {
      if (embedded) {
        report = window.__CODEX_METER_REPORT__;
      } else {
        const response = await fetch(`/api/report${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        report = await response.json();
      }
      render();
    } catch (error) {
      showAlert(`读取报告失败：${error.message}`, "error");
    } finally {
      button.disabled = embedded;
      button.textContent = embedded ? "离线报告" : "重新扫描";
      if (embedded) button.title = "单文件离线报告不支持重新扫描；请重新运行 report 命令。";
    }
  }

  $$("[data-range]").forEach(button => button.addEventListener("click", () => {
    chartRange = button.dataset.range === "all" ? "all" : Number(button.dataset.range);
    $$("[data-range]").forEach(item => item.classList.toggle("active", item === button));
    if (report) renderDaily();
  }));
  $("#sessionSearch").addEventListener("input", () => report && renderSessions());
  $("#refreshButton").addEventListener("click", () => !embedded && load(true));
  load(false);
})();

(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const number = value => value !== null && value !== undefined && value !== "" && typeof value !== "boolean" && Number.isFinite(Number(value)) ? Number(value) : null;
  const format = value => number(value) === null ? "—" : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  const time = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleTimeString("zh-CN", { hour12: false }) : "—";
  let loading = false, timer;

  function quotaWindow(key, value, stale) {
    const minutes = number(value?.window_minutes);
    $(key + "Label").textContent = minutes === 10080 ? "周额度" : minutes === 300 ? "5 小时额度" : minutes ? `${format(minutes >= 1440 ? minutes / 1440 : minutes / 60)} ${minutes >= 1440 ? "天" : "小时"}额度` : key === "primary" ? "短周期" : "周额度";
    const remaining = number(value?.remaining_percent);
    const valid = remaining !== null && !value?.expired;
    $(key + "Value").textContent = value?.expired ? "待新快照" : valid ? `${format(remaining)}%${stale ? " · 旧" : ""}` : "未提供";
    $(key + "Bar").value = valid ? Math.min(100, Math.max(0, remaining)) : 0;
    $(key + "Bar").classList.toggle("low", valid && remaining <= 20);
    const reset = value?.resets_at;
    $(key + "Reset").textContent = value?.expired ? "已到重置时间，等待官方更新" : reset ? `${new Date(reset).toLocaleString("zh-CN", { month:"numeric", day:"numeric", hour:"2-digit", minute:"2-digit" })} 重置` : "日志未提供重置时间";
  }

  function render(data) {
    const speed = data.speed || {}, quota = data.quota || {};
    $("outputSpeed").textContent = format(speed.output_tokens_per_second);
    $("inputSpeed").textContent = format(speed.input_tokens_per_second);
    $("sessionCount").textContent = `${format(speed.active_sessions)} 个近期会话 · 本机合计`;
    $("modelName").textContent = data.latest_model || "尚无用量记录";
    $("modelName").title = "最近记录的模型；速率合计本机全部会话";
    const recent = number(speed.output_tokens) > 0;
    $("stateDot").className = "dot" + (recent ? " live" : "");
    $("statusText").textContent = data.scan?.read_failures ? `有 ${data.scan.read_failures} 个日志无法读取，统计可能不完整` : recent ? "正在记录用量" : "近 60 秒暂无输出记录";
    $("planLabel").textContent = [quota.plan_type, quota.limit_name].filter(Boolean).join(" · ") || "官方快照";
    quotaWindow("primary", quota.primary, quota.stale);
    quotaWindow("secondary", quota.secondary, quota.stale);
    const expired = quota.primary?.expired || quota.secondary?.expired;
    $("quotaStatus").className = "quota-status" + (quota.stale || expired || quota.spend_control_reached ? " warn" : "");
    $("quotaStatus").textContent = quota.spend_control_reached ? "已达到官方支出控制限额" : !quota.timestamp ? "暂无官方快照；未提供的额度不会按 0 处理" : expired ? "快照已到重置时间，请等待 Codex 返回新额度" : quota.stale ? `旧快照 · ${time(quota.timestamp)}，不代表当前可用额度` : `官方快照 ${time(quota.timestamp)} · 非实时余额查询`;
    const credit = quota.credits || {};
    const balance = number(credit.balance);
    $("balance").hidden = !credit.unlimited && balance === null;
    $("balance").textContent = credit.unlimited ? "官方 credits：不限额" : `官方 credits 余额：${format(balance)}`;
    const turn = data.last_turn;
    $("turnSpeed").textContent = turn ? `${format(turn.output_tokens_per_second)} token/s` : "暂无完整回合";
    $("turnSpeed").title = turn ? `最近完成于 ${time(turn.timestamp)} · ${turn.model || ""}` : "旧日志可能没有回合计时字段";
    $("firstToken").textContent = number(turn?.time_to_first_token_ms) === null ? "未提供" : `${format(turn.time_to_first_token_ms / 1000)} s`;
    $("updatedAt").textContent = `扫描 ${time(data.generated_at)} · 2s 刷新`;
  }

  async function load() {
    if (loading) return;
    loading = true;
    clearTimeout(timer);
    $("refreshButton").disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/live", { cache:"no-store", signal:controller.signal });
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json();
      if (data.error || !data.speed) throw new Error("unavailable");
      render(data);
    } catch {
      $("stateDot").className = "dot error";
      $("statusText").textContent = "连接中断 · 正在自动重试";
      $("outputSpeed").textContent = "—";
      $("inputSpeed").textContent = "—";
      $("quotaStatus").className = "quota-status warn";
      $("quotaStatus").textContent = "无法刷新；保留的快照已过时，请勿视为当前额度";
      $("updatedAt").textContent = "刷新失败 · 2s 后重试";
    } finally {
      clearTimeout(timeout);
      loading = false;
      $("refreshButton").disabled = false;
      timer = setTimeout(load, 2000);
    }
  }

  function nativeReady() {
    if (window.pywebview?.api?.toggle_pin) {
      $("pinButton").hidden = false;
      $("windowHint").textContent = "桌面悬窗 · 拖动标题栏移动 · 可独立关闭";
    }
  }
  window.addEventListener("pywebviewready", nativeReady);
  nativeReady();
  $("pinButton").addEventListener("click", async () => {
    try {
      const pinned = await window.pywebview.api.toggle_pin();
      $("pinButton").textContent = pinned ? "已置顶" : "置顶";
      $("pinButton").setAttribute("aria-pressed", String(pinned));
    } catch { $("windowHint").textContent = "置顶切换失败，请重试"; }
  });
  $("dashboardLink").addEventListener("click", async event => {
    if (window.pywebview?.api?.show_dashboard) {
      event.preventDefault();
      try { await window.pywebview.api.show_dashboard(); }
      catch { $("windowHint").textContent = "仪表盘打开失败，请重试"; }
    }
  });
  $("refreshButton").addEventListener("click", load);
  window.addEventListener("beforeunload", () => clearTimeout(timer));
  load();
})();

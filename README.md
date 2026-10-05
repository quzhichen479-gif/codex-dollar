<div align="center">
  <img src="assets/codex-dollar.svg" width="112" alt="Codex Dollar logo">
  <h1>Codex Dollar</h1>
  <p>本地统计 Codex token，用 OpenAI 官方价格核算 API 等价金额与订阅 credits。</p>
</div>

> [!IMPORTANT]
> Codex Dollar 把「API 美元价格」和「ChatGPT/Codex 订阅」放在两本独立账本里。API 降价只更新 API 历史价格，不会自动降低 Plus、Pro、Business 等会员月费，也不会改写订阅 credits 费率。

## 它能做什么

- 扫描本机 `~/.codex/sessions` 与 `~/.codex/archived_sessions` 中的 JSONL 用量事件。
- 统计输入、缓存输入、写缓存、输出与 reasoning token，避免重复相加。
- 按每次调用的发生日期匹配官方 API 历史价格，正确处理 API 降价。
- 独立计算 Codex 订阅 credits，并显示日志中最近的官方限额剩余百分比。
- 持续监督 7 天额度窗口，把百分比变化与同期 token 关联，推算整周 API 美元等价、credits 和 token 等价。
- 识别 Fast/Priority、Batch/Flex 和超过 272k 输入 token 的长上下文倍率。
- 提供桌面 App、本地网页仪表盘、离线 HTML、JSON 和终端摘要。
- 未知模型明确标为「未计价」，不会套用相似模型价格猜测。
- 支持 GPT-6.1 Sol、GPT-6 Sol、GPT-6 Luna 与 Astra，包含缓存、长上下文、Fast 及 Astra Ultrafast 计价。

所有扫描和计算都在本机完成。项目不读取 `auth.json`，不上传提示词，不连接第三方中转，也不使用 sub2api 一类非官方渠道。

## 下载桌面 App

前往 [GitHub Releases](https://github.com/quzhichen479-gif/codex-dollar/releases) 下载对应系统的压缩包：

- Windows：解压后运行 `Codex-Dollar.exe`
- macOS：解压后运行 `Codex-Dollar.app`

发布包由 GitHub Actions 从本仓库源码构建。目前没有商业代码签名；如果系统拦截未知发布者，请先核对下载来源与 Release 中的构建记录，也可以按下文从源码运行。

## 从源码运行

需要 Python 3.10 或更高版本。统计、报告和浏览器仪表盘没有第三方运行依赖。

### Windows

```powershell
git clone https://github.com/quzhichen479-gif/codex-dollar.git
cd codex-dollar
./start-dashboard.ps1
```

脚本会优先使用 `CODEX_METER_PYTHON`，其次尝试 Codex 桌面版自带 Python，最后尝试系统 `python`/`python3`。要使用原生桌面窗口而不是浏览器回退：

```powershell
python -m pip install -e ".[desktop]"
codex-dollar app
```

### macOS / Linux

```bash
git clone https://github.com/quzhichen479-gif/codex-dollar.git
cd codex-dollar
chmod +x run.sh
./run.sh app
```

安装原生窗口依赖：

```bash
python3 -m pip install -e ".[desktop]"
codex-dollar app
```

未安装 `pywebview` 时，`app` 命令会自动在默认浏览器打开只监听 `127.0.0.1` 的本地 App。

## 常用命令

不安装也可以使用仓库内脚本：

```powershell
# 本地桌面/浏览器 App
./run.ps1 app

# 终端摘要
./run.ps1 scan

# 生成完全离线、可单独打开的 HTML 报告
./run.ps1 report -o codex-usage-report.html

# 导出脱敏 JSON
./run.ps1 scan --json --output codex-usage.json

# 只统计 2026 年 8 月
./run.ps1 scan --since 2026-08-01 --until 2026-09-01

# 检查日志可读性和官方价格表约束
./run.ps1 doctor
./run.ps1 prices --check
```

安装项目后，把 `./run.ps1` 换成 `codex-dollar` 即可。完整参数：

```text
codex-dollar {app,scan,report,serve,doctor,prices} --help
```

### 计费模式覆盖

默认 `--billing-mode auto` 会根据日志中的 `plan_type` 保守判断某次调用属于订阅还是 API。无法判断时归入 `unknown`，但仍展示「API 标准模式等价金额」。如果你的全部日志都来自 API Key 或订阅，可以显式覆盖：

```powershell
./run.ps1 scan --billing-mode api
./run.ps1 scan --billing-mode subscription
```

套餐名称只影响固定月费参考卡，不改变 token 费率。保留 `pro_5x` / `pro_20x` 参数以兼容旧命令，分别显示 Pro $100 / $200；新增 `pro_500`。通用日志标签 `pro` 无法区分三档价格，请按实际套餐显式指定：

```powershell
./run.ps1 app --plan plus
./run.ps1 app --plan pro_20x
./run.ps1 app --plan pro_500
```

## 周额度监督

App 运行时每 60 秒重新扫描一次脱敏用量事件。检测到 7 天窗口后，它会把两个额度快照之间的百分比变化与同期本地订阅 token 对齐：

```text
整周 API 美元等价 ≈ 同期 token 的官方 API Standard 等价金额 ÷ 百分比变化 × 100
整周 credits 等价  ≈ 同期订阅 credits ÷ 百分比变化 × 100
整周 token 等价    ≈ 同期 token 数 ÷ 百分比变化 × 100
```

例如，本周额度从 10% 增长到 20%，期间本地 token 按官方 API Standard 价格折合 $18，则在相同模型组合下，100% 周额度约等于 `$18 ÷ 10 × 100 = $180`。

监督器还会：

- 自动识别 `primary` 或 `secondary` 中的 10,080 分钟周窗口；
- 在额度重置、套餐或限额类型变化后重新建立样本；
- 排除明确属于 API Key 的调用，因为它们不消耗订阅额度；
- 对整数百分比的约 ±1 个百分点误差给出估算上下界；
- 使用同套餐最近的非重叠样本生成历史校准值；
- 展示样本百分比、同期 token、价格覆盖率和高/中/低可信度。

美元结果始终标记为「API 等价」，不是会员的现金价值。ChatGPT Work、云端任务、其它设备、图像生成或未知模型可能改变额度百分比，却不一定出现在本机 token 日志里；这类情况会降低关联质量。完整算法见 [docs/WEEKLY_MONITOR.md](docs/WEEKLY_MONITOR.md)。

## 怎样理解结果

| 指标 | 含义 |
|---|---|
| API 标准模式等价 | 把所有已知模型用量按发生日期的官方 Standard API 价格折算；这是比较值，不等于订阅账单 |
| API 预计费用 | 仅累计明确识别为 API Key 的调用，并应用日志中的服务等级倍率 |
| 订阅 credits 等价 | 仅累计识别为订阅的调用，按官方付费 credits 表折算；不是实际扣款，也不是套餐内已扣额度 |
| 官方限额快照 | Codex 日志最近一次返回的窗口剩余百分比与重置时间；这是会员剩余额度最可靠的本地信号 |
| 当前周额度推算 | 用当前周百分比变化与同期本地 token 反推的 100% 周额度 API 美元等价，并给出取整区间与可信度 |
| 同套餐历史校准 | 汇总同一套餐最近的非重叠有效样本，减少当前样本只有 1–2% 时的剧烈波动 |
| 价格覆盖率 | 有公开官方价格的 token 占比；未知模型不会被猜价 |

Plus、Pro、Business 的包含用量会受模型、上下文、任务复杂度与 Fast 模式等因素影响，官方并未把它们定义为一个固定 token 包。因此本项目不会用月费除以 API 单价来虚构「会员共有多少 token」。需要精确账务时：

- 订阅限额以 Codex `/status` 和 App 中的官方限额快照为准。
- API 财务对账以 OpenAI Usage Dashboard、Costs API 或正式发票为准。

## 计价原则

核心公式（各输入桶互斥）：

```text
费用 = 非缓存输入 × input_rate
     + 缓存输入   × cached_input_rate
     + 写缓存输入 × cache_write_rate
     + 输出       × output_rate
```

- `input_tokens` 在日志中包含缓存输入和写缓存输入，程序会先拆桶再计价。
- `output_tokens` 已包含 reasoning token，不会再重复收费。
- 超过 272k 输入 token 的 GPT-6.1 Sol / GPT-6 系列 / GPT-5.6/5.5/5.4 调用按官方长上下文规则计算。
- API Fast/Priority 为 Standard 的 2×；Batch/Flex 为 0.5×；Astra Ultrafast 自 2026-09-29 起为 6×。
- 付费 credits：Fast 为 2×，Astra Ultrafast 为 6×。套餐内额度消耗分别为 2.5× / 8×，不能套入付费 credits。
- v0.5.0 修正旧版把套餐内 Fast 倍率用于 credits 的口径错误，因此历史 Fast 的 credits 折算值也会修正；模型基础费率及 API 历史价格不变。官方未给出该口径说明的独立变价日，项目不编造变价日期。
- 未知模型、服务等级或早于支持日期的组合明确保持未计价，不回退为标准价。
- 地区处理加价、Web Search、容器、图像等无法从 token 日志可靠还原的项目不做推测。

完整价格历史、更新步骤和来源约束见 [docs/PRICE_LEDGER.md](docs/PRICE_LEDGER.md)。

## 隐私与安全

扫描器以流式方式读取 JSONL，只有包含 `turn_context`、`thread_settings_applied` 或 `token_count` 的行才会进入 JSON 解析。生成的报告：

- 不包含提示词、回复正文、会话标题或工作区路径；
- 不包含真实会话 UUID，只包含单向哈希后的短标识；
- 不读取 API Key、登录凭据、SQLite 数据库或 `auth.json`；
- 统计和报告不发起外部网络请求；本地服务只绑定 `127.0.0.1`；
- 价格来源由官方域名白名单校验，第三方价格源会让程序拒绝启动。

更多信息见 [SECURITY.md](SECURITY.md)。离线 HTML/JSON 报告虽然已脱敏，仍可能暴露模型用量与消费习惯，分享前请自行评估。

## 开发与测试

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
node --test tests/test_dashboard.cjs
python -m codex_meter prices --check
python -m codex_meter doctor
```

桌面构建：

```bash
python -m pip install -e ".[desktop,build]"
python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name Codex-Dollar --collect-all codex_meter src/codex_meter/app_entry.py
```

每次推送和 Pull Request 都会运行测试；`v*` 标签会构建 Windows/macOS App 并创建 GitHub Release。

## 官方来源

- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)
- [ChatGPT Work / Codex Pricing](https://learn.chatgpt.com/docs/pricing)
- [Codex speed 与 credits 倍率](https://learn.chatgpt.com/docs/agent-configuration/speed)
- [OpenAI Organization Usage API](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage)

最新补充核对：2026-10-05（GPT-6.1 Sol、GPT-6 Sol/Luna、Astra Ultrafast 和 credits 倍率；其他模型基础费率保留原来源和区间）。项目不会自动从网页抓价；价格变化必须通过人工核对官方页面、补充历史区间和测试后合并，避免今天的降价错误改写昨天的使用记录。

## 许可证

[Apache License 2.0](LICENSE)

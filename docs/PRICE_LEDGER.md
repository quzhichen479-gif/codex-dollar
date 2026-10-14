# 价格账本与更新规范

Codex Dollar 维护两份物理分离的数据文件：

- `src/codex_meter/data/api_prices.json`：API 美元价格历史。
- `src/codex_meter/data/subscription_credits.json`：ChatGPT/Codex 订阅 credits、Fast 倍率与固定月费参考。

这不是 UI 上的标签区分，而是两条独立计算路径。API 降价只能新增或结束 API 价格区间，不能修改订阅账本。

## 当前内置 API 价格

单位为 USD / 1M tokens；顺序是 input / cached input / cache write / output。

| 模型 | 生效区间（UTC） | 费率 |
|---|---|---|
| GPT-6.1 Sol | 2026-09-29 → 当前 | 2 / 0.1 / 2.5 / 10 |
| GPT-6 Sol | 2026-09-22 → 当前 | 2 / 0.2 / 2.5 / 10 |
| GPT-6 Luna | 2026-09-22 → 当前 | 0.1 / 0.01 / 0.125 / 0.5 |
| GPT-6 Astra | 2026-09-03 → 当前 | 10 / 1 / 12.5 / 50 |
| GPT-Rosalind-Research | 2026-10-05 → 当前 | 5 / 0.5 / 5 / 25 |
| GPT-5.6 Cyber | 2026-10-14（首次核实覆盖日）→ 当前 | 12.5 / 1.25 / 15.625 / 75 |
| GPT-5.6 Sol | 2026-07-09 → 2026-08-21 | 5 / 0.5 / 6.25 / 30 |
| GPT-5.6 Sol | 2026-08-21 → 当前 | 4 / 0.4 / 5 / 20 |
| GPT-5.6 Terra | 2026-07-09 → 2026-07-30 | 2.5 / 0.25 / 3.125 / 15 |
| GPT-5.6 Terra | 2026-07-30 → 当前 | 2 / 0.2 / 2.5 / 12 |
| GPT-5.6 Luna | 2026-07-09 → 2026-07-30 | 1 / 0.1 / 1.25 / 6 |
| GPT-5.6 Luna | 2026-07-30 → 当前 | 0.2 / 0.02 / 0.25 / 1.2 |

账本还保留 GPT-5.5、GPT-5.4、GPT-5.4 mini、GPT-5.2-Codex、GPT-5.1、GPT-5 与 codex-mini-latest 的官方记录，以便计算历史日志。数据文件本身是最终可执行明细。

Astra 的发布日期由官方 API Changelog 确认为 2026-09-03，费率由模型页面核对。官方没有给出当日具体发布时间，账本沿用以该日 UTC 00:00 为边界的日期粒度约定；早于该日的 Astra 日志保持未计价。只识别官方模型 ID `gpt-6-astra`，不推测 `gpt-6`、预览名称或其他别名。

以上新模型与 Astra 均按模型页面核验了缓存写入及长上下文价格。GPT-6 Sol / Luna 于 2026-09-22 发布，GPT-6.1 Sol 于 2026-09-29 发布；以 UTC 当日零点作为支持边界，不推测其他模型别名。

## 当前内置订阅 credits

单位为 credits / 1M tokens；顺序是 input / cached input / output。

| 模型 | credits | 付费 credits Fast 倍率 |
|---|---:|---:|
| GPT-6.1 Sol | 50 / 2.5 / 250 | 2× |
| GPT-6 Sol | 50 / 5 / 250 | 2× |
| GPT-6 Luna | 2.5 / 0.25 / 12.5 | 2× |
| GPT-6 Astra | 250 / 25 / 1,250 | 2× |
| GPT-Rosalind-Research | 125 / 12.5 / 625 | 未核实 |
| GPT-5.6 Cyber（Daybreak Red） | 312.5 / 31.25 / 1875 | 未核实 |
| GPT-5.6 Sol | 100 / 10 / 500 | 2× |
| GPT-5.6 Terra | 50 / 5 / 300 | 2× |
| GPT-5.6 Luna | 5 / 0.5 / 30 | 2× |
| GPT-5.5 | 125 / 12.5 / 750 | 2× |
| GPT-5.4 | 62.5 / 6.25 / 375 | 2× |
| GPT-5.4 mini | 18.75 / 1.875 / 113 | 2× |

官方订阅 credits 表没有单独的 cache-write 列。为避免低估，订阅估算把写缓存 token 归入普通 input；这个规则不会影响 API 账本。

订阅费率和服务等级倍率分别取自官方订阅 pricing/speed 页面，以模型发布日期作为首个支持的日志日期。这里计算的是订阅调用的**付费 credits 等价**，不是实际已扣 credits。日志不能可靠区分套餐包含用量与额外购买 credits 的逐次扣减。订阅 credits 不套用 API 的长上下文倍率，也不按 API 美元价格换算。

2026-10-05 核对时，官方明确区分 Fast 的付费 credits 2× 与套餐内额度 2.5×。v0.5.0 将旧版混入 credits 的 2.5× 修正为 2×，包括重新扫描历史调用时的估算。这是计价口径纠错，不声称发生了订阅降价；官方未给出独立变价日，项目不编造切换日期。原有 API 历史区间和订阅基础 token 费率保持不变。

## 2026-10-14 补充核对

- GPT-6.1 Sol Ultrafast：API 和订阅的官方发布记录均为 **2026-10-08**。API 短上下文 input / cached / write / output 为 **12 / 0.6 / 15 / 60 USD/1M**；长上下文为 **24 / 1.2 / 30 / 90**。付费 credits 为 Standard 的 6×，套餐内额度为 8×。沿用 UTC 当日零点作为日期粒度边界，不声称获知精确上线时刻。
- GPT-Rosalind-Research：API 官方明确从 **2026-10-05** 开始计费，且没有单独 cache-write 加价；写缓存输入按普通 input 费率处理。订阅表虽已公布 125 / 12.5 / 625 credits，但未确认该费率的历史起点，因此订阅账本仅从 **2026-10-14 首次核实日**覆盖，不照搬 API 生效日。
- GPT-5.6 Cyber：API 和订阅独立核实当前 Standard 价格，均仅从 **2026-10-14 首次核实日**覆盖。该日期不是模型发布日期或已知变价日。Daybreak Red 与该模型的对应关系以官方 Daybreak 指南为据，不推测别名。两种专用模型均未核实 Fast/Ultrafast/Batch/Flex 费率，相关用量保持未计价。
- GPT-5.5 于 **2026-10-14** 退出 ChatGPT/Work/Codex。保留历史 credits 费率并标注状态；API 不受影响。退役状态不用于抹去日志用量。
- GPT-6.1 Sol、GPT-6 Luna、Astra 的基础价格及 Fast/Ultrafast 双计费口径复核不变。未更改旧 API 生效区间。

## 长上下文与服务等级

对声明支持长上下文差异化价格的模型，当单次调用输入超过 272,000 token：

- input、cached input、cache write 费率乘 2；
- output 费率乘 1.5；
- 阈值按 `input_tokens` 判断，其中包含缓存和写缓存输入。

| 口径 | Standard | Fast / Priority | Astra / Sol Ultrafast |
|---|---:|---:|---:|
| API 美元 | 1× | 2× | 6× |
| 付费 credits | 1× | 2× | 6× |
| 套餐内额度消耗（仅供说明） | 1× | 2.5× | 8× |

已支持的通用模型 API Batch/Flex 为 0.5×。Ultrafast 支持 Astra（2026-09-29 起）和 GPT-6.1 Sol（2026-10-08 起）；各自支持日期之前及其他模型的 Ultrafast 保持未计价。API 的 Ultrafast 可以叠加官方长上下文倍率，订阅 credits 不叠加。专用模型仅覆盖已核实的 Standard 模式，不能直接套用通用倍率。模型、服务等级或日期不受账本支持时不回退为 Standard。

新增 Pro $500 月费参考和 `--plan pro_500`。日志的通用 `pro` 无法区分 $100 / $200 / $500，因此不再自动显示成 $200；用户可显式选择。套餐价格不会改变 token 费率或虚构固定 token 包。

## 为什么会员月费不随 API 降价

API 是按 token 与部分工具调用计费的独立产品。ChatGPT/Codex 会员则以固定月费换取由计划限制管理的使用权，并使用单独的 credits 口径。两者的费率、倍率和限额不是同一张价格表。因此：

1. API 降价只改变新 API 价格区间。
2. 历史 API 调用继续使用当时价格。
3. 会员固定月费和 credits 保持不变，除非官方订阅页面明确更新。
4. 不用会员月费除以 API 单价推算一个固定 token 包。

## 安全更新流程

1. 只接受 `https://developers.openai.com`、`https://platform.openai.com` 或 `https://learn.chatgpt.com` 上的 OpenAI 官方页面。
2. 用官方 API Pricing 页面确认当前价，用 API Changelog 确认生效日期和旧价格。
3. 在 API 账本中关闭旧区间的 `effective_to`，新增新区间；不要原地覆盖旧价。
4. 只有官方订阅 pricing/speed 页面发生明确变化时才修改订阅账本。
5. 更新 `retrieved_at`、来源链接、README 表格与覆盖生效边界的单元测试。
6. 运行：

   ```bash
   python -m unittest discover -s tests -v
   python -m codex_meter prices --check
   ```

7. 检查未知模型仍是未计价状态，不得使用近似值或第三方聚合价格补齐。

校验器会拒绝非 HTTPS、非官方白名单域名的来源。sub2api 仅作为禁止示例出现在策略字段与文档中，不是依赖、数据源或后备渠道。

## 官方来源

- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)
- [OpenAI Model catalog](https://developers.openai.com/api/docs/models)
- [GPT-6 Astra model pricing](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [ChatGPT Work / Codex Pricing](https://learn.chatgpt.com/docs/pricing)
- [Codex speed](https://learn.chatgpt.com/docs/agent-configuration/speed)

- [gpt-6.1-sol model pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [gpt-6-sol model pricing](https://developers.openai.com/api/docs/models/gpt-6-sol)
- [gpt-6-luna model pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Ultrafast API](https://developers.openai.com/api/docs/guides/ultrafast-mode)
- [ChatGPT / Codex 发布记录](https://learn.chatgpt.com/docs/changelog)
- [Daybreak 模型与访问计划](https://developers.openai.com/api/docs/guides/daybreak)
- [DevDay 2026 发布说明](https://learn.chatgpt.com/docs/whats-new/devday-2026)

本轮核对日期：2026-10-05。Astra 基础 token 费率与 2026-09-22 的记录一致；更早模型的基础费率与历史区间沿用原账本。

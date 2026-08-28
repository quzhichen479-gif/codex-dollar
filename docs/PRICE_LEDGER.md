# 价格账本与更新规范

Codex Dollar 维护两份物理分离的数据文件：

- `src/codex_meter/data/api_prices.json`：API 美元价格历史。
- `src/codex_meter/data/subscription_credits.json`：ChatGPT/Codex 订阅 credits、Fast 倍率与固定月费参考。

这不是 UI 上的标签区分，而是两条独立计算路径。API 降价只能新增或结束 API 价格区间，不能修改订阅账本。

## 当前内置 API 价格

单位为 USD / 1M tokens；顺序是 input / cached input / cache write / output。

| 模型 | 生效区间（UTC） | 费率 |
|---|---|---|
| GPT-5.6 Sol | 2026-07-09 → 2026-08-21 | 5 / 0.5 / 6.25 / 30 |
| GPT-5.6 Sol | 2026-08-21 → 当前 | 4 / 0.4 / 5 / 20 |
| GPT-5.6 Terra | 2026-07-09 → 2026-07-30 | 2.5 / 0.25 / 3.125 / 15 |
| GPT-5.6 Terra | 2026-07-30 → 当前 | 2 / 0.2 / 2.5 / 12 |
| GPT-5.6 Luna | 2026-07-09 → 2026-07-30 | 1 / 0.1 / 1.25 / 6 |
| GPT-5.6 Luna | 2026-07-30 → 当前 | 0.2 / 0.02 / 0.25 / 1.2 |

账本还保留 GPT-5.5、GPT-5.4、GPT-5.4 mini、GPT-5.2-Codex、GPT-5.1、GPT-5 与 codex-mini-latest 的官方记录，以便计算历史日志。数据文件本身是最终可执行明细。

## 当前内置订阅 credits

单位为 credits / 1M tokens；顺序是 input / cached input / output。

| 模型 | credits | Fast 倍率 |
|---|---:|---:|
| GPT-5.6 Sol | 100 / 10 / 500 | 2.5× |
| GPT-5.6 Terra | 50 / 5 / 300 | 2.5× |
| GPT-5.6 Luna | 5 / 0.5 / 30 | 2.5× |
| GPT-5.5 | 125 / 12.5 / 750 | 2.5× |
| GPT-5.4 | 62.5 / 6.25 / 375 | 2× |
| GPT-5.4 mini | 18.75 / 1.875 / 113 | 2× |

官方订阅 credits 表没有单独的 cache-write 列。为避免低估，订阅估算把写缓存 token 归入普通 input；这个规则不会影响 API 账本。

## 长上下文与服务等级

对声明支持长上下文差异化价格的模型，当单次调用输入超过 272,000 token：

- input、cached input、cache write 费率乘 2；
- output 费率乘 1.5；
- 阈值按 `input_tokens` 判断，其中包含缓存和写缓存输入。

API 服务等级倍率：Standard 1×、Fast/Priority 2×、Batch/Flex 0.5×。订阅 Fast 使用订阅账本中逐模型的倍率。

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
- [ChatGPT Work / Codex Pricing](https://learn.chatgpt.com/docs/pricing)
- [Codex speed](https://learn.chatgpt.com/docs/agent-configuration/speed)

最后核对：2026-08-28。

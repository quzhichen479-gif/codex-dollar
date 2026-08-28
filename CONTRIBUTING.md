# 参与贡献

感谢改进 Codex Dollar。请保持以下边界：

- 价格只引用 OpenAI 官方域名，且保留历史生效区间。
- API 与订阅账本必须独立；API 降价不能隐式修改会员费率。
- 不加入第三方代理、中转、凭据读取、遥测或日志上传。
- 未知模型保持未计价，除非已有可核验的官方价格。
- 新行为需要测试，涉及页面时也要检查窄屏布局和无数据状态。

本地检查：

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m codex_meter prices --check
python -m codex_meter doctor
```

价格变更请遵循 [docs/PRICE_LEDGER.md](docs/PRICE_LEDGER.md) 的更新流程，并在 Pull Request 中列出官方来源、有效时间和对历史数据的影响。

"""Chinese-friendly command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .pricing import PriceBook, parse_datetime
from .report import build_report
from .scanner import default_codex_home, discover_session_files, scan_codex
from .desktop import run_app
from .web import render_standalone, serve_dashboard


PLAN_CHOICES = (
    "free",
    "go",
    "plus",
    "pro_5x",
    "pro_20x",
    "business_annual",
    "business_monthly",
)


def _add_scan_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=None,
        help="Codex 数据目录；默认使用 CODEX_HOME 或 ~/.codex",
    )
    parser.add_argument("--active-only", action="store_true", help="不扫描 archived_sessions")
    parser.add_argument(
        "--billing-mode",
        choices=("auto", "api", "subscription"),
        default="auto",
        help="auto 根据官方限额快照判断；也可显式覆盖全部记录",
    )
    parser.add_argument("--since", help="起始时间（含），例如 2026-08-01")
    parser.add_argument("--until", help="结束时间（不含），例如 2026-09-01")
    parser.add_argument(
        "--plan",
        choices=PLAN_CHOICES,
        help="显式指定订阅套餐，只影响月费参考卡，不改变 token 计价",
    )


def _validate_dates(args: argparse.Namespace) -> None:
    try:
        start = parse_datetime(args.since) if getattr(args, "since", None) else None
        end = parse_datetime(args.until) if getattr(args, "until", None) else None
    except ValueError as exc:
        raise SystemExit(f"日期格式无效：{exc}") from exc
    if start and end and start >= end:
        raise SystemExit("--since 必须早于 --until")


def _build(args: argparse.Namespace, pricebook: PriceBook | None = None) -> dict[str, Any]:
    _validate_dates(args)
    book = pricebook or PriceBook.default()
    scan = scan_codex(
        args.codex_home,
        include_archived=not args.active_only,
        billing_mode=args.billing_mode,
    )
    return build_report(
        scan,
        book,
        since=args.since,
        until=args.until,
        plan_override=args.plan,
    )


def _format_int(value: int | float) -> str:
    return f"{int(value):,}"


def _print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    tokens = summary["tokens"]
    current = report.get("current", {})
    plan = current.get("plan_reference")
    print("Codex Token Meter")
    print(f"  统计区间: {report['period'].get('first_event') or '无记录'}  →  {report['period'].get('last_event') or '无记录'}")
    print(f"  会话 / 模型调用: {summary['sessions']} / {summary['calls']}")
    print(f"  输入 token: {_format_int(tokens['input_tokens'])}")
    print(f"    缓存命中: {_format_int(tokens['cached_input_tokens'])}")
    print(f"  输出 token: {_format_int(tokens['output_tokens'])}")
    print(f"  API 标准模式等价: ${summary['api_standard_equivalent_usd']:.6f}")
    print(f"  订阅内 credits 估算: {summary['subscription_credits_estimate']:.4f}")
    print(f"  API 价格覆盖率: {summary['api_price_coverage'] * 100:.2f}%")
    if plan:
        print(f"  当前套餐参考: {plan['label']} · ${plan['monthly_usd']:.2f}/月 ({plan['confidence']})")
    rate = current.get("rate_limit") or {}
    primary = rate.get("primary") or {}
    if primary.get("remaining_percent") is not None:
        print(f"  官方限额快照剩余: {primary['remaining_percent']:.2f}%")
    unknown = report.get("unknown_pricing", {}).get("api", {})
    if unknown:
        print("  未计价模型: " + ", ".join(f"{name} ({_format_int(count)} tokens)" for name, count in unknown.items()))


def command_scan(args: argparse.Namespace) -> int:
    report = _build(args)
    if args.json:
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
            print(f"已写入 {args.output.resolve()}")
        else:
            print(payload)
    else:
        _print_summary(report)
    return 0


def command_report(args: argparse.Namespace) -> int:
    report = _build(args)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_standalone(report), encoding="utf-8")
    print(f"已生成脱敏离线报告：{output}")
    print("报告不包含提示词、工作区路径、API Key 或原始会话 ID。")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    pricebook = PriceBook.default()

    def builder() -> dict[str, Any]:
        return _build(args, pricebook)

    serve_dashboard(builder, port=args.port, open_browser=args.open)
    return 0


def command_app(args: argparse.Namespace) -> int:
    pricebook = PriceBook.default()

    def builder() -> dict[str, Any]:
        return _build(args, pricebook)

    run_app(builder, port=args.port)
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    book = PriceBook.default()
    home = (args.codex_home or default_codex_home()).expanduser().resolve()
    files = discover_session_files(home, include_archived=not args.active_only)
    print("价格表: 通过（官方域名白名单、双账本隔离、非负费率）")
    print(f"Codex 数据目录: {home}")
    print(f"可读取 JSONL: {len(files)}")
    print(f"API 模型记录: {len(book.api.get('models', {}))}")
    print(f"订阅 credits 模型记录: {len(book.subscription.get('models', {}))}")
    print("网络依赖: 无")
    print("第三方中转: 无")
    return 0 if files else 2


def command_prices(args: argparse.Namespace) -> int:
    book = PriceBook.default()
    if args.check:
        print("价格表校验通过。API 美元与订阅 credits 保持独立。")
        return 0
    ledger = book.public_ledger()
    print("API 历史价格（USD / 1M tokens）")
    for row in ledger["api"]:
        end = row.get("effective_to") or "现在"
        rates = row["rates"]
        print(
            f"  {row['model']:<19} {row['effective_from'][:10]} → {end[:10] if end != '现在' else end:<10} "
            f"in {rates['input']:g} / cache {rates['cached_input']:g} / write {rates['cache_write']:g} / out {rates['output']:g}"
        )
    print("\n订阅 credits（credits / 1M tokens；不继承 API 降价）")
    for row in ledger["subscription"]:
        rates = row["credits"]
        print(
            f"  {row['model']:<19} in {rates['input']:g} / cache {rates['cached_input']:g} / out {rates['output']:g} "
            f"· fast ×{row['fast_multiplier']:g}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-meter",
        description="本地统计 Codex token，并用 OpenAI 官方 API 价格与订阅 credits 双账本估算。",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="扫描并在终端输出统计")
    _add_scan_options(scan_parser)
    scan_parser.add_argument("--json", action="store_true", help="输出完整 JSON 报告")
    scan_parser.add_argument("--output", type=Path, help="JSON 输出文件（需配合 --json）")
    scan_parser.set_defaults(func=command_scan)

    report_parser = subparsers.add_parser("report", help="生成单文件离线 HTML 报告")
    _add_scan_options(report_parser)
    report_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("codex-usage-report.html"),
        help="报告路径",
    )
    report_parser.set_defaults(func=command_report)

    serve_parser = subparsers.add_parser("serve", help="启动仅监听 127.0.0.1 的本地仪表盘")
    _add_scan_options(serve_parser)
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true", help="启动后打开默认浏览器")
    serve_parser.set_defaults(func=command_serve)

    app_parser = subparsers.add_parser("app", help="启动 Codex Dollar 桌面 App")
    _add_scan_options(app_parser)
    app_parser.add_argument("--port", type=int, default=0, help="本地端口；0 表示自动选择")
    app_parser.set_defaults(func=command_app)

    doctor_parser = subparsers.add_parser("doctor", help="检查日志与价格表配置")
    doctor_parser.add_argument("--codex-home", type=Path, default=None)
    doctor_parser.add_argument("--active-only", action="store_true")
    doctor_parser.set_defaults(func=command_doctor)

    prices_parser = subparsers.add_parser("prices", help="查看或校验双价格表")
    prices_parser.add_argument("--check", action="store_true")
    prices_parser.set_defaults(func=command_prices)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "output", None) and getattr(args, "json", False) is False and args.command == "scan":
        parser.error("scan --output 需要同时指定 --json")
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

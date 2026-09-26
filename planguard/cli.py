# -*- coding: utf-8 -*-
"""PlanGuard 命令行入口（骨架阶段）。

命令一览:
    py -m planguard info              版本与模块状态
    py -m planguard demo              骨架端到端演示（内置样例参数卡 × 样例规则）
    py -m planguard rules             查看内置规则库
    py -m planguard parse <方案路径>   docx/pdf 解析（M2 实现）
    py -m planguard check <方案路径>   完整审查（M3 实现）

退出码: 0 成功；1 运行错误；2 用法错误；3 功能尚未实现。
"""
import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .rules.engine import DEFAULT_RULES_DIR, RuleEngine, load_rules

UNIMPLEMENTED = (
    "该命令尚未实现：解析器在里程碑 M2、完整审查在 M3 接入"
    "（路线图见 plan/05-里程碑.md）。"
    "当前可运行 `py -m planguard demo` 查看骨架端到端演示。"
)

MODULE_STATUS = [
    ("已就绪", "ir/schema       统一中间表示（参数卡/证据/结论）"),
    ("最小可用", "rules/engine    规则引擎（required/threshold_min/threshold_max）"),
    ("样例 5 条", "rules/data      规则库（深基坑 + 高支模）"),
    ("M2 计划", "parsers/docx    docx 方案解析器"),
    ("M2 计划", "parsers/pdf     文本型 pdf 解析器"),
    ("M3 计划", "orchestrator    端到端流水线编排"),
    ("M3/M5 计划", "report          审查报告导出（Markdown → docx）"),
    ("M4 计划", "knowledge       条文知识库与检索问答"),
    ("M4 计划", "llm             LLM 兜底抽取（防幻觉三件套）"),
    ("M5 计划", "web             Web 审查面板"),
]

RESULT_LABEL = {"fail": "不合规", "manual": "待确认", "pass": "通过  "}
RESULT_ORDER = {"fail": 0, "manual": 1, "pass": 2}


def _utf8_console() -> None:
    """Windows 控制台默认 GBK，统一切换为 UTF-8，避免中文输出乱码/报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def cmd_info(_args) -> int:
    print("PlanGuard v%s（%s）" % (__version__, __import__("planguard").__status__))
    print()
    print("模块状态（里程碑详见 plan/05-里程碑.md）：")
    for status, name in MODULE_STATUS:
        print("  [%s] %s" % (status, name))
    print()
    print("快速开始: py -m planguard demo")
    return 0


def cmd_rules(args) -> int:
    rules = load_rules(Path(args.rules_dir) if args.rules_dir else DEFAULT_RULES_DIR)
    disabled = sum(1 for r in rules if not r.enabled)
    print("规则共 %d 条（其中未启用 %d 条）：" % (len(rules), disabled))
    for r in rules:
        flag = "" if r.enabled else "（未启用，%s 起）" % (r.stage or "后续")
        print("  %-9s %-26s %-18s %s%s" % (r.id, r.name, r.check_type, r.basis, flag))
    return 0


def _demo_cards():
    from .ir.schema import Evidence, ParameterCard

    return [
        ParameterCard(
            param_id="dp.excavation_depth", name="基坑开挖深度",
            value=5.4, unit="m", raw_text="5.4m", category="deep_pit",
            evidence=Evidence(doc="样例深基坑方案.docx",
                              section="三、施工工艺技术/3.2 基坑开挖", page=12,
                              line_text="基坑开挖深度为5.4m，采用放坡+土钉墙支护。"),
        ),
        ParameterCard(
            param_id="dp.retaining.displacement", name="支护结构顶部水平位移控制值",
            value=35.0, unit="mm", raw_text="35mm", category="deep_pit",
            evidence=Evidence(doc="样例深基坑方案.docx",
                              section="六、施工安全保证措施/6.3 监测方案", page=25,
                              line_text="支护结构顶部水平位移控制值为35mm。"),
        ),
        ParameterCard(
            param_id="dp.monitoring.frequency", name="基坑监测频率（开挖至底板期间）",
            value=0.5, unit="次/d", raw_text="0.5次/d", category="deep_pit",
            evidence=Evidence(doc="样例深基坑方案.docx",
                              section="六、施工安全保证措施/6.3 监测方案", page=26,
                              line_text="开挖至坑底期间，监测频率为0.5次/d。"),
        ),
    ]


def _print_review(result) -> None:
    from .ir.schema import ReviewResult

    assert isinstance(result, ReviewResult)
    s = result.summary()
    print("== PlanGuard 骨架端到端演示 ==")
    print("说明: 参数卡为内置样例；M2 起由解析器从方案文档自动提取。")
    print()
    print("提取参数卡 %d 张:" % len(result.cards))
    for card in result.cards:
        loc = card.evidence.section if card.evidence else ""
        print("  %-26s %s %-4s ← %s" % (card.param_id, card.value, card.unit, loc))
    print()
    print("核查结论（不合规 %d / 待确认 %d / 通过 %d）:" % (s["fail"], s["manual"], s["pass"]))
    for f in sorted(result.findings, key=lambda x: (RESULT_ORDER.get(x.result, 9), x.rule_id)):
        print("  [%s] %s %s" % (RESULT_LABEL.get(f.result, f.result), f.rule_id, f.rule_name))
        if f.detail:
            print("           %s" % f.detail)
        if f.evidence_line:
            print("           原文: %s" % f.evidence_line)
        print("           依据: %s" % f.basis)
        if f.advice:
            print("           建议: %s" % f.advice)
    print()
    if s["fail"]:
        print("总体结论: 不合规 —— 存在强制条款不满足，须整改后复审。")
    elif s["manual"]:
        print("总体结论: 待人工确认 —— 自动核查未发现违规，但有 %d 项需人工复核。" % s["manual"])
    else:
        print("总体结论: 通过（基于当前规则库）。")


def cmd_demo(_args) -> int:
    from .ir.schema import ReviewResult

    rules = load_rules(DEFAULT_RULES_DIR)
    engine = RuleEngine(rules)
    cards = _demo_cards()
    findings, skipped = engine.check(cards)
    result = ReviewResult(
        doc="样例深基坑方案.docx（内置演示数据）",
        cards=cards, findings=findings,
        meta={"rules_total": len(rules) + len(engine.disabled),
              "rules_skipped": [r.id for r in skipped],
              "disabled_rules": [r.id for r in engine.disabled]},
    )
    _print_review(result)
    if result.meta["rules_skipped"]:
        print()
        print("注: 规则 %s 的 check_type 骨架阶段未启用（%s 实现）。"
              % (",".join(result.meta["rules_skipped"]),
                 [r.stage for r in engine.disabled if r.id in result.meta["rules_skipped"]]))
    return 0


def cmd_parse(args) -> int:
    """M2 已实现：docx → 解析中间格式 → 参数卡（PDF 解析器 M2 收尾）。"""
    from .extract import extract_cards
    from .parsers.docx_parser import DocxParser
    from .parsers.pdf_parser import PdfParser

    path = Path(args.path)
    if not path.exists():
        print("文件不存在: %s" % path, file=sys.stderr)
        return 1
    parser_cls = {".docx": DocxParser, ".pdf": PdfParser}.get(path.suffix.lower())
    if parser_cls is None:
        print("不支持的格式: %s（当前支持 .docx / .pdf）" % path.suffix, file=sys.stderr)
        return 1
    try:
        parsed = parser_cls().parse(path)
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except RuntimeError as exc:  # 缺依赖等可读错误
        print(str(exc), file=sys.stderr)
        return 1
    cards, meta = extract_cards(parsed)
    payload = {
        "doc": parsed.doc_name,
        "sections": len(parsed.sections),
        "lines": len(parsed.lines),
        "cards": [c.to_dict() for c in cards],
        "meta": meta,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print("已写入 %s（参数卡 %d 张 / 章节 %d / 行 %d）"
              % (out, len(cards), len(parsed.sections), len(parsed.lines)))
    else:
        print(text)
    return 0


def cmd_check(args) -> int:
    print(
        "完整审查（check）在里程碑 M3 接通：解析→提取→规则引擎→报告"
        "（路线图见 plan/05-里程碑.md）。当前可运行：\n"
        "  py -m planguard parse %s   # 解析并提取参数卡（M2 已可用）\n"
        "  py -m planguard demo       # 骨架端到端演示" % args.path,
        file=sys.stderr,
    )
    return 3


def main(argv=None) -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(
        prog="planguard",
        description="PlanGuard —— 危大工程专项施工方案智能审查系统（骨架阶段）",
    )
    parser.add_argument("--version", action="version", version="planguard " + __version__)
    sub = parser.add_subparsers(dest="command")

    p_info = sub.add_parser("info", help="版本与模块状态")
    p_info.set_defaults(func=cmd_info)

    p_demo = sub.add_parser("demo", help="骨架端到端演示")
    p_demo.set_defaults(func=cmd_demo)

    p_rules = sub.add_parser("rules", help="查看内置规则库")
    p_rules.add_argument("--dir", dest="rules_dir", help="自定义规则库目录（默认内置样例）")
    p_rules.set_defaults(func=cmd_rules)

    p_parse = sub.add_parser("parse", help="解析方案文档为参数卡（docx 已可用，pdf 收尾中）")
    p_parse.add_argument("path", help="方案 docx/pdf 路径")
    p_parse.add_argument("--out", help="结果写入 JSON 文件（默认打印到 stdout）")
    p_parse.set_defaults(func=cmd_parse)

    p_check = sub.add_parser("check", help="完整审查并出报告（M3 实现）")
    p_check.add_argument("path", help="方案 docx/pdf 路径")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)

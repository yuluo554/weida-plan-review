# -*- coding: utf-8 -*-
"""端到端流水线编排（M3 接通）。

load_doc → parse → extract_cards → load_rules → check → report
每阶段记录耗时；CLI check 与 Web 面板共用本编排器；失败给出可读错误。
"""
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from .ir.schema import ReviewResult

STAGES = ("load_doc", "parse", "extract_cards", "load_rules", "check", "report")


@dataclass
class StageRecord:
    name: str
    status: str = "pending"   # pending / ok / error
    seconds: float = 0.0
    note: str = ""


@dataclass
class PipelineTrace:
    doc: str = ""
    stages: List[StageRecord] = field(default_factory=list)

    def add(self, name: str, seconds: float, note: str = "") -> None:
        self.stages.append(StageRecord(name=name, status="ok", seconds=seconds, note=note))


def _pick_parser(path: Path):
    from .parsers.docx_parser import DocxParser
    from .parsers.pdf_parser import PdfParser

    cls = {".docx": DocxParser, ".pdf": PdfParser}.get(path.suffix.lower())
    if cls is None:
        raise ValueError("不支持的格式: %s（当前支持 .docx / .pdf）" % path.suffix)
    return cls


def run(doc_path, out_dir=None, rules_dir=None) -> Tuple[ReviewResult, PipelineTrace]:
    """端到端审查：方案文档 → (ReviewResult, PipelineTrace)。

    out_dir 给定时导出 Markdown 审查报告（M5 增加 docx）。
    """
    doc_path = Path(doc_path)
    trace = PipelineTrace(doc=str(doc_path))

    def _stage(name, fn, *args, **kwargs):
        t0 = time.perf_counter()
        out = fn(*args, **kwargs)
        trace.add(name, time.perf_counter() - t0)
        return out

    if not doc_path.exists():
        raise FileNotFoundError("文件不存在: %s" % doc_path)
    parser_cls = _stage("load_doc", _pick_parser, doc_path)
    parsed = _stage("parse", parser_cls().parse, doc_path)

    from .extract import extract_cards
    cards, meta = _stage("extract_cards", extract_cards, parsed)

    from .rules.engine import DEFAULT_RULES_DIR, RuleEngine, load_rules
    rules = _stage("load_rules", load_rules,
                   Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR)
    engine = RuleEngine(rules)

    def _check():
        findings, skipped = engine.check(cards, doc=parsed)
        return ReviewResult(
            doc=parsed.doc_name, cards=cards, findings=findings,
            meta={
                "rules_total": len(rules) + len(engine.disabled),
                "rules_skipped": [r.id for r in skipped],
                "discarded": meta.get("discarded", []),
            },
        )

    result = _stage("check", _check)

    if out_dir is not None:
        from .report.exporter import export_markdown
        out_dir = Path(out_dir)
        report_path = out_dir / (Path(parsed.doc_name).stem + ".审查报告.md")
        _stage("report", export_markdown, result, report_path)
        result.meta["report"] = str(report_path)
    return result, trace

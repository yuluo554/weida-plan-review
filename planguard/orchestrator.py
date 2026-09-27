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


def _missing_params(rules, cards, parsed) -> dict:
    """required 规则要求、但规则提取未命中的参数（含 only_if_text 类目门控）。"""
    from .extract.extractor import PARAM_META, TEXT_PARAMS

    have = {c.param_id for c in cards}
    line_texts = [line.text or "" for line in parsed.lines]
    missing: dict = {}
    for rule in rules:
        if not rule.enabled or rule.check_type != "required" or rule.param in have:
            continue
        if rule.param in missing:
            continue
        if rule.only_if_text and not any(
                k in t for k in rule.only_if_text for t in line_texts):
            continue  # 类目门控：本文档不属于该规则的工程类目
        spec = PARAM_META.get(rule.param) or TEXT_PARAMS.get(rule.param)
        if spec:
            missing[rule.param] = spec if isinstance(spec, dict) else {"name": rule.param}
    return missing


def _run_llm_fallback(rules, cards, parsed) -> dict:
    """LLM 兜底抽取：只补 required 缺参；任何失败降级纯规则（info["degraded"]）。"""
    info: dict = {}
    try:
        from .llm.client import LLMError, LLMNotConfigured, OpenAICompatClient, is_configured
        from .llm.fallback import fallback_extract

        if not is_configured():
            info["reason"] = "LLM 未配置（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL），走纯规则通路"
            return info
        missing = _missing_params(rules, cards, parsed)
        info["missing_params"] = sorted(missing)
        if not missing:
            info["reason"] = "规则提取已命中全部目标参数，未触发 LLM"
            return info
        client = OpenAICompatClient()
        new_cards, fb_meta = fallback_extract(client, parsed, missing)
        cards.extend(new_cards)
        info.update(fb_meta)
    except Exception as exc:  # noqa: BLE001 降级约定：LLM 任何失败不影响确定性结论
        info["degraded"] = "%s: %s" % (type(exc).__name__, exc)
    return info


def run(doc_path, out_dir=None, rules_dir=None, use_llm=False) -> Tuple[ReviewResult, PipelineTrace]:
    """端到端审查：方案文档 → (ReviewResult, PipelineTrace)。

    out_dir 给定时导出 Markdown 审查报告（M5 增加 docx）。
    use_llm=True 时对规则提取未命中的参数做 LLM 兜底抽取（防幻觉三件套校验）；
    未配置或请求失败自动降级纯规则通路，不崩溃（降级原因记入 result.meta["llm"]）。
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

    llm_info: dict = {"use_llm": bool(use_llm)}
    if use_llm:
        def _llm_fallback():
            return _run_llm_fallback(rules, cards, parsed)

        llm_info.update(_stage("llm_fallback", _llm_fallback))

    def _check():
        findings, skipped = engine.check(cards, doc=parsed)
        return ReviewResult(
            doc=parsed.doc_name, cards=cards, findings=findings,
            meta={
                "rules_total": len(rules) + len(engine.disabled),
                "rules_skipped": [r.id for r in skipped],
                "discarded": meta.get("discarded", []),
                "llm": llm_info,
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

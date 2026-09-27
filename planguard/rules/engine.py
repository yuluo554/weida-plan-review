# -*- coding: utf-8 -*-
"""规则引擎（M3：深基坑全量 check_type）。

按 check_type 分派核查（Schema 见 plan/03-模块详设.md §3）：
- required            参数必须可提取（缺 → 漏项）
- threshold_min/max   数值下限/上限
- within_range        数值区间 [min_value, max_value]
- enum                文本取值（text_value 与 allowed 双向包含匹配）
- conditional_program 条件触发程序性检查（如深度≥5m 须专家论证），需要 doc 上下文
- checklist_section   章节完备性（建办质〔2018〕31号 九项内容），需要 doc 上下文

裁决约定（plan/03 §3）：
- 结论一律挂依据条款（basis）；
- 同一参数多值冲突 → manual（待人工确认），不硬判；
- 缺参数由 required 规则负责报告，数值类规则遇缺参跳过；
- conditional_program / checklist_section 需要 doc（ParseResult），
  未提供 doc 时跳过并记录，不静默。
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..ir.schema import Finding, ParameterCard

DEFAULT_RULES_DIR = Path(__file__).resolve().parent / "data"

SUPPORTED = ("required", "threshold_min", "threshold_max", "within_range", "enum")
DOC_REQUIRED = ("conditional_program", "checklist_section")

_LEVELS = ("强制", "建议")
_SEVERITIES = ("error", "warning", "info")


class RuleError(ValueError):
    """规则 JSON 不符合约定 Schema。"""


@dataclass
class Rule:
    id: str
    name: str
    check_type: str
    param: str
    basis: str
    level: str = "强制"
    severity: str = "error"
    category: str = ""
    op: Optional[str] = None      # threshold 类比较符
    value: Optional[float] = None  # threshold 类阈值
    unit: str = ""
    min_value: Optional[float] = None  # within_range 下限
    max_value: Optional[float] = None  # within_range 上限
    allowed: List[str] = field(default_factory=list)   # enum 允许取值
    condition: Dict[str, Any] = field(default_factory=dict)  # conditional 触发条件 {"min": 5}
    require_text: str = ""          # conditional 要求全文出现的表述
    sections: List[Dict[str, Any]] = field(default_factory=list)  # checklist 章节清单
    only_if_text: List[str] = field(default_factory=list)  # 类目门控：全文含任一关键词才生效
    advice: str = ""               # 支持 {value}/{limit}/{unit} 占位
    enabled: bool = True
    stage: str = ""                # 计划启用的里程碑
    note: str = ""                 # 备注，如"示例阈值，待核对"


def _rule_from_dict(data: Dict[str, Any]) -> Rule:
    for key in ("id", "name", "check_type", "param", "basis"):
        if not data.get(key):
            raise RuleError("规则缺少必填字段 %s: %r" % (key, data.get("id", data)))
    ct = data["check_type"]
    if ct in ("threshold_min", "threshold_max") and (data.get("op") is None or data.get("value") is None):
        raise RuleError("阈值规则须提供 op/value: %s" % data["id"])
    if ct == "within_range" and data.get("min_value") is None and data.get("max_value") is None:
        raise RuleError("within_range 规则须提供 min_value/max_value 至少其一: %s" % data["id"])
    if ct == "enum" and not data.get("allowed"):
        raise RuleError("enum 规则须提供 allowed 列表: %s" % data["id"])
    if ct == "conditional_program" and not (data.get("condition") and data.get("require_text")):
        raise RuleError("conditional_program 规则须提供 condition 与 require_text: %s" % data["id"])
    if ct == "checklist_section" and not data.get("sections"):
        raise RuleError("checklist_section 规则须提供 sections 清单: %s" % data["id"])
    if data.get("level", "强制") not in _LEVELS:
        raise RuleError("level 取值非法（须为 %s）: %s" % (_LEVELS, data["id"]))
    if data.get("severity", "error") not in _SEVERITIES:
        raise RuleError("severity 取值非法（须为 %s）: %s" % (_SEVERITIES, data["id"]))
    fields = set(Rule.__dataclass_fields__)
    return Rule(**{k: v for k, v in data.items() if k in fields})


def load_rules(path: Path) -> List[Rule]:
    """加载规则：目录 → 其中全部 *.json（按文件名排序）；或单个 json 文件。"""
    path = Path(path)
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    rules: List[Rule] = []
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("rules", [])
        for item in data:
            rules.append(_rule_from_dict(item))
    return rules


def _compare(value: float, op: str, limit: float) -> bool:
    if op == "<=":
        return value <= limit
    if op == ">=":
        return value >= limit
    if op == "<":
        return value < limit
    if op == ">":
        return value > limit
    raise RuleError("不支持的比较符: %r" % op)


class RuleEngine:
    """确定性规则引擎：参数卡进，结论出。数值结论只出自这里（NFR-05）。"""

    def __init__(self, rules: List[Rule]):
        self.rules = [r for r in rules if r.enabled]
        self.disabled = [r for r in rules if not r.enabled]

    def check(self, cards: List[ParameterCard], doc=None) -> Tuple[List[Finding], List[Rule]]:
        """返回 (findings, skipped)。

        doc: ParseResult（可选）。conditional_program / checklist_section 需要
        doc 的章节树与全文行；未提供时这些规则计入 skipped。
        skipped 为本次未执行的规则（check_type 不支持或缺 doc 上下文）。
        """
        findings: List[Finding] = []
        skipped: List[Rule] = []
        by_param: Dict[str, List[ParameterCard]] = {}
        for card in cards:
            by_param.setdefault(card.param_id, []).append(card)
        for rule in self.rules:
            ct = rule.check_type
            if rule.only_if_text and doc is not None:
                # 类目门控：全文不含关键词 → 本文档不适用该规则（如深基坑方案不查高支模参数）。
                # 对全部 check_type 生效（含 conditional_program / checklist_section）。
                if not any(k in (line.text or "") for k in rule.only_if_text for line in doc.lines):
                    continue
            if ct in DOC_REQUIRED:
                if doc is None:
                    skipped.append(rule)
                elif ct == "conditional_program":
                    findings.extend(self._check_conditional(rule, by_param, doc))
                else:
                    findings.extend(self._check_checklist(rule, doc))
                continue
            if ct not in SUPPORTED:
                skipped.append(rule)
                continue
            group = by_param.get(rule.param, [])
            if ct == "required":
                findings.append(self._check_required(rule, group))
            elif ct == "enum":
                findings.extend(self._check_enum(rule, group))
            else:
                findings.extend(self._check_numeric(rule, group))
        return findings, skipped

    @staticmethod
    def _evidence_line(group: List[ParameterCard]) -> str:
        for card in group:
            if card.evidence and card.evidence.line_text:
                return card.evidence.line_text
        return ""

    def _check_required(self, rule: Rule, group: List[ParameterCard]) -> Finding:
        if not group:
            return Finding(
                rule.id, rule.name, rule.level, rule.severity, "fail",
                basis=rule.basis,
                advice=rule.advice or "未提取到该参数，请补充或人工确认。",
            )
        got = group[0]
        detail = ("已提取: %s" % got.text_value) if got.text_value is not None \
            else ("已提取: %s %s" % (got.value, got.unit))
        return Finding(
            rule.id, rule.name, rule.level, rule.severity, "pass",
            basis=rule.basis, detail=detail,
            evidence_line=self._evidence_line(group),
        )

    def _check_numeric(self, rule: Rule, group: List[ParameterCard]) -> List[Finding]:
        """threshold_min/max 与 within_range 共用：缺参跳过，多值冲突 manual。"""
        if not group:
            return []  # 缺参由 required 规则负责报告
        values = sorted({card.value for card in group if card.value is not None})
        if not values:
            return []
        if len(values) > 1:
            detail = "同一参数提取到 %d 个取值: %s（疑似多出处冲突）" % (
                len(values), "/".join(_fmt(v) for v in values))
            return [Finding(
                rule.id, rule.name, rule.level, rule.severity, "manual",
                basis=rule.basis, detail=detail,
                advice="请人工确认以哪处原文为准。",
                evidence_line=self._evidence_line(group),
            )]
        value = values[0]
        if rule.check_type in ("threshold_min", "threshold_max"):
            ok = _compare(value, rule.op, rule.value)
            detail = "实测 %s%s，要求 %s %s%s" % (
                _fmt(value), rule.unit, rule.op, _fmt(rule.value), rule.unit)
            limit = rule.value
        else:  # within_range
            lo, hi = rule.min_value, rule.max_value
            ok = (lo is None or value >= lo) and (hi is None or value <= hi)
            detail = "实测 %s%s，要求区间 [%s, %s]%s" % (
                _fmt(value), rule.unit,
                "?" if lo is None else _fmt(lo), "?" if hi is None else _fmt(hi), rule.unit)
            limit = rule.max_value if (hi is not None and value > hi) else rule.min_value
        if ok:
            return [Finding(
                rule.id, rule.name, rule.level, rule.severity, "pass",
                basis=rule.basis, detail=detail,
                evidence_line=self._evidence_line(group),
            )]
        advice = rule.advice or "参数不满足要求，请复核并整改。"
        if "{" in advice:
            try:
                advice = advice.format(value=_fmt(value), limit=_fmt(limit), unit=rule.unit)
            except (KeyError, IndexError):
                pass
        return [Finding(
            rule.id, rule.name, rule.level, rule.severity, "fail",
            basis=rule.basis, advice=advice, detail=detail,
            evidence_line=self._evidence_line(group),
        )]

    def _check_enum(self, rule: Rule, group: List[ParameterCard]) -> List[Finding]:
        if not group:
            return []  # 缺参由 required 规则负责报告
        matched, mismatched = [], []
        for card in group:
            tv = card.text_value or ""
            hit = tv in rule.allowed or any(a in tv or tv in a for a in rule.allowed if tv)
            (matched if hit else mismatched).append(card)
        findings: List[Finding] = []
        for card in matched:
            findings.append(Finding(
                rule.id, rule.name, rule.level, rule.severity, "pass",
                basis=rule.basis, detail="取值「%s」在允许集合内" % card.text_value,
                evidence_line=self._evidence_line([card]),
            ))
        for card in mismatched:
            advice = rule.advice or "取值不在允许集合内，请复核。"
            findings.append(Finding(
                rule.id, rule.name, rule.level, rule.severity, "fail",
                basis=rule.basis,
                detail="取值「%s」不在允许集合 %s 内" % (card.text_value, "/".join(rule.allowed)),
                advice=advice,
                evidence_line=self._evidence_line([card]),
            ))
        return findings

    def _check_conditional(self, rule: Rule, by_param: Dict[str, List[ParameterCard]],
                           doc) -> List[Finding]:
        """条件触发：参数满足 condition（如 depth≥5m）时，全文须出现 require_text。"""
        group = by_param.get(rule.param, [])
        values = [c.value for c in group if c.value is not None]
        if not values:
            return []  # 参数缺失/被丢弃 → 不触发（漏项由 required 负责）
        cond_min = rule.condition.get("min")
        cond_max = rule.condition.get("max")
        triggered = any(
            (cond_min is None or v >= cond_min) and (cond_max is None or v <= cond_max)
            for v in values)
        if not triggered:
            return []
        hit = any(rule.require_text in (line.text or "") for line in doc.lines)
        detail = "触发条件 %s，全文%s「%s」" % (
            _cond_text(rule.condition), "存在" if hit else "未检出", rule.require_text)
        finding = Finding(
            rule.id, rule.name, rule.level, rule.severity,
            "pass" if hit else "fail",
            basis=rule.basis, detail=detail,
            advice="" if hit else (rule.advice or "请补充相应程序性材料。"),
            evidence_line="",
        )
        return [finding]

    def _check_checklist(self, rule: Rule, doc) -> List[Finding]:
        """章节完备性：sections 清单逐项核对（标题含任一关键词即视为存在）。"""
        titles = [s.title for s in doc.sections]
        findings: List[Finding] = []
        missing = []
        for item in rule.sections:
            title = item.get("title", "")
            keywords = item.get("keywords") or ([title] if title else [])
            found = any(k and k in t for k in keywords for t in titles)
            if not found:
                missing.append(title)
        if missing:
            return [Finding(
                rule.id, rule.name, rule.level, rule.severity, "fail",
                basis=rule.basis,
                detail="缺少章节/内容: %s" % "、".join(missing),
                advice=rule.advice or "请补齐专项方案必备章节。",
            )]
        return [Finding(
            rule.id, rule.name, rule.level, rule.severity, "pass",
            basis=rule.basis,
            detail="必备章节齐套（%d 项）" % len(rule.sections),
        )]


def _cond_text(condition: Dict[str, Any]) -> str:
    parts = []
    if condition.get("min") is not None:
        parts.append("≥%s" % _fmt(condition["min"]))
    if condition.get("max") is not None:
        parts.append("≤%s" % _fmt(condition["max"]))
    return "且".join(parts) if parts else "无条件"


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else str(value)

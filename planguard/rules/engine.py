# -*- coding: utf-8 -*-
"""规则引擎（骨架：最小可用）。

按 check_type 分派核查；M3 扩展 enum / within_range / conditional_program /
checklist_section（启用计划见 plan/03-模块详设.md §3）。

裁决约定（plan/03 §3）：
- 结论一律挂依据条款（basis）；
- 同一参数多值冲突 → manual（待人工确认），不硬判；
- 缺参数由 required 规则负责报告，阈值规则遇缺参跳过。
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..ir.schema import Finding, ParameterCard

DEFAULT_RULES_DIR = Path(__file__).resolve().parent / "data"

# 骨架阶段支持的 check_type；其余类型跳过并记录（不静默丢弃）
SUPPORTED = ("required", "threshold_min", "threshold_max")

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
    op: Optional[str] = None      # "<=" / ">=" / "<" / ">"（阈值类必填）
    value: Optional[float] = None  # 阈值（阈值类必填）
    unit: str = ""
    advice: str = ""               # 支持 {value}/{limit}/{unit} 占位
    enabled: bool = True
    stage: str = ""                # 计划启用的里程碑
    note: str = ""                 # 备注，如"示例阈值，待核对"


def _rule_from_dict(data: Dict[str, Any]) -> Rule:
    for key in ("id", "name", "check_type", "param", "basis"):
        if not data.get(key):
            raise RuleError("规则缺少必填字段 %s: %r" % (key, data.get("id", data)))
    if data["check_type"] in ("threshold_min", "threshold_max"):
        if data.get("op") is None or data.get("value") is None:
            raise RuleError("阈值规则须提供 op/value: %s" % data["id"])
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

    def check(self, cards: List[ParameterCard]) -> Tuple[List[Finding], List[Rule]]:
        """返回 (findings, skipped)：skipped 为骨架尚未支持 check_type 的规则。"""
        findings: List[Finding] = []
        skipped: List[Rule] = []
        by_param: Dict[str, List[ParameterCard]] = {}
        for card in cards:
            by_param.setdefault(card.param_id, []).append(card)
        for rule in self.rules:
            if rule.check_type not in SUPPORTED:
                skipped.append(rule)
                continue
            group = by_param.get(rule.param, [])
            if rule.check_type == "required":
                findings.append(self._check_required(rule, group))
            else:
                findings.extend(self._check_threshold(rule, group))
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
        return Finding(
            rule.id, rule.name, rule.level, rule.severity, "pass",
            basis=rule.basis,
            detail="已提取: %s %s" % (group[0].value, group[0].unit),
            evidence_line=self._evidence_line(group),
        )

    def _check_threshold(self, rule: Rule, group: List[ParameterCard]) -> List[Finding]:
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
        ok = _compare(value, rule.op, rule.value)
        detail = "实测 %s%s，要求 %s %s%s" % (
            _fmt(value), rule.unit, rule.op, _fmt(rule.value), rule.unit)
        if ok:
            return [Finding(
                rule.id, rule.name, rule.level, rule.severity, "pass",
                basis=rule.basis, detail=detail,
                evidence_line=self._evidence_line(group),
            )]
        advice = rule.advice or "参数不满足要求，请复核并整改。"
        if "{" in advice:
            try:
                advice = advice.format(value=_fmt(value), limit=_fmt(rule.value), unit=rule.unit)
            except (KeyError, IndexError):
                pass
        return [Finding(
            rule.id, rule.name, rule.level, rule.severity, "fail",
            basis=rule.basis, advice=advice, detail=detail,
            evidence_line=self._evidence_line(group),
        )]


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else str(value)

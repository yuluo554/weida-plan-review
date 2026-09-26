# -*- coding: utf-8 -*-
"""统一中间表示（IR）：参数卡、证据链、结论。

设计约束（plan/02 §2）：
- 所有解析结果归一到参数卡，合规比对 = 参数卡 × 规则表 的结构化匹配；
- 每条数据/结论必须携带证据链；多值冲突/低置信度输出 manual，不硬判。
"""
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    """证据链：定位到文档、章节、页码与原文行。"""

    doc: str
    section: str = ""
    page: Optional[int] = None
    line_text: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None


@dataclass
class ParameterCard:
    """参数卡：一条被提取出来的工程参数及其证据。"""

    param_id: str          # 归一化标识，如 dp.excavation_depth
    name: str              # 中文参数名
    value: Optional[float] = None
    unit: str = ""
    raw_text: str = ""     # 原文数值表达，如 "≥5.4m"
    category: str = ""     # deep_pit / formwork_support / lifting
    confidence: float = 1.0
    source: str = "rule"   # rule / llm / manual
    evidence: Optional[Evidence] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterCard":
        data = dict(data)
        ev = data.pop("evidence", None)
        card = cls(**data)
        if ev is not None:
            card.evidence = Evidence(**ev)
        return card


@dataclass
class Finding:
    """一条核查结论。result 三级：pass / fail / manual（待人工确认）。"""

    rule_id: str
    rule_name: str
    level: str = "强制"        # 强制 / 建议
    severity: str = "error"    # error / warning / info
    result: str = "manual"     # pass / fail / manual
    basis: str = ""            # 依据条款
    advice: str = ""           # 整改建议
    detail: str = ""           # 机器可读说明，如 "实测 35.0mm，要求 <= 30.0mm"
    evidence_line: str = ""    # 原文行


@dataclass
class ReviewResult:
    """一次完整审查的结果。"""

    doc: str = ""
    cards: List[ParameterCard] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, int]:
        counts = Counter(f.result for f in self.findings)
        return {
            "pass": counts.get("pass", 0),
            "fail": counts.get("fail", 0),
            "manual": counts.get("manual", 0),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc": self.doc,
            "cards": [c.to_dict() for c in self.cards],
            "findings": [asdict(f) for f in self.findings],
            "meta": self.meta,
        }

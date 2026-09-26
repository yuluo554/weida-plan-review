# -*- coding: utf-8 -*-
"""参数提取器（M2）：ParseResult 逐行匹配别名 → 参数卡。

规则优先（NFR-05）：纯正则 + 别名归一 + 物理范围校验，数值结论永远出自确定性通路；
LLM 兜底在 M4 接入，仅处理本提取器未命中的参数。

陷阱对策（plan/03 §2）：
- 伪空格："5. 4 m" → 5.4m（匹配前规范化，原文保留进证据链）
- 全角：５．４ｍ → 5.4m
- 超物理范围即丢弃（如深度 5400m），丢弃记录进 meta，不静默
- 多出处不同取值：各成一张参数卡，由规则引擎裁决为 manual（待人工确认）
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..ir.schema import Evidence, ParameterCard
from ..parsers.base import ParseResult

ALIASES_PATH = Path(__file__).resolve().parent / "aliases.json"

# 参数元信息：单位正则 / 物理合理范围 (min, max] / 工程类别 / 中文名
PARAM_META: Dict[str, Dict[str, Any]] = {
    "dp.excavation_depth": {
        "name": "基坑开挖深度", "unit_re": r"(?:mm|m|米)",
        "bounds": (0.0, 50.0), "category": "deep_pit",
        # 前缀护栏：这些限定词下的"开挖深度"不是基坑总深度（如"每层开挖深度"）
        "exclude_prefix": ("每层", "分层", "层间", "分段"),
    },
    "dp.retaining.displacement": {
        "name": "支护结构顶部水平位移控制值", "unit_re": r"(?:mm|毫米)",
        "bounds": (0.0, 500.0), "category": "deep_pit",
    },
    "dp.monitoring.frequency": {
        "name": "基坑监测频率（开挖至底板期间）", "unit_re": r"(?:次/d|次/天|次/日|次每日|次每天)",
        "bounds": (0.0, 24.0), "category": "deep_pit",
    },
    "fs.support.height": {
        "name": "高支模支撑体系搭设高度", "unit_re": r"(?:mm|m|米)",
        "bounds": (0.0, 100.0), "category": "formwork_support",
    },
}

UNIT_CANON = {"米": "m", "毫米": "mm", "次/天": "次/d", "次/日": "次/d", "次每日": "次/d", "次每天": "次/d"}

_NUM = r"(\d+(?:\.\d+)?)"
_FULLWIDTH = str.maketrans("０１２３４５６７８９．ＭｍｍＫｋＮｎ", "0123456789.MmmKkNn")

_alias_cache: Dict[str, List[str]] = {}


def _normalize(text: str) -> str:
    """匹配用规范化：全角→半角、压缩伪空格；原文不改，原文进证据链。"""
    t = text.translate(_FULLWIDTH)
    t = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", t)          # 小数点两侧伪空格
    t = re.sub(r"(\d)\s+(?=[0-9]|(?:mm|米|m|次))", r"\1", t)  # 数字与单位/数位间空格
    return t.replace(" ", "").replace("\u3000", "")


def load_aliases(path: Path = ALIASES_PATH) -> Dict[str, List[str]]:
    """别名归一表：中文别名 → param_id（plan/03 §1）。"""
    if path == ALIASES_PATH and _alias_cache:
        return dict(_alias_cache)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # 同一参数内长别名优先，避免"位移控制值"截断"水平位移控制值"
    data = {k: sorted(v, key=len, reverse=True) for k, v in data.items()}
    if path == ALIASES_PATH:
        _alias_cache.update(data)
    return data


def _iter_matches(alias: str, unit_re: str, norm: str):
    """别名 ... 数字 单位 的宽松匹配；别名与数字之间 ≤6 个非数字字符。"""
    pattern = re.compile(re.escape(alias) + r"[^0-9]{0,6}?" + _NUM + r"(" + unit_re + r")")
    return pattern.finditer(norm)


def extract_cards(result: ParseResult) -> Tuple[List[ParameterCard], Dict[str, Any]]:
    """从解析结果提取参数卡。返回 (cards, meta)；meta 记录丢弃项与扫描量，可审计。"""
    aliases = load_aliases()
    cards: List[ParameterCard] = []
    discarded: List[Dict[str, Any]] = []
    seen = set()
    # (行号, param) -> 已占用的匹配区间：长别名优先占位，短别名（"挖深"⊂"开挖深度"）不再重叠匹配
    consumed: Dict[Tuple[int, str], List[Tuple[int, int]]] = {}

    for line_no, line in enumerate(result.lines):
        if not line.text or not line.text.strip():
            continue
        norm = _normalize(line.text)
        for param_id, alias_list in aliases.items():
            info = PARAM_META[param_id]
            taken = consumed.setdefault((line_no, param_id), [])
            for alias in alias_list:
                if alias not in norm:
                    continue
                for m in _iter_matches(alias, info["unit_re"], norm):
                    if any(s < m.end() and m.start() < e for s, e in taken):
                        continue
                    guard = info.get("exclude_prefix")
                    if guard and any(w in norm[max(0, m.start() - 4):m.start()] for w in guard):
                        continue
                    value = float(m.group(1))
                    unit = UNIT_CANON.get(m.group(2), m.group(2))
                    if unit == "mm" and param_id in ("dp.excavation_depth", "fs.support.height"):
                        value, unit = value / 1000.0, "m"  # mm 书写的长度换算为 m
                    key = (param_id, value, line_no, m.start())
                    if key in seen:
                        continue
                    seen.add(key)
                    taken.append((m.start(), m.end()))
                    lo, hi = info["bounds"]
                    if not lo < value <= hi:
                        discarded.append({
                            "param": param_id, "value": value, "unit": unit,
                            "line": line.text, "reason": "超出物理合理范围(%g, %g]" % (lo, hi),
                        })
                        continue
                    cards.append(ParameterCard(
                        param_id=param_id,
                        name=info["name"],
                        value=value,
                        unit=unit,
                        raw_text=m.group(0),
                        category=info["category"],
                        confidence=1.0,
                        source="rule",
                        evidence=Evidence(
                            doc=result.doc_name,
                            section=line.section_path,
                            page=line.page,
                            line_text=line.text,
                            char_start=line.char_start,
                            char_end=line.char_end,
                        ),
                    ))
    return cards, {"lines_scanned": len(result.lines), "discarded": discarded}

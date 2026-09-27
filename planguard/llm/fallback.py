# -*- coding: utf-8 -*-
"""LLM 兜底抽取（M4）：规则提取未命中的参数，压缩候选行送 LLM，校验后成卡。

防幻觉三件套（plan/03 §5）：
1. 候选行压缩：只送含数字或目标参数别名的行，控制 token 成本；
2. 输出必须携带"行号 + 逐字摘录"，摘录不是对应原文行的子串 → 整条丢弃；
3. 数值合法性范围校验（PARAM_META.bounds），超范围丢弃；每参数只收第一张有效卡。

输出卡片 confidence<1.0、source="llm"；任何异常由调用方捕获并降级纯规则通路。
"""
import re
from typing import Any, Dict, List, Tuple

from ..extract.extractor import PARAM_META, TEXT_PARAMS, load_aliases
from ..ir.schema import Evidence, ParameterCard
from .client import OpenAICompatClient

MAX_CANDIDATE_LINES = 120
CONFIDENCE_LLM = 0.6
_NUM_HINT = re.compile(r"\d")


def _aliases_for(param_id: str) -> List[str]:
    aliases = load_aliases().get(param_id, [])
    spec = TEXT_PARAMS.get(param_id)
    if spec:
        aliases = aliases + [p for p in spec.get("alias_hints", [])]
    return aliases


def candidate_lines(lines, missing_params: Dict[str, Dict[str, Any]]) -> List[Tuple[int, Any]]:
    """候选行压缩：含数字或含目标参数别名的行；上限 MAX_CANDIDATE_LINES。"""
    alias_map = {param: _aliases_for(param) for param in missing_params}
    picked: List[Tuple[int, Any]] = []
    for line_no, line in enumerate(lines):
        text = (line.text or "").strip()
        if not text:
            continue
        has_alias = any(
            a in text for param in missing_params for a in alias_map.get(param, []))
        if has_alias or _NUM_HINT.search(text):
            picked.append((line_no, line))
            if len(picked) >= MAX_CANDIDATE_LINES:
                break
    return picked


def build_prompt(candidate: List[Tuple[int, Any]], missing_params: Dict[str, Any],
                 doc_name: str) -> str:
    param_lines = []
    for param_id, spec in missing_params.items():
        if param_id in PARAM_META:
            info = PARAM_META[param_id]
            param_lines.append("  %s: %s（单位 %s，合理范围 (%g, %g]，单位 mm 时按毫米填写）" % (
                param_id, info["name"], "m 或 mm", *info["bounds"]))
        else:
            spec2 = TEXT_PARAMS.get(param_id, {})
            param_lines.append("  %s: %s（文本型，text_value 填原文取值）" % (
                param_id, spec2.get("name", param_id)))
    line_block = "\n".join("  %d: %s" % (no, (ln.text or "").strip()) for no, ln in candidate)
    return (
        "你是施工方案参数抽取助手。只从给定的原文行中抽取目标参数，禁止编造、禁止使用原文以外的知识。\n"
        "文档：%s\n\n"
        "目标参数（可能一个也抽不到）：\n%s\n\n"
        "原文行（行号: 内容）：\n%s\n\n"
        "输出要求：只输出一个 JSON 对象，不要任何解释文字：\n"
        '{"items": [{"param": "参数id", "line_no": 原文行号, '
        '"excerpt": "从该行逐字连续摘录的原文片段（必须包含所依据的数值/取值）", '
        '"value": 数值或null, "text_value": 字符串或null, "unit": "单位或空"}]}\n'
        "某参数在原文行中没有依据时，不要输出该参数。全部没有则输出 {\"items\": []}。" % (
            doc_name, "\n".join(param_lines), line_block))


def _validate_item(item: Dict[str, Any], missing_params: Dict[str, Any],
                   candidate: List[Tuple[int, Any]], dropped: List[Dict[str, Any]]) -> \
        Tuple[str, Any, Any]:
    """校验单条 LLM 输出；返回 (param, value, text_value)，不合格抛 ValueError。"""
    param = item.get("param")
    if param not in missing_params:
        raise ValueError("param 不在缺失清单: %r" % (param,))
    line_no = item.get("line_no")
    lines_by_no = {no: ln for no, ln in candidate}
    if not isinstance(line_no, int) or line_no not in lines_by_no:
        raise ValueError("line_no 无效: %r" % (line_no,))
    line = lines_by_no[line_no]
    line_text = (line.text or "").strip()
    excerpt = (item.get("excerpt") or "").strip()
    if not excerpt or excerpt not in line_text:
        raise ValueError("摘录不是原文子串（防幻觉拦截）: %r" % (excerpt[:50],))

    value, text_value = item.get("value"), item.get("text_value")
    if param in TEXT_PARAMS:
        if not text_value or not isinstance(text_value, str):
            raise ValueError("文本型参数缺少 text_value")
        value = None
    else:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("数值型参数缺少有效 value")
        value = float(value)
        lo, hi = PARAM_META[param]["bounds"]
        if not lo < value <= hi:
            raise ValueError("数值超出物理合理范围 (%g, %g]: %g" % (lo, hi, value))
        text_value = None
    return param, value, text_value


def fallback_extract(client: OpenAICompatClient, parsed, missing_params: Dict[str, Any]) -> \
        Tuple[List[ParameterCard], Dict[str, Any]]:
    """对 parsed（ParseResult）做 LLM 兜底抽取。返回 (新增参数卡, meta)。"""
    candidate = candidate_lines(parsed.lines, missing_params)
    meta: Dict[str, Any] = {
        "params_requested": sorted(missing_params),
        "candidate_lines": len(candidate),
        "cards_added": 0,
        "dropped": [],
    }
    if not candidate or not missing_params:
        return [], meta
    answer = client.complete_json(build_prompt(candidate, missing_params, parsed.doc_name))
    items = answer.get("items") if isinstance(answer, dict) else answer
    if not isinstance(items, list):
        raise ValueError("LLM 返回缺少 items 列表")

    lines_by_no = {no: ln for no, ln in candidate}
    got: Dict[str, ParameterCard] = {}
    for item in items:
        if not isinstance(item, dict) or len(got) >= len(missing_params):
            continue
        try:
            param, value, text_value = _validate_item(item, missing_params, candidate, meta["dropped"])
        except (ValueError, TypeError) as exc:
            meta["dropped"].append({"param": item.get("param"), "reason": str(exc)})
            continue
        if param in got:  # 每参数只收第一张有效卡，避免 LLM 侧多值
            continue
        line = lines_by_no[item["line_no"]]
        got[param] = ParameterCard(
            param_id=param,
            name=missing_params[param].get("name") or PARAM_META.get(param, {}).get("name")
            or TEXT_PARAMS.get(param, {}).get("name") or param,
            value=value, unit=(item.get("unit") or "") if value is not None else "",
            text_value=text_value, raw_text=(item.get("excerpt") or "")[:60],
            category=PARAM_META.get(param, {}).get("category")
            or TEXT_PARAMS.get(param, {}).get("category") or "",
            confidence=CONFIDENCE_LLM, source="llm",
            evidence=Evidence(doc=parsed.doc_name, section=line.section_path, page=line.page,
                              line_text=line.text, char_start=line.char_start,
                              char_end=line.char_end),
        )
    cards = list(got.values())
    meta["cards_added"] = len(cards)
    return cards, meta

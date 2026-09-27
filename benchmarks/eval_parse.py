# -*- coding: utf-8 -*-
"""基准评测 1：参数解析 字段级 P/R/F1（M4，目标 F1 ≥ 0.95）。

对 data/gold/*.truth.json 的 expected_cards 与解析提取的参数卡逐字段比对：
- 数值参数按浮点容差匹配（isclose），文本参数（枚举类）精确匹配；
- 一对一贪心匹配：命中=TP，多提取=FP，漏提取=FN；
- 零 API 依赖（纯规则通路）可复跑；unit_error 文档真值已剔除该参数，
  若提取器回归（未丢弃超范围值）会计为 FP。

用法:
    py benchmarks/eval_parse.py [--samples DIR] [--gold DIR] [--min-f1 0.95]
        [--diag PATH] [--resume] [--json OUT]
退出码: 0 达标；1 未达标；2 运行错误。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (DEFAULT_GOLD_DIR, DEFAULT_SAMPLES_DIR, JsonlDiag,  # noqa: E402
                    load_truths, prf, value_match)


def extract_grouped(docx_path: Path):
    """解析 docx 并按 param_id 归组参数卡取值（value/text_value）。"""
    from planguard.extract import extract_cards
    from planguard.parsers.docx_parser import DocxParser

    parsed = DocxParser().parse(docx_path)
    cards, meta = extract_cards(parsed)
    grouped = defaultdict(lambda: {"values": [], "texts": []})
    for c in cards:
        if c.text_value is not None:
            grouped[c.param_id]["texts"].append(c.text_value)
        else:
            grouped[c.param_id]["values"].append(c.value)
    return grouped, meta


def match_param(expected_values, group) -> dict:
    """单个参数的 one-to-one 匹配，返回 tp/fp/fn 与明细。"""
    # 文本与数值分开匹配，避免类型互串
    pool_num = list(group.get("values", []))
    pool_txt = list(group.get("texts", []))
    used_num, used_txt = set(), set()
    tp, missed = 0, []
    for ev in expected_values:
        hit = False
        if isinstance(ev, str):
            for i, gv in enumerate(pool_txt):
                if i not in used_txt and value_match(ev, gv):
                    used_txt.add(i)
                    hit = True
                    break
        else:
            for i, gv in enumerate(pool_num):
                if i not in used_num and value_match(ev, gv):
                    used_num.add(i)
                    hit = True
                    break
        if hit:
            tp += 1
        else:
            missed.append(ev)
    fp = len(pool_num) - len(used_num) + len(pool_txt) - len(used_txt)
    return {"tp": tp, "fp": fp, "fn": len(missed),
            "missed": missed,
            "extra": [gv for i, gv in enumerate(pool_num) if i not in used_num]
                     + [gv for i, gv in enumerate(pool_txt) if i not in used_txt]}


def evaluate(samples_dir=DEFAULT_SAMPLES_DIR, gold_dir=DEFAULT_GOLD_DIR,
             diag_path=None, resume=False):
    truths = load_truths(gold_dir)
    if not truths:
        raise RuntimeError("真值目录为空: %s（先运行 py scripts/make_gold.py）" % gold_dir)
    diag = JsonlDiag(diag_path, resume=resume) if diag_path else None
    per_param = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    total = {"tp": 0, "fp": 0, "fn": 0}
    docs_bad = []
    for truth in truths:
        name = truth["file"]
        rec = diag.done.get(name) if diag else None
        if rec is None:
            grouped, _meta = extract_grouped(samples_dir / name)
            details = {}
            for param_id, expected_values in truth["expected_cards"].items():
                m = match_param(expected_values, grouped.get(param_id, {"values": [], "texts": []}))
                details[param_id] = m
                for k in ("tp", "fp", "fn"):
                    per_param[param_id][k] += m[k]
            rec = {"file": name, "details": details}
            for m in details.values():
                rec["tp"] = rec.get("tp", 0) + m["tp"]
                rec["fp"] = rec.get("fp", 0) + m["fp"]
                rec["fn"] = rec.get("fn", 0) + m["fn"]
            if diag:
                diag.write(rec)
        for k in total:
            total[k] += rec.get(k, 0)
        if rec.get("fp") or rec.get("fn"):
            docs_bad.append(name)
    if diag:
        diag.close()
    overall = prf(**total)
    overall["per_param"] = {p: prf(**v) for p, v in sorted(per_param.items())}
    overall["docs_bad"] = docs_bad
    overall["docs_total"] = len(truths)
    return overall


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="参数解析基准：字段级 P/R/F1")
    ap.add_argument("--samples", default=str(DEFAULT_SAMPLES_DIR))
    ap.add_argument("--gold", default=str(DEFAULT_GOLD_DIR))
    ap.add_argument("--min-f1", type=float, default=0.95, help="达标线（默认 0.95）")
    ap.add_argument("--diag", default="output/eval_parse_diag.jsonl")
    ap.add_argument("--resume", action="store_true", help="复用诊断文件中已完成文档的结果")
    ap.add_argument("--json", dest="json_out", help="结果另存 JSON 文件")
    args = ap.parse_args(argv)
    try:
        result = evaluate(Path(args.samples), Path(args.gold),
                          diag_path=args.diag, resume=args.resume)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("== 参数解析基准（%d 份生成样例，零 API） ==" % result["docs_total"])
    print("P=%.4f  R=%.4f  F1=%.4f  (TP=%d FP=%d FN=%d)" % (
        result["precision"], result["recall"], result["f1"],
        result["tp"], result["fp"], result["fn"]))
    print("%-30s %8s %8s %8s" % ("参数", "P", "R", "F1"))
    for p, m in result["per_param"].items():
        print("%-30s %8.4f %8.4f %8.4f" % (p, m["precision"], m["recall"], m["f1"]))
    if result["docs_bad"]:
        print("存在误差的文档: %s" % ", ".join(result["docs_bad"]))
    ok = result["f1"] >= args.min_f1
    print("达标线 F1 >= %.2f: %s" % (args.min_f1, "通过" if ok else "未达标"))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("结果已写入 %s" % args.json_out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

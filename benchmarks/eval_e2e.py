# -*- coding: utf-8 -*-
"""基准评测 2：端到端合规核查 检出率 / 误报率（M4，目标检出率 100%、误报 0）。

对每份生成样例跑完整流水线（解析→提取→规则引擎），与 truth.json 的注入差异
期望结论比对：
- 检出（hit）：存在 rule_id 与 result 均一致的 Finding；
- 强制误报（FP）：结果为 fail/manual 的 Finding，其 (rule_id, result) 不在该文档
  任一期望中——生成器保证自然参数不触发非 pass 结论，多出的即误报；
- 零 API 依赖可复跑。

用法:
    py benchmarks/eval_e2e.py [--samples DIR] [--gold DIR] [--diag PATH] [--resume]
退出码: 0 达标（检出 100% 且误报 0）；1 未达标；2 运行错误。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (DEFAULT_GOLD_DIR, DEFAULT_SAMPLES_DIR, JsonlDiag,  # noqa: E402
                    load_truths)


def run_doc(docx_path: Path):
    """完整流水线（不导出报告），返回 (rule_id, result) 计数与 findings 摘要。"""
    from planguard.orchestrator import run

    result, _trace = run(docx_path)
    got = defaultdict(set)
    for f in result.findings:
        got[f.rule_id].add(f.result)
    return got, result


def evaluate(samples_dir=DEFAULT_SAMPLES_DIR, gold_dir=DEFAULT_GOLD_DIR,
             diag_path=None, resume=False):
    truths = load_truths(gold_dir)
    if not truths:
        raise RuntimeError("真值目录为空: %s（先运行 py scripts/make_gold.py）" % gold_dir)
    diag = JsonlDiag(diag_path, resume=resume) if diag_path else None
    total_inj = hits = 0
    forced_fp = 0
    misses, fps, errors = [], [], []
    by_type = defaultdict(lambda: {"total": 0, "hit": 0})
    for truth in truths:
        name = truth["file"]
        rec = diag.done.get(name) if diag else None
        if rec is None:
            try:
                got, result = run_doc(samples_dir / name)
            except Exception as exc:  # 单文档崩溃记录后继续（机器不稳定兜底）
                rec = {"file": name, "error": "%s: %s" % (type(exc).__name__, exc)}
                if diag:
                    diag.write(rec)
                errors.append(rec)
                continue
            rec = {
                "file": name,
                "got": {k: sorted(v) for k, v in got.items()},
                "expects": [
                    {"rule_id": it.get("expect", {}).get("rule_id"),
                     "result": it.get("expect", {}).get("result"),
                     "type": it.get("type"),
                     "also": [{"rule_id": a.get("rule_id"), "result": a.get("result")}
                              for a in it.get("also_expect", [])]}
                    for it in truth.get("injected", [])
                ],
                "summary": result.summary(),
            }
            if diag:
                diag.write(rec)
        got = {k: set(v) for k, v in rec.get("got", {}).items()}
        for it, rec_exp in zip(truth.get("injected", []), rec.get("expects", [])):
            exp = it.get("expect", {})
            rid, res = exp.get("rule_id"), exp.get("result")
            t = it.get("type", "?")
            by_type[t]["total"] += 1
            total_inj += 1
            # 命中 = 主期望与全部 also_expect 的 (rule_id, result) 均出现
            checks = [(rid, res)] + [(a.get("rule_id"), a.get("result"))
                                     for a in rec_exp.get("also", [])]
            missing_checks = [c for c in checks
                              if c[0] is None or c[1] is None or c[1] not in got.get(c[0], set())]
            if not missing_checks:
                hits += 1
                by_type[t]["hit"] += 1
            else:
                misses.append({"file": name, "type": t,
                               "detail": "未满足 %s" % "; ".join(
                                   "期望 %s=%s，实际 %s" % (c0, c1, sorted(got.get(c0, set())))
                                   for c0, c1 in missing_checks)})
        expected_pairs = {(rid, res) for rid, res in
                          [(e.get("rule_id"), e.get("result")) for e in rec.get("expects", [])]
                          if rid and res}
        expected_pairs |= {(a.get("rule_id"), a.get("result"))
                           for e in rec.get("expects", []) for a in e.get("also", [])
                           if a.get("rule_id") and a.get("result")}
        for rid, results in got.items():
            for res in results:
                if res in ("fail", "manual") and (rid, res) not in expected_pairs:
                    forced_fp += 1
                    fps.append({"file": name, "rule_id": rid, "result": res})
    if diag:
        diag.close()
    return {
        "docs_total": len(truths),
        "doc_errors": errors,
        "injected_total": total_inj,
        "hits": hits,
        "detection_rate": (hits / total_inj) if total_inj else 1.0,
        "forced_fp": forced_fp,
        "misses": misses,
        "fps": fps,
        "by_type": {k: v for k, v in sorted(by_type.items())},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="端到端基准：检出率 / 误报率")
    ap.add_argument("--samples", default=str(DEFAULT_SAMPLES_DIR))
    ap.add_argument("--gold", default=str(DEFAULT_GOLD_DIR))
    ap.add_argument("--diag", default="output/eval_e2e_diag.jsonl")
    ap.add_argument("--resume", action="store_true", help="复用诊断文件中已完成文档的结果")
    ap.add_argument("--json", dest="json_out", help="结果另存 JSON 文件")
    args = ap.parse_args(argv)
    try:
        result = evaluate(Path(args.samples), Path(args.gold),
                          diag_path=args.diag, resume=args.resume)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("== 端到端合规核查基准（%d 份生成样例，零 API） ==" % result["docs_total"])
    if result["doc_errors"]:
        print("! %d 份文档流水线报错:" % len(result["doc_errors"]))
        for e in result["doc_errors"]:
            print("  %s: %s" % (e["file"], e["error"]))
    print("注入差异 %d 处，命中 %d 处，检出率 %.1f%%" % (
        result["injected_total"], result["hits"], result["detection_rate"] * 100))
    print("强制误报（非期望的 fail/manual）: %d" % result["forced_fp"])
    print("%-16s %6s %6s" % ("注入类型", "总数", "命中"))
    for t, v in result["by_type"].items():
        print("%-16s %6d %6d" % (t, v["total"], v["hit"]))
    for m in result["misses"]:
        print("漏检: %s [%s] %s" % (m["file"], m["type"], m["detail"]))
    for fp in result["fps"]:
        print("误报: %s %s result=%s" % (fp["file"], fp["rule_id"], fp["result"]))
    ok = (not result["doc_errors"]) and result["forced_fp"] == 0 \
        and result["hits"] == result["injected_total"]
    print("达标线 检出 100%% 且误报 0: %s" % ("通过" if ok else "未达标"))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("结果已写入 %s" % args.json_out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

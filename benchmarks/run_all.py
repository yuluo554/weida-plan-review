# -*- coding: utf-8 -*-
"""一键跑全部基准并输出 README 用的指标表（M4）。

用法:
    py benchmarks/run_all.py            # 跑两个基准，打印 Markdown 指标表
退出码: 0 两项均达标；1 任一未达标；2 运行错误。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_e2e  # noqa: E402
import eval_parse  # noqa: E402
from common import DEFAULT_GOLD_DIR, DEFAULT_SAMPLES_DIR  # noqa: E402


def main(argv=None) -> int:
    started = time.perf_counter()
    try:
        parse_res = eval_parse.evaluate(DEFAULT_SAMPLES_DIR, DEFAULT_GOLD_DIR)
        e2e_res = eval_e2e.evaluate(DEFAULT_SAMPLES_DIR, DEFAULT_GOLD_DIR)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rows = [
        "| 基准 | 指标 | 结果 | 目标 | 达标 |",
        "| --- | --- | --- | --- | --- |",
        "| 参数解析（字段级，40 份生成样例） | P / R / F1 | %.4f / %.4f / **%.4f** | F1 ≥ 0.95 | %s |"
        % (parse_res["precision"], parse_res["recall"], parse_res["f1"],
           "✅" if parse_res["f1"] >= 0.95 else "❌"),
        "| 端到端合规核查（%d 处注入差异） | 检出率 / 强制误报 | %.1f%%（%d/%d） / **%d** | 100%% / 0 | %s |"
        % (e2e_res["injected_total"], e2e_res["detection_rate"] * 100, e2e_res["hits"],
           e2e_res["injected_total"], e2e_res["forced_fp"],
           "✅" if e2e_res["detection_rate"] == 1.0 and e2e_res["forced_fp"] == 0 else "❌"),
    ]
    print("## PlanGuard 基准评测（零 API，seed=2026 可复现，深基坑30+高支模10 份合成样例）\n")
    print("\n".join(rows))
    print("\n评测耗时 %.1fs。复现方式见 benchmarks/README.md；最近结果已写入 benchmarks/results.json。"
          % (time.perf_counter() - started))
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_parse": {k: v for k, v in parse_res.items() if k != "per_param"},
        "eval_parse_per_param": parse_res["per_param"],
        "eval_e2e": {k: v for k, v in e2e_res.items()
                     if k not in ("misses", "fps", "doc_errors")},
    }
    Path(__file__).resolve().parent.joinpath("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = parse_res["f1"] >= 0.95 and e2e_res["detection_rate"] == 1.0 and e2e_res["forced_fp"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

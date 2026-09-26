# -*- coding: utf-8 -*-
"""配对真值数据生成器（CLI 包装，核心在 planguard/goldgen.py）。

用法:
    py scripts/make_gold.py --count 10 --seed 2026
生成: data/samples/gen_XXXX.docx + data/gold/gen_XXXX.truth.json
（样例为程序化合成，不含真实项目信息；台账见 data/README.md）
"""
import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="危大方案配对真值数据生成器（合成样例）")
    parser.add_argument("--out", default="data/samples", help="样例输出目录")
    parser.add_argument("--gold", default="data/gold", help="真值输出目录")
    parser.add_argument("--count", type=int, default=10, help="生成份数")
    parser.add_argument("--seed", type=int, default=2026, help="随机种子（保证可复现）")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from planguard.goldgen import generate

    truths = generate(Path(args.out), Path(args.gold), count=args.count, seed=args.seed)
    n_inj = sum(len(t["injected"]) for t in truths)
    print("已生成 %d 份样例（%s / %s），注入差异 %d 处，真值已写入 gold/。" %
          (len(truths), args.out, args.gold, n_inj))
    print("验证: py -m planguard parse %s/gen_0001.docx" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

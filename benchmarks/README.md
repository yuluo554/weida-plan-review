# 基准评测（M4）

两个基准脚本，**零 API 依赖可重复**（纯规则通路）；一键运行输出 README 用的指标表：

```bash
export PYTHONDONTWRITEBYTECODE=1
py -X utf8 benchmarks/run_all.py          # 两个基准 + Markdown 指标表 + results.json
py -X utf8 benchmarks/eval_parse.py       # 解析基准单跑（--min-f1 0.95 门槛，退出码 0/1）
py -X utf8 benchmarks/eval_e2e.py         # 端到端基准单跑（检出 100% 且误报 0 门槛）
```

- 评测对象：`data/samples/gen_0001–0030.docx`（seed=2026 可复现的合成样例）+ `data/gold/*.truth.json` 配对真值
- 崩溃续跑：本机 Python 偶发段错误 → 每份文档结果实时落盘到 `output/eval_*_diag.jsonl`，
  加 `--resume` 可跳过已完成文档续跑
- 真值口径：每处注入差异的 `expect` 为主期望，`also_expect` 为该注入隐含的其余
  非 pass 结论（多值冲突会使其参数上全部规则输出 manual，见 `planguard/goldgen.py`）

## 最近一次结果（2026-09-27）

| 基准 | 指标 | 结果 | 目标 | 达标 |
| --- | --- | --- | --- | --- |
| 参数解析（字段级，30 份生成样例） | P / R / F1 | 1.0000 / 1.0000 / **1.0000** | F1 ≥ 0.95 | ✅ |
| 端到端合规核查（60 处注入差异） | 检出率 / 强制误报 | 100.0%（60/60） / **0** | 100% / 0 | ✅ |

明细见 `results.json`（run_all.py 每次运行后刷新）。

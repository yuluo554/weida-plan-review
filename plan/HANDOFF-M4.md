# 交接快照：M4 进行中（2026-09-26，供新对话续接）

> 项目背景、架构、里程碑见 plan/00–06；本文只写"接着干什么"。

## 当前进度

- **M1 计划+骨架 / M2 解析层（docx+pdf）/ M3 端到端审查（20 条规则、CLI check、Markdown 报告）已全部完成并推送 GitHub**（`yuluo554/weida-plan-review`，最新 commit `c95866d`）。
- **M4 进行中**，四个子任务：
  1. 生成器补论证表述 + 样例扩到 30 份 ← 已做，**发现 2 个问题待修（见下）**
  2. 知识库三层（条文块/阈值表）+ 检索问答 `planguard ask` ← 未开始
  3. LLM 兜底（防幻觉三件套/降级）+ `check --llm` ← 未开始（.env 已配好阿里云百炼 qwen3.8-flash，OpenAI 兼容）
  4. 基准评测两脚本（解析 F1 / 检出率·误报率）+ README 指标表 ← 未开始

## 刚发现、尚未修的两个问题（M4 第一步就修）

**问题 A（真 bug，生成器措辞）**：`planguard/goldgen.py` 中 depth≥5 的文档追加论证句
`"本工程基坑开挖深度超过5m，已按规定组织专家论证，论证意见已落实。"`——句中含"开挖深度"+数字，
提取器会把 **5.0 提为 dp.excavation_depth 的第二个取值**，触发多值冲突
（gen_0021 实测出现 `manual R-DP-063: 5/8.3`）。
**修法**：论证句改措辞避开别名+数字，如
`"本工程基坑属超过一定规模的危大工程，已按规定组织专家论证，论证意见已落实。"`

**问题 B（真值口径）**：`goldgen.py` 的 missing_section 注入 expect 只有
`{"checklist": "应急处置措施", "result": "fail", "since": "M3"}`，**缺 rule_id**，
导致章节齐套规则 R-DP-051 的预期 fail 被基准脚本算成"误报"。
**修法**：missing_section 的 expect 增加 `"rule_id": "R-DP-051"`。

修完 A、B 后：`py scripts/make_gold.py --count 30 --seed 2026` 重新生成，
再用批处理方式（防段错误，见下）验证 30 份：注入命中应为 60/60、强制误报 0。

（注：此前一次批量诊断曾把 gen_0021 的 R-DP-021/031 列为"意外失败"，但单查 gen_0021
结论与真值完全一致——疑为机器不稳定造成的坏读，以单查为准；修复 A/B 后全量重测再下结论。）

## 本机环境坑（重要，全部实测）

1. **Python 写 `__pycache__` 偶发损坏** → 随机 `SystemError: unknown opcode`、段错误(139)、测试数波动。
   运行/测试一律加 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`
   （含 `C:SERS<USERNAME>\AppData\Local\Programs\Python\Python38\lib\__pycache__`）再重跑；偶发崩溃直接重试。
   （已写入 README「已知环境问题」；建议用户检查磁盘/杀毒。）
2. **pip 被注册表系统代理污染**（https 项是错误的 `https://127.0.0.1:7897`）→ 装包用
   `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
3. **git 推送走代理**：本仓库已配 `http.proxy=127.0.0.1:7897`，直接 `git push` 即可；直连会超时。
4. py3.8 装 reportlab 必须 `<4`（实测 3.6.13）；python-docx 1.1.2、pdfplumber 0.11.5 已装。
5. 跑脚本用 `py -X utf8`；长循环分批 + 落盘（diag.jsonl 模式）抗崩溃。

## M4 验收标准（DoD，全部完成才算完）

- [ ] 修复问题 A/B；30 份样例注入 60/60 命中、强制误报 0
- [ ] 知识库三层落地：`data/knowledge/blocks/`（条文块 ≥30，逐条标"待核对"）+ `data/knowledge/thresholds/deep_pit.json`（≥20 条）+ `raw/` 来源登记
- [ ] `planguard/knowledge/store.py` 实现（零依赖中文检索：bigram TF 余弦即可；偏离 plan/03 的 jieba 需注明）+ CLI `ask` 命令（L3 阈值表结构化命中直接回答，否则 L2 top-k 条文）
- [ ] LLM 兜底：`llm/client.py` 的 complete_json（urllib 零依赖、enable_thinking=false、超时重试、JSON 修复、摘录必须为原文子串=防幻觉三件套、失败降级纯规则通路）+ orchestrator/CLI `check --llm` 集成
- [ ] `benchmarks/eval_parse.py`（字段级 P/R/F1，目标 F1≥0.95）与 `benchmarks/eval_e2e.py`（检出率/误报率，目标误报=0），零 API 可复跑，指标写进 README 评测表
- [ ] 测试全绿（PYTHONDONTWRITEBYTECODE=1 连跑三轮确认稳定）
- [ ] plan/00、03、04、05 状态回写（注明偏差：30 份=深基坑先行，高支模模板+规则随 M5）；提交推送 GitHub

## 关键命令速查

```bash
export PYTHONDONTWRITEBYTECODE=1
py -X utf8 -m unittest discover -v          # 全量测试
py -X utf8 scripts/make_gold.py --count 30 --seed 2026   # 重建语料
py -X utf8 -m planguard check data/samples/gen_0001.docx --report output
```

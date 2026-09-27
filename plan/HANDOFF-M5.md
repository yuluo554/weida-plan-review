# 交接快照：M4 已完成 / M5 待开始（2026-09-27，供新对话续接）

> 项目背景、架构、里程碑见 plan/00–06；M4 交接见 plan/HANDOFF-M4.md（已过时仅作历史）。
> 本文只写"接着干什么"。

## 当前进度

- **M1 计划+骨架 / M2 解析层 / M3 端到端审查 / M4 知识库+LLM兜底+基准评测 全部完成并推送 GitHub**
  （`yuluo554/weida-plan-review`，最新 commit `5e07196`）。
- M4 落地：知识库三层（条文块 35 / 阈值表 25 / raw 来源登记 7 部，全部"待核对"）；`planguard ask`
  （L3 阈值直答 / L2 bigram 余弦 top-k）；LLM 兜底（`llm/client.py` urllib+重试+JSON 截断修复、
  `llm/fallback.py` 防幻觉三件套、失败降级纯规则、`check --llm`）；基准三脚本
  （`benchmarks/eval_parse.py` / `eval_e2e.py` / `run_all.py`）；样例 30 份 + 60 处注入。
- **M4 实测指标（README 评测表已写）**：解析 F1=1.0000（150 字段全对）；端到端检出率 100%（60/60）、
  强制误报 0。66 项测试连跑三轮全绿。
- 真实 LLM 冒烟已通过（百炼 qwen3.8-flash）：规则提取器漏掉的"水平位移按25毫米控制"措辞由 LLM
  兜底命中且摘录子串校验通过；无依据参数正确不输出。

## M5 待办（plan/05，四个子任务，均未开始）

1. **Web 审查面板**（`planguard/web/app.py` 现只有 /api/health 骨架）：FastAPI + **本地 vendor Vue3**
   （不依赖 CDN，断网可演示）；上传 docx/pdf → 流水线进度（复用 orchestrator 的 stage 计时）→
   在线渲染三级结论报告（结构对齐 report/exporter.py 的 Markdown）+ 条文问答页（复用
   knowledge/store.ask）。启动：`uvicorn planguard.web.app:create_app --factory`。
2. **docx 审查报告**（`report/exporter.py` 现只有 Markdown）：python-docx 生成可归档 docx
   （总体结论/不合规清单/待确认/通过项/参数卡附录/签署栏，结构同 plan/03 §7）。
3. **高支模类目扩展**：goldgen 加高支模模板（fs.*，含"超过一定规模"论证句措辞注意——
   见 HANDOFF-M4 问题 A 教训：论证句避开"别名+数字"）；规则库加 fs 规则（threshold/required/
   conditional_program 等，全部示例值"待核对"）；样例扩到 深基坑30+高支模10（plan/04 §2 原目标）。
4. **知识库扩量**：高支模条文块（JGJ 162-2008 等）+ `thresholds/formwork_support.json` ≥15 条；
   L2 全量 ≥300 为长期目标，M5 打样即可（偏差已在 plan/04 §3 注明）。

## M5 必须遵守的既定口径（改错会直接打挂基准）

- **真值口径**（`planguard/goldgen.py` 模块注释）：自然参数不得触发任何非 pass 结论；
  每处注入 `expect` 记主期望、`also_expect` 记同一注入隐含的其余非 pass 结论
  （多值冲突会使其参数上**全部规则**输出 manual）。新增高支模注入必须保持该不变量。
- **基准门槛**：`py benchmarks/run_all.py` 必须维持 解析 F1 ≥0.95、端到端检出 100% / 误报 0
  （语料扩到 40 份后全部指标按扩大的语料复测；results.json 是 run_all 产物，随仓库入库可 diff）。
- **数值结论只出确定性规则**；LLM 只做 required 缺参兜底（含 only_if_text 门控），不许进裁决。
- 新增规则/阈值/条文块全部标"待核对"（示例值/要点+出处形式，不转载版权全文）；
  检索用 bigram 余弦（偏离 jieba 已在 plan/03 §4 注明，接口别改）。
- 测试新增进 `tests/test_m4.py` 同级（建议 test_m5.py），保持全离线（LLM 用假客户端 mock）。

## 本机环境坑（重要，全部实测）

1. **Python 写 `__pycache__` 偶发损坏** → 随机 `SystemError: unknown opcode`、段错误(139)、测试数波动。
   运行/测试一律加 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`
   （含 `C:SERS<USERNAME>\AppData\Local\Programs\Python\Python38\lib\__pycache__`）再重跑；偶发崩溃直接重试。
2. **pip 被注册表系统代理污染**（https 项是错误的 `https://127.0.0.1:7897`）→ 装包用
   `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
   M5 装法：`NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .[web]`
   （fastapi/uvicorn 尚未装）。
3. **git 推送**：代理 `127.0.0.1:7897` 时好时坏。先直接 `git push`；报 `Failed to connect ... via 127.0.0.1`
   就**切直连**（2026-09-27 实测可用，已写入 README 已知环境问题）：
   `git -c http.proxy= -c https.proxy= push`。
4. py3.8：reportlab 必须 `<4`（实测 3.6.13）；python-docx 1.1.2、pdfplumber 0.11.5 已装；
   fastapi/uvicorn 未装（M5 装 extras `[web]`）。
5. 跑脚本用 `py -X utf8`；长循环分批 + 落盘（JSONL diag 模式）抗崩溃（基准脚本已内置 --resume）。

## M5 验收标准（DoD，全部完成才算完，对齐 plan/05）

- [ ] 浏览器上传 gen_0001.docx → 在线看三级结论报告，**断网演示通过**（vendor Vue3、无 CDN）
- [ ] docx 审查报告可直接归档（含签署栏；用 python-docx）
- [ ] 高支模：生成器模板 + fs.* 规则 + 高支模样例 10 份；扩料后基准仍 检出 100% / 误报 0 / 解析 F1 ≥0.95
- [ ] 高支模阈值表 ≥15 条 + 相关条文块入库（全部"待核对"）
- [ ] 全量测试绿（PYTHONDONTWRITEBYTECODE=1 连跑三轮确认稳定）
- [ ] plan/00、04、05 状态回写（注明偏差）；README 特性/评测表同步；提交推送 GitHub

## 关键命令速查

```bash
export PYTHONDONTWRITEBYTECODE=1
py -X utf8 -m unittest discover -v                        # 全量测试（66 项）
py -X utf8 benchmarks/run_all.py                          # 基准评测 → 指标表 + results.json
py -X utf8 scripts/make_gold.py --count 30 --seed 2026    # 重建语料
py -X utf8 -m planguard check data/samples/gen_0001.docx --report output
py -X utf8 -m planguard check data/samples/gen_0001.docx --report output --llm   # LLM 兜底
py -X utf8 -m planguard ask "基坑开挖深度超过多少需要专家论证"
```

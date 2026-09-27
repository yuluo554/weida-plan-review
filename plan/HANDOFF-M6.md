# 交接快照：M5 已完成 / M6 待开始（2026-09-27，供新对话续接）

> **2026-09-27 更新：M6 已完成**——脱敏四步、发布门、干净环境验证全部通过并留档，
> 见 [RELEASE-M6.md](RELEASE-M6.md) 与 plan/05 M6；本文转为历史留档。

> 项目背景、架构、里程碑见 plan/00–06；M5 执行细节留档见 plan/PROGRESS-M5.md；
> HANDOFF-M4/M5 已过时仅作历史。本文只写"接着干什么"。

## 当前进度

- **M1 计划+骨架 / M2 解析层 / M3 端到端审查 / M4 知识库+LLM兜底+基准评测 / M5 Web+docx报告+高支模 全部完成并推送 GitHub**
  （`yuluo554/weida-plan-review`，最新 commit `1745100`）。
- M5 落地：Web 审查面板（`planguard/web/app.py`：POST /api/review 上传→流水线→三级结论 JSON、
  /api/ask 条文问答、/ 静态页；**本地 vendor Vue 3.4.38**，页面 0 外链，断网可演示）；
  docx 审查报告（`report/exporter.py export_docx`，六大节含签署栏，`check` 默认同时导出 md+docx）；
  高支模类目（`goldgen.make_fs_spec` 5 类注入 + `rules/data/formwork_support.json` 9 条 fs.* 规则 +
  样例 fs_0001–0010）；知识库扩量（阈值表 41 条 = 深基坑25+高支模16、条文块 43 块含 JGJ 162-2008，
  全部"待核对"）。
- **M5 实测指标（README 评测表已写）**：40 份语料（深基坑30+高支模10）注入 80 处——
  解析 F1=1.0000（180 字段全对）；端到端检出率 100%（80/80）、强制误报 0。81 项测试连跑三轮全绿
  （2 skip 为可选依赖 pdf/reportlab）。
- **M5 顺带修复**：规则引擎 only_if_text 门控原先对 conditional/checklist 不生效 → 已改为对全部
  check_type 生效；深基坑 required/checklist 规则已加 `only_if_text:["基坑"]` 门控（高支模规则
  门控 `["高支模","模板支撑","模板工程"]`）。**改数据/加类目时必须维持这个类目隔离**。

## M6 待办（plan/05 M6 + plan/06 §3，未开始）

1. **脱敏四步审查**（plan/06 §3 脱敏门，缺一不可，逐项打勾留档）：
   ① `git ls-files | grep -iE "\.env$|\.key$|secret|token"` 为空（.gitignore 覆盖 .env/运行产物/
   赛题材料/`data/**/_private/`）；② 内容级扫描全部跟踪文件（sk- 密钥、手机号/身份证、
   个人路径 C:\Users\xx、内部域名）；③ 二进制样例单独扫（docx/pdf 里的真实联系人/单位/项目名，
   样例均为程序化合成理论上干净，仍要扫）；④ 推送后发现问题的重写历史流程（新仓库无协作者安全）。
2. **发布门**：根 README 终版自查（简介/特性/mermaid 架构图/快速开始/评测表/目录/限制/免责声明——
   M5 已大部分就位，补"限制"小节）；LICENSE（MIT 已有）；
   `py -m planguard demo` 与 Web 面板在**干净 Windows 机 clone→一次成功**（本机验证替代：新目录
   clone + `py -m venv` 干净环境跑通）。
3. **功能门自查**：plan/ 与 data/ 台账齐全（已 ✅）；基准可复现达标（已 ✅，重跑确认即可）；
   端到端 CLI+Web 断网演示（已 ✅）；测试全绿含失败路径（已 ✅ 81 项）。
4. **初赛材料**：按 plan/06 §4 决策——用户不参赛 → 方案书/PPT **不适用**；
   如用户改主意要写，素材定位见 plan/06 §2（创新点四条已提炼好）。

## M6 必须遵守的既定口径（动了会打挂基准）

- **真值口径**（`planguard/goldgen.py` 模块注释）：自然参数不触发任何非 pass 结论；
  注入 `expect` 记主期望、`also_expect` 记同一注入隐含的其余非 pass（评测按文档全部非 pass 集合对账）。
  已知互斥坑（plan/04 §2）：fs 的 unit_error 打立杆间距、multi_height 第二值封顶 7.8m、
  over_height 先清计算书高度行；fs.formwork.type 真值存短名（"扣件式"）。
- **基准门槛**：`py benchmarks/run_all.py` 维持 解析 F1 ≥0.95、检出 100%/误报 0（40 份/80 处）。
- **数值结论只出确定性规则**；LLM 只做 required 缺参兜底（only_if_text 门控），不许进裁决。
- 规则/阈值/条文块全部标"待核对"（要点+出处形式，不转载版权全文）；检索 bigram 余弦接口别改。
- 类目隔离靠 only_if_text（引擎已全类型生效）；新类目规则必须带门控关键词，且与现有语料关键词互斥。
- 测试全离线（LLM 用假客户端 mock；Web 用 fastapi TestClient，httpx<0.28 已进 dev extras）。

## 本机环境坑（重要，全部实测）

1. **Python 写 `__pycache__` 偶发损坏** → 一律 `PYTHONDONTWRITEBYTECODE=1`；怪错/随机 FAIL 先清
   `__pycache__`（含 `C:\Users\<username>\AppData\Local\Programs\Python\Python38\lib\__pycache__`）再重跑；
   偶发崩溃直接重试（M5 实测三轮里第 3 轮随机错一次，重跑即恢复）。
2. **pip 被注册表系统代理污染**（错误的 `https://127.0.0.1:7897`）→
   `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
3. **git 推送**：先 `git push`；报 `Failed to connect ... via 127.0.0.1` 就切直连（M5 实测可用）：
   `git -c http.proxy= -c https.proxy= push`（注意 shell 管道会吃退出码，fallback 别写在 `||` 后面）。
4. py3.8：reportlab<4、python-docx 1.1.2、pdfplumber 0.11.5、fastapi 0.124.4/uvicorn/httpx 0.27.2 已装；
   vendor Vue 用 npmmirror 下载：`https://registry.npmmirror.com/vue/<ver>/files/dist/vue.global.prod.js`。
5. **agent-browser 在本机拉不起 Chrome/Edge**（DevToolsActivePort 不产出）→ 浏览器自动化不可用，
   Web 验收用 curl/urllib 冒烟 + 静态零外链核查替代（M5 已注明偏差）。
6. 跑脚本 `py -X utf8`；uvicorn 必须 `--factory`：`py -X utf8 -m uvicorn planguard.web.app:create_app --factory --port 8000`。

## M6 验收标准（DoD，全部完成才算完，对齐 plan/05 + plan/06 §3）

- [ ] 脱敏四步逐项通过并留档（四份检查的命令输出/结论写进 plan/06 或新文档）
- [ ] README 终版（补"限制"小节；其余已就位）
- [ ] 干净环境 clone → demo/check/ask/Web 一次成功（本机新目录 + 干净 venv 模拟）
- [ ] 全量测试绿（PYTHONDONTWRITEBYTECODE=1 连跑三轮）
- [ ] plan/00、05、06 状态回写；最终 commit 推送 GitHub
- [ ] （可选，用户改主意才做）初赛方案书 + PPT

## 关键命令速查

```bash
export PYTHONDONTWRITEBYTECODE=1
py -X utf8 -m unittest discover -v                        # 全量测试（81 项，2 skip）
py -X utf8 benchmarks/run_all.py                          # 基准 → 40份/80注入指标表 + results.json
py -X utf8 scripts/make_gold.py --count 30 --fs-count 10 --seed 2026   # 重建语料
py -X utf8 -m planguard check data/samples/gen_0001.docx --report output          # md+docx 报告
py -X utf8 -m planguard check data/samples/fs_0001.docx --report output --llm     # LLM 兜底
py -X utf8 -m planguard ask "高支模搭设高度超过多少需要专家论证"
py -X utf8 -m uvicorn planguard.web.app:create_app --factory --port 8000          # Web 面板
git ls-files | grep -iE "\.env$|\.key$|secret|token"      # 脱敏第①步
```

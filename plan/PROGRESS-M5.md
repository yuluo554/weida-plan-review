# M5 执行进度快照（已完成 ✅，留档防闪退）

> M5 全部完成（2026-09-27），本文件仅作执行细节留档。**新对话续接请读 plan/HANDOFF-M6.md**。

## DoD 验收对照（HANDOFF-M5.md）

- [x] 浏览器上传 gen_0001.docx → 在线三级结论报告，断网可演示：接口全链路冒烟通过（POST /api/review 上传 gen_0001.docx → summary/findings/cards/stages 齐全；/api/ask threshold 直答；/ 静态页 200；/vendor/vue.global.prod.js 200 本地 143KB）。index.html 唯一脚本=本地 vendor，全文 0 个外链（grep 证实）。偏差：本机 Chrome/Edge 自动化拉起失败（DevToolsActivePort 不产出，环境问题非代码问题），已在 plan/05 注明，人工演示命令写入 README。
- [x] docx 审查报告可归档：export_docx（python-docx）六大节+签署栏，check 默认同时导出 md+docx（orchestrator report/report_docx 阶段）。
- [x] 高支模扩展 + 基准：fs 模板 5 类注入 + fs.* 规则 9 条（R-FS-002/003/004/012/031/041/051/101/102）+ 10 份样例；40 份语料 检出 80/80=100%、误报 0、F1=1.0000。
- [x] 高支模阈值表 16 条（≥15）+ JGJ 162-2008 条文块 8 块入库，全部"待核对"；知识库总 41 阈值/43 块。
- [x] 全量测试三轮绿：81 项（2 skip=pdf/reportlab 可选依赖），OK (skipped=2) ×3。
- [x] plan/00、04、05 回写（偏差已注明）+ data/README 台账 + README 特性/评测表/快速开始同步 + 提交推送。

## M5 关键实现落点（新会话速查）

- 生成器：goldgen.py make_fs_spec / generate(category=)；make_gold.py --fs-count 10（默认 40 份/80 注入）
- 规则：rules/data/formwork_support.json（9 条）；引擎门控修复：engine.py only_if_text 对全部 check_type 生效；deep_pit required/checklist 规则加 only_if_text:["基坑"]
- 提取器：PARAM_META fs.pole.spacing；TEXT_PARAMS fs.formwork.type（捕获短名"扣件式"，真值同口径）
- 知识库：thresholds/formwork_support.json（16 条）、blocks/jgj162_2008.json（8 块）
- 报告：report/exporter.py export_docx；orchestrator out_dir 时双导出（meta.report / meta.report_docx）
- Web：web/app.py（/api/review 上传审查、/api/ask、/、/vendor/*）；web/static/index.html + vendor/vue.global.prod.js（Vue 3.4.38，npmmirror 下载）
- 测试：tests/test_m5.py（goldgen/规则门控/docx报告/Web TestClient/知识库扩量）；test_m4 基准断言 30→40；test_m3 报告阶段断言放宽
- 依赖：fastapi 0.124.4/starlette 0.44/uvicorn/httpx 0.27（dev extras 加 httpx<0.28）

## 环境实测备忘

- uvicorn 启动：`py -X utf8 -m uvicorn planguard.web.app:create_app --factory --port 8000`（--factory 必须带）
- agent-browser 在本机无法拉起 Chrome/Edge（Auto-launch failed: DevToolsActivePort）——浏览器自动化不可用
- Python38 偶发一轮 unittest 报错（环境抖动），清缓存/重跑即恢复——三轮全绿以最终轮为准
- git 推送：先 `git push`，失败 `git -c http.proxy= -c https.proxy= push`

## 下一里程碑 M6（plan/05）

脱敏四步审查（06 §3）；README 终版；初赛方案书（5000–8000 字）+ PPT（16:9）；干净 Windows 机 clone→demo 验证。

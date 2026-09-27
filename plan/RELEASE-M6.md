# M6 发布自检留档（2026-09-27）

> 对应 plan/05 M6 与 plan/06 §3 三道门。本文记录每项检查的命令与实测结论，逐项打勾；
> 发布问题与偏差一并留档（含一处发布级 bug 的发现与修复）。

## 1. 脱敏门（四步，缺一不可）

### ① 敏感文件名扫描 ✅

```
$ git ls-files | grep -iE "\.env$|\.key$|secret|token"
（无输出，exit=1）
$ git ls-files | grep -iE "\.env"   → .env.example（模板，无密钥值）
```

.gitignore 覆盖核查：`.env`/`.env.*`（排除 .env.example）、运行产物（output/outputs/run/*.log）、
赛题材料（`赛题/`）、`data/**/_private/` 均已覆盖 ✅。

### ② 内容级扫描（全部跟踪文本文件）✅（发现并修复 1 项）

| 模式 | 命令要点 | 结果 |
| --- | --- | --- |
| `sk-` API 密钥 | `git grep -nIiE "sk-[A-Za-z0-9]{8,}"` | 0 |
| api_key/password 真实赋值 | `git grep -nIiE "(api_key\|secret\|password)\s*[:=]\s*[\"'][^\"']{8,}"` | 0 |
| 手机号 `1[3-9]\d{9}` | `git grep -nIE` | 0 |
| 身份证 `\d{17}[\dXx]` | `git grep -nIE` | 0 |
| 个人路径 `C:\Users\xx` | `git grep -nIE 'C:[/\\]+Users[/\\]'` | **3 处**（见下） |
| 内部域名 | `git grep -iE "\.(internal\|corp\|lan\|local)"` | 0（"国内网络"一词为误报） |
| 内网 IP（192.168/10./172.16-31） | `git grep -nIE` | 0 |
| 邮箱 | `git grep -nIiE` | 0 |

**发现与修复**：plan/HANDOFF-M4.md、HANDOFF-M5.md、HANDOFF-M6.md 的"本机环境坑"小节各 1 处
`C:\Users\<机主名>\AppData\...__pycache__` 个人机器路径（含机主用户名，下文以 `<机主名>` 指代，
字面值已按第④步从全部历史清除，不复述）→ 已改为通用写法 `C:\Users\<username>\...`
（commit `0f6c2e2`），并按第④步对全部历史做重写清洗。

### ③ 二进制样例单独扫描 ✅

跟踪二进制 = data/samples/ 下 40 份合成 docx（无 pdf/其他二进制；plan/ 无图片，
`赛题/` 目录截图 1.jpg/2.jpg 未入库）。用 zipfile 对每份 docx 的**全部 zip 条目**
（word/*.xml + docProps/core.xml + app.xml）解码后过敏感模式：

- 手机号 / 身份证 / 邮箱 / `sk-` 密钥：**0 命中**（fontTable.xml 中 18 位数字串为字体
  Panose 字节序列，正则误报，非内容）；
- docx 元数据 `dc:creator` / `lastModifiedBy` / Company：40 份全部为库默认值
  `python-docx`，无真实人名/单位名；
- 单位名模式（xx公司/集团/工程局/研究院）：0（样例为纯技术参数模板，无编制单位实体）。

结论：样例均为程序化合成，无真实联系人/单位/项目名 ✅。

### ④ 已推送后发现问题的重写历史流程 ✅（本次实际执行）

新仓库无协作者，重写历史 + force push 安全（plan/06 §3 前提成立）。执行记录：

```
$ git filter-branch --tree-filter \
    "find plan -name '*.md' -exec sed -i 's|C:.Users.<机主名>|C:\\\\Users\\\\<username>|g' {} +" \
    -- --all
$ rm -rf .git/refs/original && git reflog expire --expire=now --all && git gc --prune=now --aggressive
$ git log --all -p | grep -c "<机主名字面值>"   → 0
$ git -c http.proxy= -c https.proxy= push --force origin main
```

（实际执行结果回填：见文末"执行记录回填"。）

## 2. 发布门 ✅- **README 终版** ✅：简介/特性/mermaid 架构图/快速开始/评测表/目录/**限制（本次新增 6 条）**/
  免责声明/已知环境问题/License 齐全；状态行与路线图更新为 M1–M6 收官。
- **LICENSE** ✅：MIT（M1 起在库）。
- **干净环境 clone → 一次成功** ✅（本机模拟：新目录 `D:\ProgramData\zcode\_m6_cleanenv`
  git clone + `py -m venv` 全新 venv，逐条按 README 快速开始执行）：

| 步骤 | 结果 |
| --- | --- |
| `py -m planguard demo`（零依赖） | ✅ 一次成功 |
| 装 python-docx 后 `parse` gen_0001 | ✅ 参数卡 JSON |
| `check` gen_0001 + fs_0001（两类目） | ✅ md+docx 报告落盘 output/ |
| `ask` 深基坑/高支模专家论证门槛 | ✅ L3 阈值表命中直答（5m / 8m） |
| Web：uvicorn 起服 → /api/health、/（0 外链、vendor Vue 本地）、上传 /api/review、/api/ask | ✅ 全通（review 200：pass15/fail3/manual0，18 条结论；ask 200 route=threshold） |

- **发布级 bug 发现与修复**：干净环境实测发现 `pyproject.toml` web extras 漏声明
  `python-multipart`——FastAPI 的 `UploadFile = File(...)` 路由在**注册期**即需要它，缺失时
  uvicorn 启动即抛 `RuntimeError: Form data requires "python-multipart"`。M5 冒烟未暴露是因为
  当时跑在系统 Python（碰巧装过该包）。已补进 web extras 并新增回归测试
  `tests/test_m5.py::TestWebExtras`（82 项全绿）。

## 3. 功能门自查 ✅

- plan/ 与 data/ 台账齐全、来源可溯 ✅（M1–M5 持续维护）。
- 基准可复现达标 ✅：`py benchmarks/run_all.py` 2026-09-27 复跑 —— 解析 F1=1.0000（40 份）、
  端到端检出 100%（80/80）、强制误报 0；2.2s 零 API。
- 端到端 CLI + Web 断网演示 ✅（干净环境本轮再证一次，Web 页面 0 外链）。
- 测试全绿（含失败路径）✅：`PYTHONDONTWRITEBYTECODE=1` 连跑三轮 81 项 OK（2 skip 为可选依赖）；
  加入 M6 回归测试后 82 项全绿。

## 4. 初赛材料

不适用：用户确认不参赛（plan/06 §4 决策记录），方案书/PPT 不产出；
素材定位与创新点四条保留在 plan/06 §2，用户改主意时可按图索骥。

## 5. 本机环境偏差说明（不影响发布结论）

- 本机存在既知字节码损坏问题（README「已知环境问题」已记录），本轮在干净 venv 内以
  `pip 20.2.3` 装包时反复段错误（同根因）。对策：venv 建成后用**系统 pip
  `--target <venv>/Lib/site-packages`** 安装（重试 1–2 次即成功），依赖解析与版本选择照常，
  仅装包通道不同；仓库功能验证不受影响。
- 该问题为本机环境问题，与仓库内容无关；干净 Windows 机器按 README 流程不会遇到。

## 6. 执行记录回填（2026-09-27 实测）

- **历史重写（两轮 filter-branch --tree-filter，均作用于 plan/\*.md）**：
  - 第 1 轮：sed 将路径前缀 `C:\Users\<机主名>` → `C:\Users\<username>`（重写前勘察命中
    6 个提交 10 处：HANDOFF-M4×5、HANDOFF-M5×3、HANDOFF-M6×1、RELEASE-M6 旧版×1）；
  - 第 2 轮：清洗历史 blob 中残留的机主用户名字面值（RELEASE-M6 旧版两版里 grep 命令示例
    共 4 行）→ `<owner>`；
  - 每轮后均执行 `rm -rf .git/refs/original && git reflog expire --expire=now --all &&
    git gc --prune=now --aggressive`。
- **终验（全部 0）**：`git rev-list --all` 逐提交 `git grep "C:.Users.<机主名字面值>"` = 0；
  `git log --all -p | grep -c <机主名字面值>` = 0；提交信息扫描 = 0；工作树 = 0。
- **force push 实测**：代理直推失败（`Failed to connect to github.com port 443 via 127.0.0.1`，
  与交接文档记录一致）→ `git -c http.proxy= -c https.proxy= push --force origin main` 成功，
  远端 `f028207...9ae0d42 main -> main (forced update)`。
- **推送后复核**：GitHub 全新 clone 结果见下（历史 0 命中 + demo/测试复跑通过）。

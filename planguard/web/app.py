# -*- coding: utf-8 -*-
"""Web 审查面板（M5）：FastAPI + 本地 vendor Vue3（不依赖 CDN，断网可演示）。

接口：
- GET  /                审查面板页（static/index.html）
- GET  /api/health      健康检查
- POST /api/review      上传 docx/pdf → 完整流水线（orchestrator.run）→
                        三级结论报告 JSON（结构对齐 report/exporter.py 的 Markdown）
- POST /api/ask         条文问答（knowledge/store.ask）

启动：uvicorn planguard.web.app:create_app --factory
"""
import json
import shutil
import tempfile
from pathlib import Path

from .. import __version__

MAX_UPLOAD_MB = 50
ALLOWED_SUFFIXES = (".docx", ".pdf")

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"


def create_app():
    try:
        from fastapi import FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import FileResponse, JSONResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Web 面板需要 FastAPI。请先安装: "
            "NO_PROXY=\"*\" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .[web]"
        ) from exc

    app = FastAPI(title="PlanGuard", version=__version__)

    @app.get("/api/health")
    def health():
        return {"status": __import__("planguard").__status__, "version": __version__}

    @app.post("/api/review")
    async def review(file: UploadFile = File(...)):
        """上传方案 → 端到端审查 → 报告 JSON（含流水线各阶段计时）。"""
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(400, "不支持的格式: %s（支持 .docx / .pdf）" % (suffix or "未知"))
        tmp_dir = Path(tempfile.mkdtemp(prefix="planguard_web_"))
        try:
            doc_path = tmp_dir / ("upload" + suffix)
            with open(doc_path, "wb") as fh:
                shutil.copyfileobj(file.file, fh)
            from ..orchestrator import run

            result, trace = run(doc_path)
            summary = result.summary()
            order = {"fail": 0, "manual": 1, "pass": 2}
            findings = sorted(result.findings,
                              key=lambda f: (order.get(f.result, 9), f.rule_id))
            cards = [{
                "param_id": c.param_id, "name": c.name,
                "value": c.text_value if c.text_value is not None else c.value,
                "unit": c.unit or ("文本" if c.text_value is not None else ""),
                "section": c.evidence.section if c.evidence else "",
                "line": c.evidence.line_text if c.evidence else "",
            } for c in result.cards]
            return {
                "doc": file.filename,
                "summary": summary,
                "overall": _overall_text(summary),
                "findings": [{
                    "rule_id": f.rule_id, "rule_name": f.rule_name, "level": f.level,
                    "result": f.result, "result_label": _RESULT_LABEL.get(f.result, f.result),
                    "detail": f.detail, "basis": f.basis, "advice": f.advice,
                    "evidence": f.evidence_line,
                } for f in findings],
                "cards": cards,
                "stages": [{"name": st.name, "seconds": round(st.seconds, 4),
                            "status": st.status} for st in trace.stages],
                "discarded": result.meta.get("discarded", []),
                "rules_total": result.meta.get("rules_total"),
            }
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:  # noqa: BLE001  解析失败等，给可读错误而不是 500 堆栈
            raise HTTPException(400, "审查失败: %s: %s" % (type(exc).__name__, exc))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.post("/api/ask")
    async def ask(payload: dict):
        """条文知识库问答：L3 阈值命中直答，否则 L2 条文检索 top-k。"""
        query = str((payload or {}).get("query", "")).strip()
        if not query:
            raise HTTPException(400, "问题为空")
        from ..knowledge.store import DEFAULT_KNOWLEDGE_DIR, ask as kb_ask

        out = kb_ask(query, DEFAULT_KNOWLEDGE_DIR, top_k=3)
        return JSONResponse(out)

    @app.get("/")
    def index():
        index_html = _STATIC_DIR / "index.html"
        if not index_html.exists():
            raise HTTPException(404, "面板页面缺失（planguard/web/static/index.html）")
        return FileResponse(index_html)

    @app.get("/vendor/{name}")
    def vendor(name: str):
        """本地 vendor 资源（Vue3 等），断网可演示——不回源任何 CDN。"""
        path = (_STATIC_DIR / "vendor" / name).resolve()
        if not str(path).startswith(str((_STATIC_DIR / "vendor").resolve())) or not path.exists():
            raise HTTPException(404, "资源不存在")
        return FileResponse(path)

    @app.get("/favicon.ico")
    def favicon():
        raise HTTPException(404, "")

    return app


_RESULT_LABEL = {"fail": "不合规", "manual": "待人工确认", "pass": "通过"}


def _overall_text(summary: dict) -> str:
    if summary["fail"]:
        return "不合规 —— 存在强制条款不满足，须整改后复审。"
    if summary["manual"]:
        return "待人工确认 —— 自动核查未发现违规，但有 %d 项需人工复核。" % summary["manual"]
    return "通过（基于当前规则库）。"

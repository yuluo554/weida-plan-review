# -*- coding: utf-8 -*-
"""Web 面板入口（M5 实现）。懒加载 fastapi，骨架阶段不引入任何依赖。"""
from .. import __version__


def create_app():
    try:
        from fastapi import FastAPI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Web 面板在里程碑 M5 实现（plan/05-里程碑.md）；"
            "届时先安装依赖: pip install -e .[web]"
        ) from exc

    app = FastAPI(title="PlanGuard", version=__version__)

    @app.get("/api/health")
    def health():
        return {"status": __import__("planguard").__status__, "version": __version__}

    return app

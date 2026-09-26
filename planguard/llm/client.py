# -*- coding: utf-8 -*-
"""LLM 客户端（M4 实现）：OpenAI 兼容接口，只做兜底。

约定（plan/03 §5）：
- 数值结论永远来自确定性规则，LLM 仅做未命中参数的抽取兜底/别名归一/报告行文；
- 防幻觉三件套：候选行压缩；输出须含"条款编号+逐字摘录"且摘录为原文子串；数值范围校验；
- 客户端配置 enable_thinking=false；max_tokens 截断后 JSON 修复；重试+超时；失败降级规则通路。
"""
import os
from dataclasses import dataclass
from typing import Optional


class LLMNotConfigured(RuntimeError):
    """缺少 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 配置。"""


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 60.0
    max_retries: int = 2
    enable_thinking: bool = False  # qwen 系必须显式关闭，否则思考模式极慢

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", ""),
            timeout=float(os.environ.get("LLM_TIMEOUT", "60")),
        )


def is_configured(config: Optional[LLMConfig] = None) -> bool:
    cfg = config or LLMConfig.from_env()
    return bool(cfg.base_url and cfg.api_key and cfg.model)


class OpenAICompatClient:
    """OpenAI 兼容客户端骨架。M4 实现 complete_json()（含 JSON 修复与摘录校验）。"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        if not is_configured(self.config):
            raise LLMNotConfigured(
                "LLM 未配置（需要环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，"
                "参见 .env.example）。未配置时系统自动走纯规则通路。"
            )

    def complete_json(self, prompt: str) -> dict:
        raise NotImplementedError("LLM 兜底抽取在里程碑 M4 实现（plan/05-里程碑.md）。")

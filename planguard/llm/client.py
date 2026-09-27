# -*- coding: utf-8 -*-
"""LLM 客户端（M4）：OpenAI 兼容接口，只做兜底。

约定（plan/03 §5）：
- 数值结论永远来自确定性规则，LLM 仅做未命中参数的抽取兜底/别名归一/报告行文；
- 防幻觉三件套：候选行压缩；输出须含"条款编号+逐字摘录"且摘录为原文子串；数值范围校验；
- 客户端配置 enable_thinking=false；max_tokens 截断后 JSON 修复；重试+超时；失败降级规则通路。

传输用 urllib（零第三方依赖）。配置读环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，
缺省自动加载仓库根目录 .env（不入库）。
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Optional[Path] = None) -> dict:
    """读 KEY=VALUE 行的 .env 并 os.environ.setdefault；幂等，返回本次注入的键。"""
    path = Path(path or _ENV_PATH)
    loaded: dict = {}
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


class LLMNotConfigured(RuntimeError):
    """缺少 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 配置。"""


class LLMError(RuntimeError):
    """请求失败（网络/超时/限流/返回不可解析）。调用方应降级到纯规则通路。"""


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 60.0
    max_retries: int = 2
    max_tokens: int = 2000
    temperature: float = 0.1
    enable_thinking: bool = False  # qwen 系必须显式关闭，否则思考模式极慢

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_env()
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", ""),
            timeout=float(os.environ.get("LLM_TIMEOUT", "60")),
            max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
        )


def is_configured(config: Optional[LLMConfig] = None) -> bool:
    cfg = config or LLMConfig.from_env()
    return bool(cfg.base_url and cfg.api_key and cfg.model)


class OpenAICompatClient:
    """OpenAI 兼容客户端（chat/completions），带重试与 JSON 修复。"""

    # 4xx 配置类错误：重试无意义，立即失败
    _NO_RETRY_CODES = {400, 401, 403, 404}

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        if not is_configured(self.config):
            raise LLMNotConfigured(
                "LLM 未配置（需要环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，"
                "参见 .env.example）。未配置时系统自动走纯规则通路。"
            )

    # ---- 传输 ----

    def _request(self, payload: dict) -> dict:
        """单次 HTTP 调用（不含重试），返回响应 JSON。"""
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % self.config.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """补全请求，返回首个 choice 的文本 content；失败抛 LLMError。"""
        messages: List[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "enable_thinking": self.config.enable_thinking,  # qwen 系：显式关闭思考模式
        }
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                data = self._request(payload)
                content = data["choices"][0]["message"].get("content") or ""
                if content.strip():
                    return content
                raise LLMError("LLM 返回空 content（可能被截断或为思考输出）")
            except urllib.error.HTTPError as exc:
                if exc.code in self._NO_RETRY_CODES:
                    raise LLMError("LLM 请求被拒绝（HTTP %d，请检查 LLM_API_KEY/LLM_MODEL）" % exc.code) from exc
                last_exc = exc
            except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                    IndexError, json.JSONDecodeError) as exc:
                last_exc = exc
            if attempt < self.config.max_retries:
                time.sleep(min(2 ** attempt, 4))  # 1s, 2s 退避
        raise LLMError("LLM 请求失败（已重试 %d 次）: %s" % (self.config.max_retries, last_exc))

    def complete_json(self, prompt: str, system: Optional[str] = None) -> Union[dict, list]:
        """补全并解析 JSON：容忍 markdown 代码围栏与 max_tokens 截断；不可解析抛 LLMError。"""
        text = self.complete(prompt, system=system)
        parsed = _loads_lenient(_strip_noise(text))
        if parsed is None:
            raise LLMError("LLM 返回内容无法解析为 JSON: %r" % text[:200])
        return parsed


# ---- JSON 容错解析 ----

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _strip_noise(text: str) -> str:
    """剥掉 markdown 围栏与 JSON 前后的说明文字，取首个 { 或 [ 起。"""
    t = text.strip()
    m = _FENCE_RE.search(t)
    if m:
        t = m.group(1).strip()
    starts = [p for p in (t.find("{"), t.find("[")) if p >= 0]
    if starts and min(starts) > 0:
        t = t[min(starts):]
    return t.strip()


def _loads_lenient(text: str) -> Optional[Any]:
    """json.loads → 去尾逗号 → 截断修复（补引号/括号）三级尝试。"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    t = re.sub(r",\s*([}\]])", r"\1", text).strip()
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        pass
    t2 = _close_truncated(t)
    try:
        return json.loads(t2)
    except (json.JSONDecodeError, ValueError):
        return None


def _close_truncated(t: str) -> str:
    """max_tokens 截断修复：扫描括号栈，截到最后一个完整闭合点并补齐未闭合的引号与括号。"""
    stack: List[str] = []
    in_str = False
    esc = False
    end = len(t)
    for idx, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            expected_open = "{" if ch == "}" else "["
            if not stack:
                end = idx  # 多余的闭合符：其后是解释性文字 → 丢弃
                break
            if stack[-1] != expected_open:
                end = idx  # 错位闭合符（截断产物）：停在闭合点前，按未闭合补齐
                break
            stack.pop()
            if not stack:
                end = idx + 1  # 顶层闭合 → 其后为解释性文字，截断
                break
    prefix = t[:end]
    if in_str:
        prefix += '"'
    prefix = re.sub(r",\s*$", "", prefix)
    prefix += "".join("}" if c == "{" else "]" for c in reversed(stack))
    return prefix

"""
LLM 客户端：双模式封装。

模式切换：
- 在线模式（DEEPSEEK_API_KEY 环境变量存在）：调 DeepSeek API
- 离线模式（无 API Key）：生成 prompt 文件，等待外部执行，读取结果 JSON

离线模式兼容现有"人肉协议"：
  generate_ai_texts.py prepare → analysis_prompt.md
  → 外部 Agent/人 执行 LLM → llm_analysis.json
  → generate_ai_texts.py compile

在线模式则由本模块直接调 API 生成 llm_analysis.json，无需人工介入。
"""

import os
import json
import time
import ssl
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """LLM 响应"""
    success: bool
    content: str = ""
    usage: dict = None
    error: str = ""
    mode: str = ""  # online / offline
    duration_ms: int = 0

    def __bool__(self):
        return self.success


class LLMClient:
    """LLM 客户端：双模式。

    在线模式：DEEPSEEK_API_KEY 环境变量存在时启用
    离线模式：生成 prompt，等待外部执行后读取结果
    """

    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEFAULT_MODEL = "deepseek-chat"
    DEFAULT_TIMEOUT = 120
    MAX_RETRIES = 3

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or self.DEEPSEEK_API_URL
        self.mode = "online" if self.api_key else "offline"

    def is_online(self) -> bool:
        return self.mode == "online"

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> LLMResponse:
        """对话接口。

        在线模式：调 DeepSeek API
        离线模式：返回提示，由调用方处理（生成 prompt 文件等待外部执行）
        """
        if self.is_online():
            return self._chat_online(system_prompt, user_prompt, temperature)
        return self._chat_offline(system_prompt, user_prompt)

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> LLMResponse:
        """对话接口（要求 JSON 输出）。

        在线模式：调 API + 解析 JSON
        离线模式：生成 prompt 文件，等待外部执行后由调用方读取结果 JSON
        """
        if self.is_online():
            resp = self._chat_online(system_prompt, user_prompt, temperature, json_mode=True)
            if resp.success:
                # 尝试解析 JSON
                try:
                    content = resp.content.strip()
                    # 去除可能的 markdown 代码块包裹
                    if content.startswith("```"):
                        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    resp.usage = json.loads(content) if isinstance(resp.usage, type(None)) else resp.usage
                    resp.usage = {"parsed_json": json.loads(content), "raw_tokens": resp.usage or {}}
                except json.JSONDecodeError as e:
                    return LLMResponse(success=False, error=f"JSON 解析失败: {e}", mode="online", duration_ms=resp.duration_ms)
            return resp
        return self._chat_offline(system_prompt, user_prompt, json_mode=True)

    def _chat_online(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool = False) -> LLMResponse:
        """在线模式：调 DeepSeek API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=headers, method="POST")

        last_err = ""
        for attempt in range(self.MAX_RETRIES):
            start = time.time()
            try:
                # 跳过 SSL 验证（代理环境自签证书）
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=self.DEFAULT_TIMEOUT, context=ssl_ctx) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    duration_ms = int((time.time() - start) * 1000)
                    content = body["choices"][0]["message"]["content"]
                    usage = body.get("usage", {})
                    return LLMResponse(
                        success=True,
                        content=content,
                        usage=usage,
                        mode="online",
                        duration_ms=duration_ms,
                    )
            except urllib.error.HTTPError as e:
                duration_ms = int((time.time() - start) * 1000)
                last_err = f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}"
                if e.code == 429:
                    time.sleep(2 ** attempt)  # 限流退避
                elif e.code >= 500:
                    time.sleep(1 + attempt)
                else:
                    break  # 4xx 非限流不重试
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                last_err = str(e)
                time.sleep(1 + attempt)

        return LLMResponse(success=False, error=f"重试 {self.MAX_RETRIES} 次失败: {last_err}", mode="online", duration_ms=0)

    def _chat_offline(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> LLMResponse:
        """离线模式：返回 prompt 信息，由调用方写入文件等待外部执行。

        调用方应：
        1. 把 system_prompt + user_prompt 写入 analysis_prompt.md
        2. 等待外部（Agent/人）执行 LLM，生成 llm_analysis.json
        3. 读取 llm_analysis.json 继续后续流程
        """
        return LLMResponse(
            success=False,
            error="离线模式：需外部执行 LLM。请将 prompt 写入文件，外部执行后读取结果 JSON。",
            mode="offline",
            content=user_prompt,
        )

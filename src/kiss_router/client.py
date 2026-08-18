import asyncio
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ModelConfig
from .models import ChatResult


class ChatClient:
    async def chat(self, config: ModelConfig, messages: list[dict[str, str]]) -> ChatResult:
        return await asyncio.to_thread(self._chat, config, messages)

    @staticmethod
    def _chat(config: ModelConfig, messages: list[dict[str, str]]) -> ChatResult:
        payload = json.dumps({"model": config.model, "messages": messages,
                              "temperature": config.temperature, "max_tokens": config.max_tokens}).encode()
        request = Request(config.endpoint.rstrip("/") + "/chat/completions", payload,
                          {"Content-Type": "application/json"}, method="POST")
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                data = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"{config.id} request failed: {error}") from error
        try:
            usage = data.get("usage", {})
            return ChatResult(data["choices"][0]["message"]["content"], data.get("model", config.model),
                              usage.get("prompt_tokens"), usage.get("completion_tokens"),
                              round((time.perf_counter() - started) * 1000))
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(f"{config.id} returned an invalid chat completion") from error

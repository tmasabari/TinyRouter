import json
import logging

from .client import ChatClient
from .config import ModelConfig
from .models import CapabilityResult, ChatResult

log = logging.getLogger("tinyrouter.worker")


class ModelWorker:
    def __init__(self, client: ChatClient, config: ModelConfig):
        self.client, self.config = client, config

    async def invoke(self, messages: list[dict[str, str]]) -> CapabilityResult:
        result = await self.client.chat(self.config, [{"role": "system", "content": self.config.capability_prompt}, *messages])
        try:
            data = json.loads(result.content)
            status = data["status"]
            reason = data["reason_code"]
            answer = data.get("answer", "")
            if status not in {"can_handle", "escalate"} or not isinstance(reason, str) or not reason.strip() or not isinstance(answer, str):
                raise ValueError("invalid capability response")
            if status == "can_handle" and not answer.strip():
                raise ValueError("can_handle requires answer")
            if status == "escalate" and answer.strip():
                log.warning("%s returned an answer while escalating; answer ignored", self.config.id)
                answer = ""
            return CapabilityResult(status == "can_handle", reason, answer, result)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"{self.config.id} returned an invalid capability response") from error

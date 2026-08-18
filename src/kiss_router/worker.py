import json

from .client import ChatClient
from .config import ModelConfig
from .models import CapabilityResult


class ModelWorker:
    def __init__(self, client: ChatClient, config: ModelConfig, capability_prompt: str):
        self.client, self.config, self.capability_prompt = client, config, capability_prompt

    async def invoke(self, messages):
        result = await self.client.chat(
            self.config,
            [{"role": "system", "content": self.capability_prompt}, *messages],
        )
        try:
            data = json.loads(result.content)
            status = data["status"]
            reason = data["reason_code"]
            answer = data.get("answer", "")
            if status not in {"can_handle", "escalate"} or not isinstance(reason, str) or not isinstance(answer, str):
                raise ValueError("invalid capability response")
            if status == "can_handle" and not answer.strip():
                raise ValueError("can_handle requires answer")
            if status == "escalate":
                answer = ""
            return CapabilityResult(status == "can_handle", reason, answer, result)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{self.config.id} returned invalid capability response") from error

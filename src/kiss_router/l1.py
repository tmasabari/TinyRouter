import json

from .client import ChatClient
from .config import ModelConfig
from .models import RouteDecision


class L1Router:
    def __init__(self, client: ChatClient, config: ModelConfig, routing_prompt: str, low_confidence_threshold: float):
        self.client, self.config = client, config
        self.routing_prompt, self.low_confidence_threshold = routing_prompt, low_confidence_threshold

    async def route(self, prompt: str) -> RouteDecision:
        messages = [{"role": "system", "content": self.routing_prompt}, {"role": "user", "content": prompt}]
        for retry in range(2):
            result = await self.client.chat(self.config, messages)
            try:
                data = json.loads(result.content)
                route, confidence, reason = data["route"], data["confidence"], data["reason_code"]
                if route in {"l1", "l2"} and isinstance(confidence, (int, float)) and 0 <= confidence <= 1 and isinstance(reason, str):
                    if route == "l1" and confidence < self.low_confidence_threshold:
                        return RouteDecision("l2", "l1_low_confidence", confidence=float(confidence), reason_code=reason)
                    return RouteDecision(route, "l1", confidence=float(confidence), reason_code=reason)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
            messages[0] = {"role": "system", "content": self.routing_prompt + " Invalid output. Return JSON only."}
        return RouteDecision("l2", "l1_invalid")

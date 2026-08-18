import json

from .client import ChatClient
from .config import ModelConfig
from .models import ChatResult, RouteDecision


class L1Router:
    def __init__(self, client: ChatClient, config: ModelConfig, routing_prompt: str, low_confidence_threshold: float):
        self.client, self.config = client, config
        self.routing_prompt, self.low_confidence_threshold = routing_prompt, low_confidence_threshold

    async def route(self, prompt: str, messages: list[dict[str, str]]) -> tuple[RouteDecision, ChatResult]:
        routing_messages = [{"role": "system", "content": self.routing_prompt}, {"role": "user", "content": prompt}]
        for retry in range(2):
            result = await self.client.chat(self.config, routing_messages)
            try:
                data = json.loads(result.content)
                route, confidence, reason = data["route"], data["confidence"], data["reason_code"]
                if route not in {"l1", "l2"} or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1 or not isinstance(reason, str):
                    raise ValueError("invalid routing response")
                if confidence < self.low_confidence_threshold:
                    return RouteDecision("l2", "l1_low_confidence", confidence=float(confidence), reason_code=reason), result
                if route == "l1":
                    answer = data.get("answer")
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError("l1 response requires answer")
                    return RouteDecision("l1", "l1", confidence=float(confidence), reason_code=reason), ChatResult(answer, result.model, result.input_tokens, result.output_tokens, result.latency_ms)
                return RouteDecision("l2", "l1", confidence=float(confidence), reason_code=reason), result
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                routing_messages[0] = {"role": "system", "content": self.routing_prompt + " Invalid output. Return JSON only with route, confidence, reason_code and answer when route=l1."}
        return RouteDecision("l2", "l1_invalid"), result

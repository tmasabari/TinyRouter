import time
from uuid import uuid4

from .client import ChatClient
from .config import RouterConfig
from .l1 import L1Router
from .models import HandleResult, RoutingEvent
from .rules import evaluate


class Orchestrator:
    def __init__(self, config: RouterConfig, client: ChatClient):
        self.config, self.client = config, client
        self.l1 = L1Router(client, config.models["l1"], config.routing_prompt, config.low_confidence_threshold)
        self.events: list[RoutingEvent] = []

    async def handle(self, messages: list[dict[str, str]]) -> HandleResult:
        prompt = "\n".join(message["content"] for message in messages if message.get("role") == "user")
        if not prompt:
            raise ValueError("a user message is required")
        started, request_id = time.perf_counter(), str(uuid4())
        decision = evaluate(prompt, self.config.rules, self.config.default_route)
        l1_result = None
        l1_latency = 0
        target = self.config.models[decision.route]
        try:
            if decision.route == "l1":
                decision, l1_result = await self.l1.route(prompt, messages)
                l1_latency = l1_result.latency_ms
                target = self.config.models[decision.route]
                response = l1_result if decision.route == "l1" else await self.client.chat(target, messages)
            else:
                response = await self.client.chat(target, messages)
            event = self._event(request_id, decision, target.name, response, prompt, started, l1_result, l1_latency)
            self.events.append(event)
            return HandleResult(response, decision, event)
        except Exception as exc:
            event = self._event(request_id, decision, target.name, None, prompt, started, l1_result, l1_latency, str(exc))
            self.events.append(event)
            raise

    @staticmethod
    def _event(request_id, decision, model, response, prompt, started, l1_result, l1_latency, error=None):
        return RoutingEvent(request_id, decision.route, decision.source, decision.rule, model,
                            round((time.perf_counter() - started) * 1000), len(prompt),
                            response.input_tokens if response else None,
                            response.output_tokens if response else None,
                            decision.confidence, error is None,
                            decision.source.startswith("l1"), l1_latency,
                            l1_result.input_tokens if l1_result else None,
                            l1_result.output_tokens if l1_result else None, error)

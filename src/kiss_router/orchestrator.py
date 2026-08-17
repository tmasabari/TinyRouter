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
        if decision.route == "l1":
            decision = await self.l1.route(prompt)
        target = self.config.models[decision.route]
        response = await self.client.chat(target, messages)
        event = RoutingEvent(request_id, decision.route, decision.source, decision.rule, response.model,
                             round((time.perf_counter() - started) * 1000), len(prompt), response.input_tokens,
                             response.output_tokens, decision.confidence, True, decision.source.startswith("l1"))
        self.events.append(event)
        return HandleResult(response, decision, event)

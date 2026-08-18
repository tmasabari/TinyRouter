import re
import time
from uuid import uuid4

from .client import ChatClient
from .config import RouterConfig
from .models import HandleResult, RouteDecision, RoutingEvent
from .rules import evaluate
from .worker import ModelWorker


class Orchestrator:
    def __init__(self, config: RouterConfig, client: ChatClient, logger=None):
        self.config, self.client, self.logger = config, client, logger
        self.workers = {key: ModelWorker(client, model, model.capability_prompt) for key, model in config.models.items()}
        self.events = []

    async def handle(self, messages):
        messages, override = self._model_override(messages)
        prompt = "\n".join(m["content"] for m in messages if m.get("role") == "user")
        if not prompt:
            raise ValueError("a user message is required")
        request_id, started = str(uuid4()), time.perf_counter()
        if override:
            result = await self.client.chat(self.config.models[override], messages)
            decision = RouteDecision(override, "user_override")
            return self._finish(request_id, decision, result, prompt, started, 1)

        decision = evaluate(prompt, self.config.rules, self.config.default_route)
        visited = set()
        for hop in range(self.config.max_hops):
            route = decision.route
            if route in visited:
                raise RuntimeError(f"routing cycle detected at {route}")
            visited.add(route)
            worker = self.workers[route]
            self.logger.debug("request=%s hop=%d model=%s source=%s", request_id, hop, route, decision.source) if self.logger else None
            try:
                capability = await worker.invoke(messages)
            except Exception as error:
                self.logger.error("request=%s model=%s error=%s", request_id, route, error) if self.logger else None
                raise
            if capability.can_handle:
                result = capability.result
                result = type(result)(capability.answer, result.model, result.input_tokens, result.output_tokens, result.latency_ms)
                return self._finish(request_id, RouteDecision(route, decision.source, decision.rule, capability.reason_code), result, prompt, started, hop + 1)
            next_decision = evaluate(prompt, self.config.rules, self.config.escalation_defaults.get(route, ""), route, capability.reason_code)
            if not next_decision.route or next_decision.route == route:
                raise RuntimeError(f"no escalation route configured for {route}: {capability.reason_code}")
            decision = next_decision

        raise RuntimeError(f"maximum routing hops exceeded ({self.config.max_hops})")

    def _finish(self, request_id, decision, response, prompt, started, hops):
        event = RoutingEvent(request_id, decision.route, decision.source, decision.rule, response.model,
                             round((time.perf_counter() - started) * 1000), len(prompt),
                             response.input_tokens, response.output_tokens, True,
                             hops > 1, hops=hops)
        self.events.append(event)
        if self.logger:
            self.logger.info("request=%s route=%s model=%s hops=%d latency_ms=%d", request_id, decision.route, response.model, hops, event.latency_ms)
        return HandleResult(response, decision, event)

    def _model_override(self, messages):
        for index, message in enumerate(messages):
            if message.get("role") != "user":
                continue
            match = re.match(r"^@(l\d+)(?:\s+|$)", message["content"], re.IGNORECASE)
            if not match:
                return messages, None
            route = match.group(1).lower()
            if route not in self.config.models:
                raise ValueError(f"model override {route} is not configured")
            updated = [dict(item) for item in messages]
            updated[index]["content"] = message["content"][match.end():].lstrip()
            return updated, route
        return messages, None

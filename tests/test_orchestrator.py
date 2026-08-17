import unittest

from kiss_router.config import ModelConfig, RouterConfig, RuleConfig
from kiss_router.models import ChatResult
from kiss_router.orchestrator import Orchestrator


class FakeClient:
    def __init__(self, replies): self.replies, self.calls = iter(replies), []
    async def chat(self, config, messages):
        self.calls.append(config.id)
        return ChatResult(next(self.replies), config.model)


def config(rules=()):
    models = {key: ModelConfig(key, key, "http://localhost/v1", key, 1, 0, 1) for key in ("l1", "l2")}
    return RouterConfig(models, rules, "l1", "Return JSON", 0.7)


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_rule_bypasses_l1(self):
        client = FakeClient(["answer"])
        router = Orchestrator(config((RuleConfig("code", True, {"keywords": {"any": ["debug"]}}, "l2"),)), client)
        result = await router.handle([{"role": "user", "content": "debug this"}])
        self.assertEqual(client.calls, ["l2"])
        self.assertEqual(result.event.source, "rules")

    async def test_l1_escalates_to_l2(self):
        client = FakeClient(['{"route":"l2","confidence":0.9,"reason_code":"hard"}', "answer"])
        router = Orchestrator(config(), client)
        result = await router.handle([{"role": "user", "content": "compare options"}])
        self.assertEqual(client.calls, ["l1", "l2"])
        self.assertTrue(result.event.escalation)

    async def test_invalid_l1_json_retries_then_falls_back_to_l2(self):
        client = FakeClient(["not json", "still not json", "answer"])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "hello"}])
        self.assertEqual(client.calls, ["l1", "l1", "l2"])
        self.assertEqual(result.decision.source, "l1_invalid")

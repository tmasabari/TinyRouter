import unittest

from kiss_router.config import ModelConfig, RouterConfig, RuleConfig, ServerConfig
from kiss_router.models import ChatResult
from kiss_router.orchestrator import Orchestrator


class FakeClient:
    def __init__(self, replies): self.replies, self.calls = iter(replies), []
    async def chat(self, config, messages):
        self.calls.append(config.id)
        return ChatResult(next(self.replies), config.model, 10, 2, 5)


def config(rules=()):
    models = {key: ModelConfig(key, key, "http://localhost/v1", key, 1, 0, 10) for key in ("l1", "l2")}
    return RouterConfig(ServerConfig("127.0.0.1", 8090), models, rules, "l1", "Return JSON", 0.7)


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_rule_bypasses_l1(self):
        client = FakeClient(["answer"])
        router = Orchestrator(config((RuleConfig("code", True, {"keywords": {"any": ["debug"]}}, "l2"),)), client)
        result = await router.handle([{"role": "user", "content": "debug this"}])
        self.assertEqual(client.calls, ["l2"])
        self.assertEqual(result.event.source, "rules")

    async def test_l1_answers_without_second_l1_call(self):
        client = FakeClient(['{"route":"l1","confidence":0.9,"reason_code":"simple","answer":"hello"}'])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "hello"}])
        self.assertEqual(client.calls, ["l1"])
        self.assertEqual(result.response.content, "hello")
        self.assertEqual(result.decision.route, "l1")

    async def test_l1_escalates_to_l2(self):
        client = FakeClient(['{"route":"l2","confidence":0.9,"reason_code":"hard"}', "answer"])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "compare options"}])
        self.assertEqual(client.calls, ["l1", "l2"])
        self.assertTrue(result.event.escalation)
        self.assertEqual(result.event.l1_output_tokens, 2)

    async def test_invalid_l1_json_retries_then_falls_back_to_l2(self):
        client = FakeClient(["not json", "still not json", "answer"])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "hello"}])
        self.assertEqual(client.calls, ["l1", "l1", "l2"])
        self.assertEqual(result.decision.source, "l1_invalid")

    async def test_l1_low_confidence_escalates(self):
        client = FakeClient(['{"route":"l1","confidence":0.5,"reason_code":"uncertain"}', "answer"])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "maybe"}])
        self.assertEqual(client.calls, ["l1", "l2"])
        self.assertEqual(result.decision.source, "l1_low_confidence")

    async def test_failure_is_recorded(self):
        class FailingClient(FakeClient):
            async def chat(self, config, messages):
                self.calls.append(config.id)
                raise RuntimeError("boom")
        router = Orchestrator(config(), FailingClient([]))
        with self.assertRaises(RuntimeError):
            await router.handle([{"role": "user", "content": "hello"}])
        self.assertFalse(router.events[-1].success)
        self.assertEqual(router.events[-1].error, "boom")

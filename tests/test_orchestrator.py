import unittest

from kiss_router.config import ModelConfig, RouterConfig, RuleConfig, ServerConfig
from kiss_router.models import ChatResult
from kiss_router.orchestrator import Orchestrator


class FakeClient:
    def __init__(self, replies): self.replies, self.calls = iter(replies), []
    async def chat(self, config, messages):
        self.calls.append((config.id, messages))
        return ChatResult(next(self.replies), config.model, 10, 2, 5)


def config(rules=()):
    models = {key: ModelConfig(key, key, "http://localhost/v1", key, "Return capability JSON", 1, 0, 10) for key in ("l1", "l2", "l3")}
    return RouterConfig(ServerConfig("127.0.0.1", 8090), models, rules, "l1", {"l1": "l2", "l2": "l3"}, type("Log", (), {"level":"INFO","console":False,"file":None,"queue_size":10,"include_content":False})())


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_rule_routes_to_l2_and_l2_answers(self):
        client = FakeClient(['{"status":"can_handle","reason_code":"simple","answer":"answer"}'])
        router = Orchestrator(config((RuleConfig("code", True, {"keywords": {"any": ["debug"]}}, "l2"),)), client)
        result = await router.handle([{"role": "user", "content": "debug this"}])
        self.assertEqual([call[0] for call in client.calls], ["l2"])
        self.assertEqual(result.response.content, "answer")
        self.assertEqual(result.event.source, "rules")

    async def test_l1_answers(self):
        client = FakeClient(['{"status":"can_handle","reason_code":"simple","answer":"hello"}'])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "hello"}])
        self.assertEqual([call[0] for call in client.calls], ["l1"])
        self.assertEqual(result.response.content, "hello")

    async def test_l1_escalates_and_rules_select_l2(self):
        client = FakeClient(['{"status":"escalate","reason_code":"complex_reasoning","answer":""}', '{"status":"can_handle","reason_code":"answer","answer":"done"}'])
        rules = (RuleConfig("complex", True, {"reason_codes": {"any": ["complex_reasoning"]}}, "l2", "l1"),)
        result = await Orchestrator(config(rules), client).handle([{"role": "user", "content": "hard"}])
        self.assertEqual([call[0] for call in client.calls], ["l1", "l2"])
        self.assertTrue(result.event.escalation)

    async def test_l2_escalates_to_l3(self):
        client = FakeClient([
            '{"status":"escalate","reason_code":"complex_reasoning","answer":""}',
            '{"status":"escalate","reason_code":"needs_more_reasoning","answer":""}',
            '{"status":"can_handle","reason_code":"final","answer":"done"}',
        ])
        rules = (
            RuleConfig("l1hard", True, {"reason_codes": {"any": ["complex_reasoning"]}}, "l2", "l1"),
            RuleConfig("l2hard", True, {"reason_codes": {"any": ["needs_more_reasoning"]}}, "l3", "l2"),
        )
        result = await Orchestrator(config(rules), client).handle([{"role": "user", "content": "hard"}])
        self.assertEqual([call[0] for call in client.calls], ["l1", "l2", "l3"])
        self.assertEqual(result.response.content, "done")

    async def test_user_override_bypasses_capability_routing(self):
        client = FakeClient(["direct answer"])
        result = await Orchestrator(config(), client).handle([{"role": "user", "content": "@l3 Explain the architecture."}])
        self.assertEqual([call[0] for call in client.calls], ["l3"])
        self.assertEqual(client.calls[0][1][0]["content"], "Explain the architecture.")
        self.assertEqual(result.decision.source, "user_override")

    async def test_unknown_override_rejected(self):
        with self.assertRaises(ValueError):
            await Orchestrator(config(), FakeClient([])).handle([{"role": "user", "content": "@l9 hello"}])

    async def test_cycle_is_rejected(self):
        client = FakeClient(['{"status":"escalate","reason_code":"hard","answer":""}'])
        rules = (RuleConfig("cycle", True, {"reason_codes": {"any": ["hard"]}}, "l1", "l1"),)
        with self.assertRaises(RuntimeError):
            await Orchestrator(config(rules), client).handle([{"role": "user", "content": "hard"}])

    async def test_failure_is_recorded(self):
        class FailingClient(FakeClient):
            async def chat(self, config, messages):
                self.calls.append((config.id, messages))
                raise RuntimeError("boom")
        router = Orchestrator(config(), FailingClient([]))
        with self.assertRaises(RuntimeError):
            await router.handle([{"role": "user", "content": "hello"}])
        self.assertFalse(router.events[-1].success)
        self.assertEqual(router.events[-1].error, "boom")

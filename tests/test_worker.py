import unittest

from kiss_router.config import ModelConfig
from kiss_router.models import ChatResult
from kiss_router.worker import ModelWorker


class FakeClient:
    def __init__(self, content):
        self.content = content

    async def chat(self, config, messages):
        return ChatResult(self.content, config.model, 1, 1, 1)


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return ModelConfig("l1", "l1", "http://localhost/v1", "l1", "Return JSON", 1, 0, 10)

    async def test_can_handle(self):
        result = await ModelWorker(FakeClient('{"status":"can_handle","reason_code":"simple","answer":"ok"}'), self.config()).invoke([])
        self.assertTrue(result.can_handle)
        self.assertEqual(result.answer, "ok")

    async def test_escalate_discards_answer(self):
        result = await ModelWorker(FakeClient('{"status":"escalate","reason_code":"hard","answer":"ignore"}'), self.config()).invoke([])
        self.assertFalse(result.can_handle)
        self.assertEqual(result.answer, "")

    async def test_invalid_response_fails(self):
        with self.assertRaises(RuntimeError):
            await ModelWorker(FakeClient('{"status":"can_handle","reason_code":"simple","answer":""}'), self.config()).invoke([])

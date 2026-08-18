import logging
import tempfile
import unittest
from pathlib import Path

from kiss_router.logger import AsyncLogger, TRACE


class LoggerTests(unittest.TestCase):
    def test_trace_level(self):
        logger = AsyncLogger(type("Config", (), {"level": "TRACE", "console": False, "file": None, "queue_size": 10})())
        try:
            self.assertEqual(logger.logger.level, TRACE)
            self.assertTrue(logger.logger.isEnabledFor(TRACE))
        finally:
            logger.close()

    def test_file_logging_is_flushed_on_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "router.log"
            logger = AsyncLogger(type("Config", (), {"level": "INFO", "console": False, "file": str(path), "queue_size": 10})())
            logger.info("hello")
            logger.close()
            self.assertIn("hello", path.read_text(encoding="utf-8"))

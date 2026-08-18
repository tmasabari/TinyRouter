import tempfile
import unittest
from pathlib import Path

from kiss_router.logger import AsyncLogger


class LoggerTests(unittest.TestCase):
    def test_trace_level_and_file_logging(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "router.log"
            config = type("Log", (), {"level":"TRACE", "console":False, "file":str(path), "queue_size":10})()
            logger = AsyncLogger(config)
            logger.trace("trace-test")
            logger.close()
            self.assertIn("trace-test", path.read_text(encoding="utf-8"))

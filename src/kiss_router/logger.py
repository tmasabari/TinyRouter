import logging
import queue
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = _trace


class AsyncLogger:
    def __init__(self, config):
        self.queue = queue.Queue(maxsize=config.queue_size)
        self.logger = logging.getLogger("tinyrouter")
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()
        level = TRACE if config.level == "TRACE" else getattr(logging, config.level)
        self.logger.setLevel(level)
        self.logger.propagate = False
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handlers = []
        if config.console:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            handlers.append(handler)
        if config.file:
            path = Path(config.file)
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setFormatter(formatter)
            handlers.append(handler)
        self.handlers = handlers
        self.handler = QueueHandler(self.queue)
        self.logger.addHandler(self.handler)
        self.listener = QueueListener(self.queue, *handlers, respect_handler_level=True)
        self.listener.start()
        self._closed = False

    def __getattr__(self, name):
        return getattr(self.logger, name)

    def close(self):
        if self._closed:
            return
        self.listener.stop()
        self.logger.removeHandler(self.handler)
        self.handler.close()
        for handler in self.handlers:
            handler.close()
        self._closed = True

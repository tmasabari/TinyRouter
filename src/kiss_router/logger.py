import logging
import queue
from logging.handlers import QueueHandler, QueueListener

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = _trace


class AsyncLogger:
    def __init__(self, level="INFO", console=True, file=None, queue_size=4096):
        self.queue = queue.Queue(maxsize=queue_size)
        self.logger = logging.getLogger("tinyrouter")
        self.logger.handlers.clear()
        self.logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        self.logger.propagate = False
        handlers = []
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        if console:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            handlers.append(handler)
        if file:
            handler = logging.FileHandler(file, encoding="utf-8")
            handler.setFormatter(formatter)
            handlers.append(handler)
        self.handler = QueueHandler(self.queue)
        self.logger.addHandler(self.handler)
        self.listener = QueueListener(self.queue, *handlers, respect_handler_level=True)
        self.listener.start()

    def close(self):
        self.listener.stop()
        self.logger.removeHandler(self.handler)


def create_logger(config):
    return AsyncLogger(
        config.get("level", "INFO"),
        config.get("console", True),
        config.get("file"),
        config.get("queue_size", 4096),
    )

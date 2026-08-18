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
    def __init__(self, config):
        self.queue = queue.Queue(maxsize=config.queue_size)
        self.logger = logging.getLogger("tinyrouter")
        self.logger.handlers.clear()
        self.logger.setLevel(getattr(logging, config.level))
        self.logger.propagate = False
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handlers = []
        if config.console:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            handlers.append(handler)
        if config.file:
            handler = logging.FileHandler(config.file, encoding="utf-8")
            handler.setFormatter(formatter)
            handlers.append(handler)
        self.handler = QueueHandler(self.queue)
        self.logger.addHandler(self.handler)
        self.listener = QueueListener(self.queue, *handlers, respect_handler_level=True)
        self.listener.start()

    def __getattr__(self, name):
        return getattr(self.logger, name)

    def close(self):
        self.listener.stop()
        self.logger.removeHandler(self.handler)

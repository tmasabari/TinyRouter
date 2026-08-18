import tempfile
import unittest
from pathlib import Path

from kiss_router.config import ConfigError, load_config


VALID = '''
version: 1
server: {host: 127.0.0.1, port: 8090}
models:
  - {id: l1, name: l1, endpoint: http://127.0.0.1:8081/v1, model: l1, capability_prompt: Return JSON, timeout_seconds: 10, temperature: 0, max_tokens: 10}
  - {id: l2, name: l2, endpoint: http://127.0.0.1:8082/v1, model: l2, capability_prompt: Return JSON, timeout_seconds: 10, temperature: 0.2, max_tokens: 10}
routing:
  max_hops: 3
  default_route: l1
  escalation_defaults: {l1: l2}
  rules: []
logging: {level: INFO, console: false}
'''


class ConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "router.yaml"
            path.write_text(text, encoding="utf-8")
            return load_config(path)

    def test_valid_config(self):
        config = self.load(VALID)
        self.assertEqual(config.server.port, 8090)
        self.assertEqual(config.max_hops, 3)
        self.assertEqual(config.escalation_defaults["l1"], "l2")

    def test_invalid_prompt_operator_fails_fast(self):
        with self.assertRaises(ConfigError):
            self.load(VALID.replace("rules: []", "rules: [{name: bad, enabled: true, condition: {prompt_chars: {bad: 1}}, route: l2}]"))

    def test_invalid_route_fails_fast(self):
        with self.assertRaises(ConfigError):
            self.load(VALID.replace("default_route: l1", "default_route: l3"))

    def test_invalid_rule_source_fails_fast(self):
        with self.assertRaises(ConfigError):
            self.load(VALID.replace("rules: []", "rules: [{name: bad, enabled: true, source: l3, condition: {reason_codes: {any: [hard]}}, route: l2}]"))

    def test_invalid_max_hops_fails_fast(self):
        with self.assertRaises(ConfigError):
            self.load(VALID.replace("max_hops: 3", "max_hops: 0"))

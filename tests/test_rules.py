import unittest

from kiss_router.config import RuleConfig
from kiss_router.rules import evaluate


class RulesTests(unittest.TestCase):
    def test_first_enabled_match_wins_case_insensitively(self):
        rules = (RuleConfig("off", False, {"keywords": {"any": ["debug"]}}, "l1"),
                 RuleConfig("coding", True, {"keywords": {"any": ["debug"]}}, "l2"))
        result = evaluate("Please DEBUG this", rules, "l1")
        self.assertEqual((result.route, result.rule), ("l2", "coding"))

    def test_length_is_strictly_greater(self):
        rule = RuleConfig("long", True, {"prompt_chars": {"gt": 3}}, "l2")
        self.assertEqual(evaluate("abc", (rule,), "l1").route, "l1")
        self.assertEqual(evaluate("abcd", (rule,), "l1").route, "l2")

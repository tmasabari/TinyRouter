from .config import RuleConfig
from .models import RouteDecision


def evaluate(prompt, rules, default_route, source=None, reason_code=None):
    text = prompt.casefold()
    for rule in rules:
        if not rule.enabled or (rule.source and rule.source != source):
            continue
        if _matches(text, len(prompt), reason_code, rule):
            return RouteDecision(rule.route, "rules", rule.name, reason_code)
    return RouteDecision(default_route, "default", reason_code=reason_code)


def _matches(text, length, reason_code, rule):
    condition = rule.condition
    if "keywords" in condition:
        if not any(str(word).casefold() in text for word in condition["keywords"]["any"]):
            return False
    if "reason_codes" in condition:
        if reason_code not in condition["reason_codes"]["any"]:
            return False
    if "prompt_chars" in condition:
        if not all(_compare(length, op, value) for op, value in condition["prompt_chars"].items()):
            return False
    return True


def _compare(value, operator, expected):
    return {"gt": value > expected, "gte": value >= expected, "lt": value < expected,
            "lte": value <= expected, "eq": value == expected}.get(operator, False)

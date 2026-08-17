from .config import RuleConfig
from .models import RouteDecision


def evaluate(prompt: str, rules: tuple[RuleConfig, ...], default_route: str) -> RouteDecision:
    text = prompt.casefold()
    for rule in rules:
        if rule.enabled and _matches(text, len(prompt), rule):
            return RouteDecision(rule.route, "rules", rule.name)
    return RouteDecision(default_route, "default")


def _matches(text: str, length: int, rule: RuleConfig) -> bool:
    condition = rule.condition
    if "keywords" in condition:
        keywords = condition["keywords"].get("any", [])
        if not isinstance(keywords, list) or not any(str(word).casefold() in text for word in keywords):
            return False
    if "prompt_chars" in condition:
        comparisons = condition["prompt_chars"]
        if not isinstance(comparisons, dict) or not all(_compare(length, op, value) for op, value in comparisons.items()):
            return False
    return True


def _compare(value: int, operator: str, expected: object) -> bool:
    if not isinstance(expected, int):
        return False
    return {"gt": value > expected, "gte": value >= expected, "lt": value < expected,
            "lte": value <= expected, "eq": value == expected}.get(operator, False)

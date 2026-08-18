from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class ModelConfig:
    id: str
    name: str
    endpoint: str
    model: str
    capability_prompt: str
    timeout_seconds: float
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class RuleConfig:
    name: str
    enabled: bool
    condition: dict[str, Any]
    route: str
    source: str | None = None


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    console: bool = True
    file: str | None = None
    queue_size: int = 4096
    include_content: bool = False


@dataclass(frozen=True)
class RouterConfig:
    server: ServerConfig
    models: dict[str, ModelConfig]
    rules: tuple[RuleConfig, ...]
    default_route: str
    escalation_defaults: dict[str, str]
    logging: LoggingConfig


def _need(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ConfigError(f"missing {key}")
    return data[key]


def load_config(path: str | Path) -> RouterConfig:
    try:
        import yaml
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except ImportError as error:
        raise ConfigError("PyYAML is required; install the project dependencies") from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(str(error)) from error
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ConfigError("version must be 1")

    server = _need(raw, "server")
    if not isinstance(server, dict):
        raise ConfigError("server must be an object")
    host, port = _need(server, "host"), _need(server, "port")
    if not isinstance(host, str) or not host or isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError("invalid server configuration")

    raw_models = _need(raw, "models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ConfigError("models must be a non-empty array")
    models: dict[str, ModelConfig] = {}
    for item in raw_models:
        if not isinstance(item, dict):
            raise ConfigError("invalid model")
        try:
            model = ModelConfig(**{key: _need(item, key) for key in (
                "id", "name", "endpoint", "model", "capability_prompt", "timeout_seconds", "temperature", "max_tokens")})
        except (TypeError, ConfigError) as error:
            raise ConfigError(f"invalid model: {error}") from error
        if not isinstance(model.id, str) or not model.id.startswith("l") or not model.id[1:].isdigit() or model.id in models or not model.endpoint.startswith(("http://", "https://")):
            raise ConfigError(f"invalid model {model.id}")
        if not isinstance(model.capability_prompt, str) or not model.capability_prompt.strip():
            raise ConfigError(f"{model.id}.capability_prompt must be non-empty")
        if isinstance(model.timeout_seconds, bool) or not isinstance(model.timeout_seconds, (int, float)) or model.timeout_seconds <= 0:
            raise ConfigError(f"{model.id}.timeout_seconds must be > 0")
        if isinstance(model.max_tokens, bool) or not isinstance(model.max_tokens, int) or model.max_tokens <= 0:
            raise ConfigError(f"{model.id}.max_tokens must be > 0")
        if isinstance(model.temperature, bool) or not isinstance(model.temperature, (int, float)) or model.temperature < 0:
            raise ConfigError(f"{model.id}.temperature must be >= 0")
        models[model.id] = model
    if "l1" not in models:
        raise ConfigError("models must contain l1")

    routing = _need(raw, "routing")
    if not isinstance(routing, dict):
        raise ConfigError("routing must be an object")
    default_route = _need(routing, "default_route")
    if default_route not in models:
        raise ConfigError("invalid default_route")
    raw_rules = routing.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ConfigError("routing.rules must be an array")
    rules = []
    for item in raw_rules:
        if not isinstance(item, dict):
            raise ConfigError("invalid rule")
        rule = RuleConfig(_need(item, "name"), _need(item, "enabled"), _need(item, "condition"), _need(item, "route"), item.get("source"))
        if not isinstance(rule.name, str) or not rule.name or not isinstance(rule.enabled, bool) or rule.route not in models or not isinstance(rule.condition, dict) or not rule.condition:
            raise ConfigError(f"invalid rule {rule.name}")
        if rule.source is not None and rule.source not in models:
            raise ConfigError(f"invalid rule source {rule.source}")
        if set(rule.condition) - {"keywords", "prompt_chars", "reason_codes"}:
            raise ConfigError(f"unsupported condition in {rule.name}")
        if "keywords" in rule.condition:
            keywords = rule.condition["keywords"]
            if not isinstance(keywords, dict) or set(keywords) != {"any"} or not isinstance(keywords["any"], list) or not keywords["any"] or not all(isinstance(k, str) and k for k in keywords["any"]):
                raise ConfigError(f"invalid keywords condition in {rule.name}")
        if "reason_codes" in rule.condition:
            reasons = rule.condition["reason_codes"]
            if not isinstance(reasons, dict) or set(reasons) != {"any"} or not isinstance(reasons["any"], list) or not reasons["any"] or not all(isinstance(k, str) and k for k in reasons["any"]):
                raise ConfigError(f"invalid reason_codes condition in {rule.name}")
        if "prompt_chars" in rule.condition:
            comparisons = rule.condition["prompt_chars"]
            valid_ops = {"gt", "gte", "lt", "lte", "eq"}
            if not isinstance(comparisons, dict) or not comparisons or set(comparisons) - valid_ops:
                raise ConfigError(f"invalid prompt_chars condition in {rule.name}")
            if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in comparisons.values()):
                raise ConfigError(f"invalid prompt_chars values in {rule.name}")
        rules.append(rule)

    defaults = routing.get("escalation_defaults", {})
    if not isinstance(defaults, dict) or any(source not in models or target not in models or source == target for source, target in defaults.items()):
        raise ConfigError("invalid escalation_defaults")

    logging_raw = raw.get("logging", {})
    if not isinstance(logging_raw, dict):
        raise ConfigError("logging must be an object")
    level = str(logging_raw.get("level", "INFO")).upper()
    if level not in {"ERROR", "WARNING", "INFO", "DEBUG", "TRACE"}:
        raise ConfigError("logging.level must be ERROR, WARNING, INFO, DEBUG, or TRACE")
    queue_size = logging_raw.get("queue_size", 4096)
    if isinstance(queue_size, bool) or not isinstance(queue_size, int) or queue_size <= 0:
        raise ConfigError("logging.queue_size must be > 0")
    if not isinstance(logging_raw.get("console", True), bool) or not isinstance(logging_raw.get("include_content", False), bool):
        raise ConfigError("logging.console/include_content must be boolean")
    file = logging_raw.get("file")
    if file is not None and not isinstance(file, str):
        raise ConfigError("logging.file must be a string")

    return RouterConfig(ServerConfig(host, port), models, tuple(rules), default_route,
                        {str(k): str(v) for k, v in defaults.items()},
                        LoggingConfig(level, logging_raw.get("console", True), file, queue_size, logging_raw.get("include_content", False)))

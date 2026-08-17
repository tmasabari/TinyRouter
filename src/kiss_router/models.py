from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RouteDecision:
    route: str
    source: str
    rule: str | None = None
    confidence: float | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class RoutingEvent:
    request_id: str
    route: str
    source: str
    rule: str | None
    model: str
    latency_ms: int
    input_chars: int
    input_tokens: int | None
    output_tokens: int | None
    confidence: float | None
    success: bool
    escalation: bool


@dataclass(frozen=True)
class HandleResult:
    response: ChatResult
    decision: RouteDecision
    event: RoutingEvent

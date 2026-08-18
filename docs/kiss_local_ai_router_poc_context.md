# TinyRouter — KISS Local AI Router POC Context

**Status:** capability-routing POC  
**Date:** 2026-08-18

## 1. Objective

Build the smallest useful local AI router where:

- YAML rules decide which model runs next.
- Each model only reports whether it can handle the request.
- A model never selects another model or endpoint.
- The user can explicitly override routing with `@l1`, `@l2`, or `@l3`.
- Logging is configurable and asynchronous so model inference is never blocked by log I/O.

The design must follow **KISS, YAGNI, DRY, and POLA**.

## 2. Architecture

```text
                         USER
                          |
                   optional @lN
                          |
                          v
                    ORCHESTRATOR
                          |
                  +-------+-------+
                  |               |
              override        automatic
                  |               |
                  v               v
                 Lx          RULE ENGINE
                                  |
                                  v
                                 L1
                                  |
                         +--------+--------+
                         |                 |
                     can_handle         escalate
                         |                 |
                         v                 v
                      answer          RULE ENGINE
                                           |
                                           v
                                          L2
                                           |
                                  +--------+--------+
                                  |                 |
                              can_handle        escalate
                                  |                 |
                                  v                 v
                               answer             L3
```

The important boundary is:

> **Models report capability. Rules control routing.**

## 3. Model Capability Contract

Every automatic model invocation uses the same contract:

```json
{"status":"can_handle","reason_code":"simple_question","answer":"complete user-facing answer"}
```

or:

```json
{"status":"escalate","reason_code":"complex_reasoning","answer":""}
```

Rules:

- `status` is `can_handle` or `escalate`.
- `reason_code` is a short machine-readable reason.
- `can_handle` requires a non-empty answer.
- `escalate` never exposes an answer to the user.
- Model-generated confidence is intentionally not part of the contract.

### Why no confidence?

Testing showed that small local models can produce high confidence for wrong answers. A generated `0.92` is not a calibrated probability. Routing therefore uses deterministic rules and explicit capability status instead.

## 4. Routing Priority

```text
1. User override
2. Initial YAML rules
3. Default route
4. Model capability response
5. YAML escalation rules
6. Per-model escalation default
7. Maximum-hop/cycle protection
```

### User override

```text
@l1 question
@l2 question
@l3 question
```

The marker is removed before inference. An explicit override directly invokes that model and bypasses capability routing.

### Automatic routing

Example:

```text
Rules -> L1
          |
          +-- can_handle -> answer
          |
          +-- escalate(complex_reasoning)
                    |
                    v
                 Rule Engine
                    |
                    v
                   L2
```

## 5. Rule Engine

The rule engine is deliberately small.

Supported conditions:

- `keywords.any`
- `prompt_chars` using `gt`, `gte`, `lt`, `lte`, `eq`
- `reason_codes.any`

Rules are evaluated top-to-bottom. The first enabled matching rule wins.

A rule can optionally specify `source` so capability escalation rules only apply to the intended model.

Example:

```yaml
- name: l1_complex
  enabled: true
  source: l1
  condition:
    reason_codes:
      any: [complex_reasoning, insufficient_capability]
  route: l2
```

Do not add regex, scripting, database-backed rules, arbitrary expressions, priorities, or a complex DSL unless benchmark evidence requires them.

## 6. Escalation Defaults

YAML provides a simple fallback chain:

```yaml
routing:
  escalation_defaults:
    l1: l2
    l2: l3
```

This means a model can safely return `escalate` even when no specific reason-code rule exists.

The router rejects:

- missing escalation target;
- same-model escalation;
- routing cycles;
- more than `max_hops`.

Default:

```yaml
routing:
  max_hops: 3
```

## 7. Current Example Models

The sample configuration supports:

```text
L1 -> LFM2.5-1.2B
L2 -> LFM2.5-8B-A1B
L3 -> Qwen3.6-35B-A3B
```

Endpoints remain OpenAI-compatible `/v1/chat/completions` endpoints and are configured in YAML.

Model names are configuration metadata; the router contains no llama.cpp-specific code.

## 8. Model Worker

`ModelWorker` is the single model-capability abstraction.

It:

1. adds the model's capability prompt;
2. calls the shared `ChatClient`;
3. parses the capability JSON;
4. validates the response;
5. returns `CapabilityResult`.

There is no `L1Router`, `L2Router`, or `L3Router` implementation.

This keeps the architecture DRY and makes adding another layer a configuration change rather than another routing class.

## 9. Logging

Logging uses Python's standard `QueueHandler` + `QueueListener`.

```text
request thread
     |
     v
QueueHandler -> bounded queue -> QueueListener -> console/file
```

The request path only enqueues a log record. Console/file I/O runs on the listener thread.

Supported levels:

```text
ERROR
WARNING
INFO
DEBUG
TRACE
```

`TRACE` is a small custom level below `DEBUG`.

YAML:

```yaml
logging:
  level: INFO
  console: true
  file: logs/tinyrouter.log
  queue_size: 4096
```

Prompt/response content is not logged by default.

The logger is stopped during server shutdown so queued records are flushed.

## 10. Telemetry

Every request gets a `request_id`.

A `RoutingEvent` records:

- request ID;
- final route;
- source;
- matched rule;
- model;
- total latency;
- prompt character count;
- input/output token counts when available;
- success/failure;
- escalation;
- hop count;
- error text on failure.

The event remains in memory for the POC. No database or telemetry platform is required.

## 11. OpenAI-Compatible API

```text
POST /v1/chat/completions
```

The router does not trust a client-supplied physical endpoint. The `model` field is only API compatibility; routing is controlled by override markers and YAML.

The response remains compatible with normal OpenAI-style clients.

## 12. Failure Behavior

### Invalid user request

```text
HTTP 400
```

### Model/transport failure

```text
HTTP 502
```

### Invalid capability JSON

The current POC treats it as a model failure rather than trying to infer meaning from arbitrary natural language.

### Routing cycle

Fail immediately.

### Maximum hops exceeded

Fail immediately.

The POC intentionally does not add generic transport retries or circuit breakers yet.

## 13. Tests

Tests cover:

- configuration validation;
- rule ordering;
- case-insensitive keywords;
- prompt length boundaries;
- reason-code/source routing;
- model capability parsing;
- `can_handle` answer validation;
- escalation;
- L1 -> L2 -> L3;
- user overrides;
- unknown overrides;
- cycle protection;
- failed-request telemetry;
- async logger behavior.

The benchmark remains separate from unit tests.

## 14. Benchmark Goal

The benchmark must compare:

```text
Direct L2 baseline
        vs
Rules -> L1 -> optional escalation
```

Measure:

- L1 calls;
- L2 calls;
- L3 calls;
- L2 calls avoided;
- L1 routing latency;
- total latency;
- escalation rate;
- model failure rate;
- capability/routing errors.

The goal is not maximum L1 usage. The goal is:

> **reduce expensive-model calls without materially reducing answer quality.**

## 15. Explicitly Out of Scope

Do not add yet:

- RAG;
- MCP;
- embeddings/vector databases;
- Redis/database state;
- distributed tracing;
- service discovery;
- Kubernetes;
- complex rule DSL;
- LLM-as-judge;
- automatic model downloading;
- cloud provider integrations.

These violate the POC's KISS/YAGNI objective until measured evidence justifies them.

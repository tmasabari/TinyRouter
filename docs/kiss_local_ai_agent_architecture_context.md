# KISS Local AI Agent — Architecture & Design

**Project:** TinyRouter / KISS Local AI Agent  
**Owner:** Sabarinathan  
**Status:** Post-POC architecture baseline

> The router POC has validated the core separation of rules, workers, escalation, overrides, and telemetry. This document replaces the earlier model-specific architecture.

## 1. Architecture principles

1. **KISS** — minimal components and contracts.
2. **YAGNI** — no infrastructure without a demonstrated requirement.
3. **DRY** — one generic worker contract and one routing mechanism.
4. **POLA** — each component has one obvious responsibility.
5. **Model agnostic** — L1/L2/L3 are logical capability levels; models are replaceable implementations.
6. **Policy outside models** — models are untrusted input and never own security or physical routing.

## 2. Logical architecture

```text
                         USER / CLIENT
                              |
                    optional @l1/@l2/@l3
                              |
                              v
                     +------------------+
                     | API / NORMALIZER |
                     +--------+---------+
                              |
                              v
                     +------------------+
                     | KISS ORCHESTRATOR |
                     +--------+-----------+
                              |
                      +-------+-------+
                      |               |
                 explicit level   automatic
                      |               |
                      |               v
                      |        +-------------+
                      |        | RULE ENGINE  |
                      |        +------+------+ 
                      |               |
                      +-------+-------+
                              |
                              v
                       configured worker
                         /          \
                 can_handle       escalate
                    |                 |
                    v                 v
                 RESULT          RULE ENGINE
                                      |
                                  next level
```

The routing graph is configurable. It is not a hard-coded L1 -> L2 -> L3 pipeline.

## 3. Logical levels

```text
L1 = lowest-cost capable worker
L2 = medium-capability worker
L3 = highest-capability / coding-agent worker
```

Current deployments are only examples:

```yaml
levels:
  l1: { worker: ... }
  l2: { worker: ... }
  l3: { worker: ... }
```

A future model can replace any current model without changing the orchestrator.

## 4. Component responsibilities

### API / Normalizer

- accepts OpenAI-compatible chat requests;
- validates basic input;
- extracts optional `@lN` override;
- removes the marker before model invocation;
- creates request/correlation ID.

### Orchestrator

- owns request lifecycle;
- applies explicit override;
- invokes rules;
- invokes workers;
- handles capability results;
- asks rules for the next route;
- enforces hop/cycle limits;
- returns final result;
- records telemetry.

It must not contain model-specific behavior.

### Rule Engine

- evaluates deterministic configuration;
- selects the initial logical level;
- selects the next level after escalation;
- may inspect source level and reason code;
- may use keywords, length, context size, risk, availability, and task metadata.

It must remain a small policy engine, not a custom AI classifier.

### ModelWorker

A generic adapter around a configured model endpoint.

Responsibilities:

- build model request;
- invoke endpoint;
- parse capability response;
- validate schema;
- return normalized result.

It must not choose the next worker.

### AgentWorker

Optional adapter for a mature coding agent such as Pi.

Responsibilities:

- pass normalized task/context/policy;
- receive agent result;
- report completion or escalation.

The orchestrator must not reimplement the agent loop.

### Tool Registry

Owns tool definitions and implementations.

### Policy Engine

Makes deterministic allow/deny/confirm decisions before tool execution.

### Telemetry / Logger

Records request and hop events without blocking the main request path.

## 5. Worker contract

The core model contract is intentionally small:

```json
{
  "status": "can_handle | escalate",
  "reason_code": "simple_question",
  "answer": "actual answer or empty string"
}
```

Rules:

- `can_handle` means the worker's answer is the final answer for this hop.
- `escalate` means the worker cannot complete the task at its current capability.
- `reason_code` must use a controlled vocabulary where practical.
- `answer` must be empty for escalation.
- confidence is not required.
- a worker never specifies `l2`, `l3`, an endpoint, or another physical model.

## 6. Routing algorithm

```text
handle(request):
    if explicit override:
        invoke selected level
        return result

    route = rules.initial(request)
    visited = {}

    repeat until complete:
        reject if hop limit exceeded
        reject if route already visited

        result = worker[route].invoke(request)

        if result.can_handle:
            return result

        route = rules.next(request, route, result.reason_code)
```

This is deliberately small.

## 7. User override

Supported syntax:

```text
@l1 What is dependency injection?
@l2 Analyze this design.
@l3 Refactor the repository.
```

Priority:

```text
1. explicit user override
2. deterministic initial rules
3. configured default
4. worker capability result
5. escalation rules
```

An explicit override bypasses automatic routing but does not bypass tool policy.

## 8. Routing rules

Example:

```yaml
routing:
  default: l1
  max_hops: 3

  escalation_defaults:
    l1: l2
    l2: l3

  rules:
    - name: coding
      enabled: true
      condition:
        keywords:
          any: [implement, refactor, debug, repository]
      route: l3

    - name: l1_complex
      enabled: true
      source: l1
      condition:
        reason_codes:
          any: [complex_reasoning, insufficient_capability]
      route: l2
```

Exact fields may evolve, but the rule model should remain small.

## 9. Reliability controls

Required:

```text
per-worker timeout
bounded retry
invalid response handling
model unavailable handling
max_hops
cycle detection
no-route failure
```

A configuration that creates `L1 -> L2 -> L1` must be rejected or stopped at runtime.

Retries must not create unbounded inference or tool loops.

## 10. Context architecture

```text
full conversation
       |
       v
request normalizer
       |
       v
compact AgentState
       |
       v
worker-specific context
```

Pass only what the target worker needs:

- current request;
- compact summary;
- constraints;
- relevant files;
- relevant tool results;
- workspace information;
- policy constraints.

Do not automatically propagate:

- unrelated conversation history;
- verbose model reasoning;
- duplicated instructions;
- stale tool results.

## 11. Tool execution boundary

```text
LLM
 |
 v
structured request
 |
 v
schema validation
 |
 v
policy engine
 +---- deny
 +---- confirmation
 +---- allow
          |
          v
       executor
```

Minimum policy dimensions:

- allowed tool;
- allowed level;
- read/write permission;
- workspace/path restriction;
- shell restriction;
- network permission;
- timeout;
- output size;
- maximum calls/retries;
- destructive-operation confirmation/deny.

The LLM is never the security boundary.

## 12. L3 / Pi integration

```text
Orchestrator
    |
    +--> task
    +--> relevant context
    +--> workspace
    +--> policy constraints
             |
             v
            Pi
             |
       inspect/edit/test
             |
             v
          result
```

Pi owns the coding-agent loop. Do not duplicate it in TinyRouter.

## 13. Observability

Every request and hop should capture:

```json
{
  "request_id": "uuid",
  "hop": 1,
  "source_level": "l1",
  "selected_level": "l2",
  "model": "configured-model",
  "reason_code": "complex_reasoning",
  "latency_ms": 0,
  "tokens_in": 0,
  "tokens_out": 0,
  "escalated": true,
  "success": true
}
```

Do not make model names part of the schema's meaning; they are telemetry metadata.

### Logging

Use the standard-library asynchronous queue pattern:

```text
request thread
     |
 QueueHandler
     |
 bounded queue
     |
 QueueListener/background worker
     |
 console/file handlers
```

Levels:

- ERROR
- WARNING
- INFO
- DEBUG
- TRACE

Logging must not block model execution on normal console/file I/O. Shutdown must flush queued records and close file handles cleanly, including on Windows.

Prompt/response content should not be logged by default.

## 14. Evaluation architecture

Always compare routing against a direct strongest-worker baseline.

```text
                    test case
                       |
          +------------+------------+
          |            |            |
       direct       hierarchy    explicit @lN
      strongest
          |            |            |
          +------------+------------+
                       |
                    metrics
```

Required measurements:

- task success/correctness;
- routing correctness;
- false escalation;
- missed escalation;
- latency/TTFT;
- tokens;
- worker invocation count;
- context size;
- CPU/RAM;
- timeout/retry/failure recovery;
- tool correctness.

Include boundary cases where a small model is likely to answer confidently but incorrectly. The POC exposed this failure mode and it must remain in regression tests.

## 15. Evaluation categories

Minimum dataset:

1. simple QA;
2. simple transformation;
3. structured extraction;
4. simple tool task;
5. medium multi-tool task;
6. research;
7. coding;
8. architecture;
9. long-context;
10. multi-step reasoning;
11. ambiguous/borderline;
12. invalid model output;
13. tool misuse;
14. destructive request;
15. explicit `@l1/@l2/@l3` override;
16. model timeout/unavailable.

## 16. Technology boundaries

Keep the core implementation small:

- Python;
- validated YAML/configuration;
- HTTP/OpenAI-compatible model adapters;
- Pydantic or equivalent schema validation;
- pytest;
- standard-library asynchronous logging.

Avoid adding a heavyweight orchestration framework until the requirements demonstrate a need.

RAG, MCP, vector stores, distributed queues, Kubernetes, Redis, Kafka, and alternative inference kernels remain future extensions.

## 17. Architecture decisions

### ADR-001 — Logical capability levels

L1/L2/L3 are logical roles, not permanent model identities.

### ADR-002 — Capability contract

Workers return `can_handle` or `escalate`; they do not select the next physical model.

### ADR-003 — Rules own routing

Routing policy remains deterministic, configurable, and independently testable.

### ADR-004 — Explicit override

Users may directly select a configured logical level.

### ADR-005 — Direct escalation

Routing may skip intermediate levels when configured.

### ADR-006 — Confidence is not authoritative

Generated confidence is optional telemetry only.

### ADR-007 — Context minimization

Context is packaged per worker to control latency and memory bandwidth.

### ADR-008 — External tool policy

LLM output cannot directly execute privileged operations.

### ADR-009 — Generic adapters

Model providers, model versions, quantization, and inference backends are replaceable behind adapters.

## 18. Non-goals

Do not build:

- a general multi-agent framework;
- unlimited autonomous agents;
- unrestricted shell/filesystem access;
- distributed inference;
- RAG before it is needed;
- MCP before native tools are proven;
- Bonsai/ternary support inside routing code;
- cloud-specific infrastructure.

## 19. Definition of done

The architecture foundation is complete when:

- [ ] L1/L2/L3 are configurable logical levels.
- [ ] Any compatible model can replace a level.
- [ ] Worker capability contract is validated.
- [ ] Rules own escalation.
- [ ] Explicit overrides work.
- [ ] Direct L1 -> L3 is supported.
- [ ] Max-hop/cycle protection works.
- [ ] Context is minimized.
- [ ] Tool policy is external and default-deny.
- [ ] Async logging/telemetry works.
- [ ] Failure paths are deterministic and tested.
- [ ] Real-model benchmarks compare hierarchy against a direct strongest-worker baseline.

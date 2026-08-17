# KISS Local AI Router POC — User Story & Design Context

**Project:** TinyRouter — KISS Local AI Agent Routing  
**POC:** Rules Engine + L1 + L2  
**Owner:** Sabarinathan  
**Status:** Implemented POC baseline  
**Updated:** 2026-08-18

---

## 1. Objective

Build the smallest useful local AI router that validates this hypothesis:

> A cheap deterministic rules layer plus a fast Qwen 3.6 0.8B L1 can avoid unnecessary L2 inference while preserving useful response quality.

The POC intentionally excludes L3/Pi, tools, RAG, MCP, databases, queues, embeddings, and complex rule DSLs.

### Target flow

```text
                         USER REQUEST
                              |
                              v
                       +--------------+
                       | RULES ENGINE |
                       +------+-------+
                              |
                    +---------+---------+
                    |                   |
                 L2 match            no match
                    |                   |
                    v                   v
                   L2                  L1
                                      |
                              +-------+-------+
                              |               |
                           handles         escalates
                              |               |
                              v               v
                           RESPONSE          L2
```

The critical property is that **Rules → L2 bypasses L1**, while **Rules → L1 requires only one L1 model call**.

---

## 2. Fixed Model Decisions

### L1 — Qwen 3.6 0.8B

Role:

- semantic routing;
- simple request handling;
- deciding whether L2 is required;
- returning a constrained structured routing result plus an answer when it can handle the request.

Previously measured benchmark observations:

- prompt processing: approximately 562 tok/s;
- generation: approximately 54 tok/s.

These are observations, not contractual targets.

### L2 — LFM2.5-8B-A1B

Role:

- medium-complexity reasoning;
- requests explicitly classified as complex by deterministic rules;
- requests escalated by L1.

Both models are accessed through OpenAI-compatible `/v1/chat/completions` endpoints.

---

## 3. Architecture Decisions

### AD-001 — Deterministic rules come before L1

The router first evaluates cheap deterministic signals:

- configured keywords;
- configured prompt character length conditions.

If a rule routes to L2, **L1 is never called**.

### AD-002 — First matching rule wins

Rules are evaluated top-to-bottom. The first enabled rule that matches determines the route.

Do not add a priority field until the POC demonstrates a real need for one.

### AD-003 — YAML is the configuration boundary

Routing behavior and model endpoints are configuration, not code.

The router must never accept an endpoint selected by an LLM.

### AD-004 — L1 is both router and lightweight worker

The original implementation review exposed an important bug: treating L1 purely as a classifier and then calling L1 again for the answer caused two L1 calls.

The corrected contract is:

```text
Rules → L1 → simple answer
Rules → L1 → L2
```

Therefore a simple request costs exactly one L1 inference.

### AD-005 — Shared model client

L1 and L2 use the same `ChatClient` abstraction. Endpoint, model, timeout, temperature, and token limits are configuration.

No llama.cpp-specific logic belongs in the router.

### AD-006 — Standard library HTTP server

The POC exposes an OpenAI-compatible router endpoint using Python's standard `http.server` implementation.

No FastAPI, Flask, or other web framework is required for the experiment.

### AD-007 — Fail closed toward L2

L1 output is untrusted.

Invalid JSON, invalid route data, or insufficient confidence must not block a request. The POC performs one constrained retry and then escalates to L2.

### AD-008 — Failures are observable

Model failures must produce telemetry rather than silently disappearing. The final request result may still raise an upstream error, but the routing event records failure status and latency.

---

## 4. User Stories and Acceptance Criteria

### US-POC-001 — Configurable Rules Engine

As a system designer, I want routing rules defined in YAML so that routing behavior can change without code changes.

Acceptance:

- YAML is loaded at startup.
- Invalid configuration fails fast.
- Rules can be enabled/disabled.
- Keyword and prompt-character conditions are supported.
- Routes are limited to `l1` and `l2`.
- Rule order is deterministic.
- First matching rule wins.

### US-POC-002 — Keyword Routing

Case-insensitive keyword matching can route obvious complex requests directly to L2.

Example:

```yaml
- name: coding
  enabled: true
  condition:
    keywords:
      any:
        - implement
        - refactor
        - debug
  route: l2
```

### US-POC-003 — Prompt Length Routing

Prompt character count is configurable.

Example:

```yaml
condition:
  prompt_chars:
    gt: 5000
```

The threshold is a hypothesis and must be benchmarked rather than treated as a universal value.

### US-POC-004 — L1 Semantic Routing

L1 returns a constrained decision:

```json
{
  "route": "l1",
  "confidence": 0.96,
  "reason_code": "simple_question",
  "answer": "..."
}
```

or:

```json
{
  "route": "l2",
  "confidence": 0.91,
  "reason_code": "complex_reasoning"
}
```

L1 may select only `l1` or `l2`. It cannot select endpoints.

### US-POC-005 — L2 Invocation

L2 can be reached through either:

```text
Rules → L2
```

or:

```text
Rules → L1 → L2
```

### US-POC-006 — Common OpenAI-Compatible Interface

The router exposes:

```text
POST /v1/chat/completions
```

and internally calls configured model endpoints using the same API contract.

### US-POC-007 — Observable Routing

Routing events record:

- request ID;
- final route;
- routing source;
- matched rule;
- final model;
- L1 latency/tokens when L1 ran;
- total latency;
- input characters/tokens where available;
- output tokens where available;
- confidence;
- success/failure;
- escalation.

---

## 5. YAML Configuration

Current configuration shape:

```yaml
version: 1

server:
  host: 127.0.0.1
  port: 8090

models:
  - id: l1
    name: qwen3.6-0.8b
    endpoint: http://127.0.0.1:8081/v1
    model: qwen3.6-0.8b
    role: router
    timeout_seconds: 10
    temperature: 0.0
    max_tokens: 256

  - id: l2
    name: lfm2.5-8b-a1b
    endpoint: http://127.0.0.1:8082/v1
    model: lfm2.5-8b-a1b
    role: worker
    timeout_seconds: 60
    temperature: 0.2
    max_tokens: 2048

routing:
  rules:
    - name: long_prompt
      enabled: true
      condition:
        prompt_chars:
          gt: 5000
      route: l2

    - name: coding
      enabled: true
      condition:
        keywords:
          any:
            - implement
            - refactor
            - debug
            - repository
            - source code
      route: l2

    - name: architecture
      enabled: true
      condition:
        keywords:
          any:
            - architecture
            - system design
      route: l2

  default_route: l1

l1:
  routing_prompt: |
    Classify the user request.
    Decide whether L1 can answer it or L2 is required.
    Return ONLY valid JSON with route, confidence, reason_code,
    and answer when route is l1.

  low_confidence_threshold: 0.70
```

Supported prompt-length operators are intentionally limited to:

```text
gt
gte
lt
lte
eq
```

Unsupported operators and malformed rule structures fail configuration validation instead of silently behaving as non-matches.

---

## 6. Rule Engine Contract

The rules engine remains deliberately dumb.

```python
def evaluate(prompt, rules, default_route):
    for rule in rules:
        if rule.enabled and matches(rule.condition, prompt):
            return RouteDecision(rule.route, "rules", rule.name)
    return RouteDecision(default_route, "default")
```

Supported conditions:

1. `keywords.any` — case-insensitive substring matching.
2. `prompt_chars` — numeric comparison.

Do not implement:

- embedded Python;
- arbitrary expressions;
- scripting;
- database-backed rules;
- complex boolean DSL;
- rule priorities unless required by evidence.

Substring matching is intentionally a heuristic. For the POC, correctness should be evaluated empirically before introducing regex or NLP-based rule matching.

---

## 7. L1 Contract

L1 receives the request messages through the shared model client.

The system prompt asks Qwen 3.6 0.8B to return JSON only.

For an L1-handled request:

```json
{
  "route": "l1",
  "confidence": 0.95,
  "reason_code": "simple_question",
  "answer": "Dependency injection is..."
}
```

For escalation:

```json
{
  "route": "l2",
  "confidence": 0.88,
  "reason_code": "complex_reasoning"
}
```

Validation rules:

- route must be `l1` or `l2`;
- confidence must be numeric and between 0 and 1;
- reason code must be a string;
- an `l1` decision must contain a non-empty answer.

### Low confidence

If:

```text
route = l1
confidence < configured threshold
```

the orchestrator changes the decision to L2.

### Invalid output

```text
L1
 |
 | invalid JSON
 v
retry once
 |
 +---- valid ---> continue
 |
 +---- invalid -> L2
```

The router never attempts to infer intent from malformed natural-language output.

---

## 8. Corrected Orchestration Contract

The implementation must follow this behavior:

```python
async def handle(messages):
    prompt = extract_user_prompt(messages)
    decision = evaluate(prompt, rules, "l1")

    if decision.route == "l2":
        return await l2.chat(messages)

    l1_result = await l1.route(messages)

    if l1_result.route == "l1":
        return l1_result.answer

    return await l2.chat(messages)
```

The important performance property is:

```text
simple request:
Rules → one L1 call → response

complex rule:
Rules → one L2 call → response

L1 escalation:
Rules → one L1 call → one L2 call → response
```

There must never be an unnecessary second L1 inference for a simple request.

---

## 9. OpenAI-Compatible Router API

The POC exposes:

```text
POST /v1/chat/completions
```

Example request:

```json
{
  "model": "router",
  "messages": [
    {"role": "user", "content": "What is dependency injection?"}
  ]
}
```

The router ignores client-selected physical endpoints. Model routing is controlled by YAML.

Example response shape:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "model": "qwen3.6-0.8b",
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

Token counts remain zero when the underlying inference server does not provide usage data.

---

## 10. Telemetry Model

A `RoutingEvent` captures routing evidence for the POC.

Important distinction:

```text
L1 latency/tokens = routing overhead
Total latency     = user-visible request cost
L2 latency/tokens = worker cost when escalation occurs
```

This allows the experiment to answer whether L1 routing actually saves cost/latency.

Failures should still create an event with `success=false` before the exception is returned to the API layer.

The current POC keeps events in memory. Do not add a database or distributed telemetry stack yet.

---

## 11. Configuration Validation

Startup validation must reject:

- missing `version` or unsupported version;
- missing models;
- duplicate model IDs;
- anything other than exactly `l1` and `l2` models;
- invalid endpoint schemes;
- invalid model numeric settings;
- invalid default routes;
- invalid rule routes;
- unsupported condition keys;
- malformed keyword conditions;
- malformed prompt-length comparisons;
- unsupported prompt-length operators;
- invalid L1 confidence threshold;
- missing/empty L1 routing prompt.

The objective is fail-fast behavior rather than silently accepting a broken router configuration.

---

## 12. HTTP Failure Handling

The standard-library client must surface upstream failures as router failures.

The API layer maps an upstream model failure to HTTP 502.

Client validation failures map to HTTP 400.

The POC does not add sophisticated retry policies for model availability. L1 has only its constrained JSON-output retry; transport retries are intentionally out of scope.

---

## 13. Tests

The test suite should verify at minimum:

### Rules

- disabled rule is skipped;
- first enabled matching rule wins;
- keyword matching is case-insensitive;
- prompt length boundaries are correct;
- all supported comparison operators work;
- invalid operators/configuration fail fast.

### Orchestration

- rule → L2 bypasses L1;
- simple request → exactly one L1 call;
- L1 → L2 performs exactly one L1 and one L2 call;
- low-confidence L1 escalates;
- malformed L1 output retries once;
- repeated malformed L1 output falls back to L2;
- model failure records failed telemetry.

### API

- invalid JSON/request returns 400;
- valid chat completion returns OpenAI-compatible shape;
- upstream failure returns 502.

---

## 14. Repository Structure

```text
TinyRouter/
├── config/
│   └── router.yaml
├── docs/
│   ├── kiss_local_ai_router_poc_context.md
│   └── ...
├── src/
│   └── kiss_router/
│       ├── client.py
│       ├── config.py
│       ├── l1.py
│       ├── models.py
│       ├── orchestrator.py
│       ├── rules.py
│       └── server.py
├── tests/
│   ├── test_config.py
│   ├── test_orchestrator.py
│   └── test_rules.py
├── pyproject.toml
└── README.md
```

The implementation intentionally remains small. A new abstraction or dependency requires a demonstrated POC need.

---

## 15. Running the POC

Install in an isolated Python environment:

```bash
python -m venv .venv
# activate the environment
pip install -e .
```

Run tests:

```bash
python -m pytest
```

Start the router:

```bash
tiny-router --config config/router.yaml
```

or:

```bash
python -m kiss_router.server --config config/router.yaml
```

Default router endpoint:

```text
http://127.0.0.1:8090/v1/chat/completions
```

The configured L1 and L2 inference servers must already expose their own OpenAI-compatible `/v1/chat/completions` endpoints.

---

## 16. Example Routing Paths

### Simple request

```text
"What is dependency injection?"

Rules
  ↓ no match
L1 / Qwen 0.8B
  ↓ route=l1
response
```

### Obvious coding request

```text
"Refactor this repository's authentication implementation"

Rules
  ↓ coding match
L2 / LFM2.5-8B-A1B
```

### Long request

```text
prompt > configured threshold

Rules
  ↓ long_prompt
L2
```

### Ambiguous/complex request

```text
Rules
  ↓ no match
L1
  ↓ route=l2
L2
```

### Invalid L1 output

```text
Rules
  ↓
L1
  ↓ invalid JSON
L1 retry
  ↓ invalid again
L2
```

---

## 17. Review Findings and Resolutions

The first Codex-generated implementation was reviewed against this design. The following issues were found and corrected.

### Finding 1 — Double L1 invocation

**Problem:** L1 classified a request and then the orchestrator invoked L1 again to produce the answer.

**Impact:** Simple requests paid for two L1 calls, invalidating the intended cost/latency experiment.

**Resolution:** L1 now returns an answer when it selects `l1`; the orchestrator returns it directly.

### Finding 2 — Incomplete telemetry

**Problem:** A single latency/token pair represented only the final model call.

**Impact:** L1 routing overhead could not be measured separately.

**Resolution:** Routing events distinguish L1 routing metrics from total request latency and record escalation.

### Finding 3 — Hard-coded success

**Problem:** Successful telemetry was constructed with `success=True` and failures were not recorded.

**Resolution:** Model-call failures are recorded with `success=False` before being surfaced.

### Finding 4 — Weak configuration validation

**Problem:** Unsupported prompt-length operators could silently become non-matches.

**Resolution:** Supported operators and condition structure are validated at startup.

### Finding 5 — Missing router API

**Problem:** The library implemented orchestration but did not expose the specified ChatGPT-style router endpoint.

**Resolution:** Added a minimal standard-library HTTP server exposing `/v1/chat/completions`.

### Finding 6 — Insufficient tests

**Problem:** Existing tests covered only the main routing paths.

**Resolution:** Added configuration and orchestration tests for the corrected contracts, including direct L1 handling, escalation, invalid output, and validation behavior.

---

## 18. POC Non-Goals

Do not add these until benchmark evidence justifies them:

- L3/Pi routing;
- RAG;
- MCP;
- tool execution;
- embeddings/vector search;
- semantic rule matching;
- dynamic rule editing API;
- database-backed telemetry;
- distributed tracing;
- model load balancing;
- circuit breakers;
- complex retry policies;
- rule priority/weighting;
- agent loops.

KISS/YAGNI is an explicit design constraint, not a temporary lack of features.

---

## 19. Next Experiment

The next useful work is measurement, not architecture.

Benchmark the same request set through:

```text
Baseline:
Request → L2

Router:
Request → Rules → L1/L2
```

Measure:

- percentage routed directly to L2 by rules;
- percentage handled by L1;
- percentage escalated from L1 to L2;
- L1 routing latency;
- total latency;
- L2 calls avoided;
- token consumption where available;
- answer quality/error rate.

The POC succeeds only if the additional routing cost is outweighed by avoided L2 work without unacceptable quality loss.

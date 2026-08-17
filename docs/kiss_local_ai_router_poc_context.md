# KISS Local AI Router POC — User Story & Design Context

**Project:** KISS Local AI Agent Routing  
**POC:** Rules Engine + L1 + L2  
**Owner:** Sabarinathan  
**Date:** 2026-08-17  
**Status:** POC design baseline

---

# 1. POC Objective

Build the smallest useful version of the local AI router with three stages:

```text
User Request
     |
     v
Rules Engine
     |
     +---- explicit rule match ----> L2
     |
     +---- no rule match ----------> L1
                                      |
                                      +---- L1 handles
                                      |
                                      +---- L1 escalates --> L2
```

The purpose of the POC is to validate whether a deterministic rules layer combined with the Qwen 3.6 0.8B router can reduce unnecessary L2 inference while maintaining acceptable routing quality.

The POC intentionally excludes L3/Pi.

---

# 2. Fixed Model Decisions

## L1

**Model:** Qwen 3.6 0.8B

Role:

- semantic request classification;
- simple requests;
- deciding whether L2 is required;
- structured routing response.

Existing benchmark evidence indicates approximately:

- prompt processing: ~562 tok/s;
- generation: ~54 tok/s.

These are benchmark observations, not contractual performance targets.

## L2

**Model:** LFM2.5-8B-A1B

Role:

- medium-complexity reasoning;
- moderate tool-oriented tasks;
- requests that deterministic rules classify as complex;
- requests escalated by L1.

The model is accessed through the same OpenAI-compatible chat completion interface as L1.

---

# 3. Problem Statement

Sending every user request directly to L2 is wasteful.

Many requests can be identified as complex using deterministic information such as:

- specific keywords;
- prompt length;
- explicitly configured patterns.

Requests that do not match those obvious conditions can be passed to the small L1 model.

The POC therefore introduces a cheap deterministic first stage:

```text
                    REQUEST
                       |
                       v
                +-------------+
                | RULES       |
                | ENGINE      |
                +------+------+
                       |
             +---------+---------+
             |                   |
        rule matched         no match
             |                   |
             v                   v
            L2                  L1
                                |
                         +------+------+
                         |             |
                       L1 OK        L2 needed
                         |             |
                         v             v
                      RESULT          L2
```

---

# 4. User Story

## Epic

**As a local AI developer, I want a configurable deterministic rules engine in front of the L1 model, so that obviously complex requests can go directly to L2 while simpler or ambiguous requests are evaluated by the fast Qwen 3.6 0.8B router.**

---

# 5. User Stories

## US-POC-001 — Configurable Rules Engine

**As a system designer, I want routing rules defined in YAML so that routing behavior can be changed without modifying application code.**

### Acceptance criteria

- Rules are loaded from YAML.
- Rules can be enabled/disabled.
- Rules support keyword matching.
- Rules support prompt-character length conditions.
- Rules specify a logical destination such as `l1` or `l2`.
- Rule order is deterministic.
- The first matching rule wins unless the configuration explicitly defines another behavior.
- No model call occurs when a rule routes directly to L2.
- Invalid configuration fails fast at startup.

---

## US-POC-002 — Keyword Routing

**As a system designer, I want configured keywords to identify obviously complex requests so they can bypass L1.**

Example:

```yaml
- name: coding
  condition:
    keywords:
      any:
        - implement
        - refactor
        - debug
        - repository
  route: l2
```

Example request:

```text
"Refactor the authentication subsystem"
```

Expected:

```text
Rules Engine -> L2
```

The keyword list is a heuristic, not an intelligence system.

---

## US-POC-003 — Prompt Length Routing

**As a system designer, I want prompt length to be configurable so that very large requests can bypass L1 when appropriate.**

Example:

```yaml
- name: long_prompt
  condition:
    prompt_chars:
      gt: 5000
  route: l2
```

Expected:

```text
prompt <= 5000  -> continue to L1
prompt > 5000   -> L2
```

The threshold must be configurable because 5000 characters is only an initial hypothesis.

---

## US-POC-004 — L1 Semantic Routing

**As a user, I want requests that are not obvious from deterministic rules to be evaluated by Qwen 3.6 0.8B.**

Expected L1 response:

```json
{
  "route": "l1",
  "confidence": 0.96,
  "reason_code": "simple_question"
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

L1 may choose only:

```text
l1
l2
```

L1 must not select arbitrary endpoints.

---

## US-POC-005 — L2 Invocation

**As a user, I want L2 to receive requests that are classified as requiring greater capability.**

L2 may be reached through:

```text
Rules Engine -> L2
```

or:

```text
Rules Engine -> L1 -> L2
```

L2 must not require L1 to have executed first.

---

## US-POC-006 — Common Model Endpoint

**As a system designer, I want both models to use a common OpenAI-compatible endpoint configuration so that the router is independent of the underlying inference server.**

Expected API:

```text
POST /v1/chat/completions
```

The application should not contain llama.cpp-specific routing logic.

---

## US-POC-007 — Observable Routing

**As a system designer, I want every routing decision recorded so that the POC can be evaluated objectively.**

Each request should record:

- request ID;
- route;
- routing source;
- matched rule;
- model;
- latency;
- input tokens/characters where available;
- output tokens where available;
- L1 confidence;
- success/failure;
- escalation.

---

# 6. Functional Architecture

```text
                         +----------------+
                         |     CLIENT     |
                         | ChatGPT-style  |
                         +-------+--------+
                                 |
                                 v
                         +---------------+
                         | ORCHESTRATOR  |
                         +-------+-------+
                                 |
                                 v
                         +---------------+
                         | RULES ENGINE  |
                         | YAML          |
                         +-------+-------+
                                 |
                    +------------+------------+
                    |                         |
               matched L2                no match
                    |                         |
                    v                         v
              +-----------+             +-----------+
              | L2        |             | L1        |
              | LFM2.5    |             | Qwen 0.8B |
              | 8B-A1B    |             +-----+-----+
              +-----+-----+                   |
                    |                    +----+----+
                    |                    |         |
                    |                   L1        L2
                    |                    |         |
                    |                    |         v
                    +--------------------+------> L2
                                             |
                                             v
                                          RESPONSE
```

---

# 7. Responsibility Boundaries

## Client

Sends a normal chat-completion style request.

## Orchestrator

Responsible for:

- request validation;
- state;
- invoking rules;
- invoking L1;
- invoking L2;
- returning the final response;
- telemetry.

## Rules Engine

Responsible only for deterministic classification.

It does not:

- call LLMs;
- execute tools;
- contain business logic for models;
- make security decisions.

## L1

Responsible for semantic routing and simple requests.

It does not:

- select endpoints;
- execute privileged tools;
- bypass the orchestrator.

## L2

Responsible for medium-complexity responses/workflows.

---

# 8. YAML Configuration

Recommended initial configuration:

```yaml
version: 1

server:
  host: "127.0.0.1"
  port: 8090

models:

  - id: "l1"
    name: "qwen3.6-0.8b"
    endpoint: "http://127.0.0.1:8081/v1"
    model: "qwen3.6-0.8b"
    role: "router"
    timeout_seconds: 10
    temperature: 0.0
    max_tokens: 256

  - id: "l2"
    name: "lfm2.5-8b-a1b"
    endpoint: "http://127.0.0.1:8082/v1"
    model: "lfm2.5-8b-a1b"
    role: "worker"
    timeout_seconds: 60
    temperature: 0.2
    max_tokens: 2048

routing:

  rules:

    - name: "long_prompt"
      enabled: true
      condition:
        prompt_chars:
          gt: 5000
      route: "l2"

    - name: "coding"
      enabled: true
      condition:
        keywords:
          any:
            - "implement"
            - "refactor"
            - "debug"
            - "repository"
            - "source code"
      route: "l2"

    - name: "architecture"
      enabled: true
      condition:
        keywords:
          any:
            - "architecture"
            - "system design"
      route: "l2"

  default_route: "l1"

l1:

  routing_prompt: |
    Classify the user request.

    Decide whether the request can be handled by L1
    or requires L2.

    Return ONLY valid JSON:

    {
      "route": "l1 | l2",
      "confidence": 0.0,
      "reason_code": "string"
    }

  low_confidence_threshold: 0.70
```

---

# 9. Rule Evaluation

The initial engine should remain deliberately simple.

Conceptual algorithm:

```python
def evaluate(request, rules):
    for rule in rules:
        if not rule.enabled:
            continue

        if matches(rule.condition, request):
            return RouteDecision(
                route=rule.route,
                source="rules",
                rule=rule.name
            )

    return RouteDecision(
        route="l1",
        source="default",
        rule=None
    )
```

The rules engine must not become a programming language.

Do not implement:

- arbitrary expressions;
- embedded Python;
- scripting;
- complex boolean DSL;
- database-backed rules.

YAGNI.

---

# 10. Rule Types for POC

Only implement:

## Keyword

```yaml
condition:
  keywords:
    any:
      - "refactor"
      - "debug"
```

Case-insensitive substring matching is sufficient initially.

## Prompt character count

```yaml
condition:
  prompt_chars:
    gt: 5000
```

Potential operators:

```text
gt
gte
lt
lte
eq
```

Only implement those if required by tests.

---

# 11. Rule Priority

Rules are evaluated top-to-bottom.

Example:

```yaml
rules:

  - name: "explicit_coding"
    ...

  - name: "long_prompt"
    ...

  - name: "research"
    ...
```

The first matching rule wins.

This makes routing behavior predictable.

If priority becomes necessary later, add an explicit `priority` field. Do not add it to the first implementation unless needed.

---

# 12. L1 Contract

L1 receives a minimal prompt.

It should not receive the complete historical conversation unless the POC explicitly needs it.

Input conceptually:

```json
{
  "request": "Explain dependency injection in .NET"
}
```

L1 returns:

```json
{
  "route": "l1",
  "confidence": 0.97,
  "reason_code": "simple_explanation"
}
```

For escalation:

```json
{
  "route": "l2",
  "confidence": 0.89,
  "reason_code": "complex_reasoning"
}
```

The response must be parsed and validated before use.

---

# 13. L1 Failure Handling

L1 is not trusted to produce valid JSON.

If L1 returns:

```text
I think this should go to L2.
```

the orchestrator must not guess.

Recommended POC behavior:

```text
invalid JSON
    |
    v
one constrained retry
    |
    +---- valid --> continue
    |
    +---- invalid --> L2
```

This prevents malformed small-model output from blocking the request.

---

# 14. Model Client

Both models use the same client abstraction.

Conceptual interface:

```python
class ChatClient:
    async def chat(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float,
        max_tokens: int
    ) -> ChatResponse:
        ...
```

Configuration determines:

```text
l1 -> endpoint + model
l2 -> endpoint + model
```

The orchestrator should not contain separate L1 HTTP and L2 HTTP implementations.

---

# 15. OpenAI-Compatible Endpoint

Expected interface:

```text
POST {endpoint}/chat/completions
```

For example:

```text
L1
http://127.0.0.1:8081/v1/chat/completions

L2
http://127.0.0.1:8082/v1/chat/completions
```

The endpoint is configuration.

The logical route remains:

```text
l1
l2
```

Never allow an LLM to provide an endpoint.

---

# 16. Orchestration Algorithm

POC behavior:

```python
async def handle(request):

    decision = rules.evaluate(request)

    if decision.route == "l2":
        return await l2.chat(request)

    result = await l1.route(request)

    if result.route == "l1":
        return result.response

    return await l2.chat(request)
```

The important property is that the Rules Engine can bypass L1.

---

# 17. Routing Paths

## Path 1 — Rule → L2

```text
Request
  |
  v
Rules
  |
  | "refactor"
  v
L2
  |
  v
Response
```

## Path 2 — Rules → L1

```text
Request
  |
  v
Rules
  |
  | no match
  v
L1
  |
  v
Response
```

## Path 3 — Rules → L1 → L2

```text
Request
  |
  v
Rules
  |
  | no match
  v
L1
  |
  | requires L2
  v
L2
  |
  v
Response
```

---

# 18. Example Requests

## Simple request

```text
"What is dependency injection?"
```

Expected:

```text
Rules -> L1 -> response
```

## Long request

```text
> 5000 characters
```

Expected:

```text
Rules -> L2
```

## Explicit coding request

```text
"Refactor this repository's authentication implementation."
```

Expected:

```text
Rules -> L2
```

## Ambiguous request

```text
"Compare these two approaches and tell me which is better."
```

Expected initial behavior:

```text
Rules -> L1
```

L1 decides whether L2 is required.

---

# 19. Important POC Design Principle

The Rules Engine is a **fast deterministic filter**, not an attempt to replace L1.

Correct division:

```text
Rules:
"Is this obviously complex?"

L1:
"Given that it is not obviously complex,
can I handle it?"

L2:
"Perform the more capable work."
```

This is the main hypothesis being tested by the POC.

---

# 20. Telemetry

Each request should produce a routing event:

```json
{
  "request_id": "uuid",
  "route": "l2",
  "source": "rules",
  "rule": "long_prompt",
  "model": "lfm2.5-8b-a1b",
  "latency_ms": 1250,
  "confidence": null,
  "success": true
}
```

For L1:

```json
{
  "request_id": "uuid",
  "route": "l2",
  "source": "l1",
  "rule": null,
  "model": "lfm2.5-8b-a1b",
  "latency_ms": 1800,
  "confidence": 0.91,
  "success": true
}
```

Important metrics:

- rules → L1 percentage;
- rules → L2 percentage;
- L1 → L1 percentage;
- L1 → L2 percentage;
- total L2 percentage;
- L1 latency;
- L2 latency;
- end-to-end latency;
- invalid L1 JSON rate;
- L1 retry rate;
- request success rate.

---

# 21. POC Success Criteria

The POC is successful if:

1. YAML changes routing behavior without code changes.
2. Rules can bypass L1.
3. Requests not matching rules reach L1.
4. L1 can route to L1 or L2.
5. Both model endpoints use the same client abstraction.
6. LLMs cannot choose arbitrary endpoints.
7. Invalid L1 JSON is handled safely.
8. Every route is observable.
9. Direct L2 and routed execution can be benchmarked.
10. The system remains small enough to understand in one sitting.

---

# 22. POC Benchmark

Create a fixed set of requests.

Categories:

```text
simple_qa
simple_explanation
simple_transformation
coding_keyword
architecture_keyword
long_prompt
ambiguous
complex_reasoning
```

For each request record:

```yaml
id:
prompt:
expected_rule_route:
expected_l1_route:
expected_final_route:
```

Compare:

```text
Direct L2
Rules -> L1
Rules -> L2
Rules -> L1 -> L2
```

Primary measurements:

```text
                latency
                   +
                   |
             routing accuracy
                   +
                   |
              L2 avoidance
```

The most important question is:

> Does the deterministic Rules Engine reduce unnecessary L1/L2 inference without increasing incorrect routing?

---

# 23. Implementation Plan

## Step 1 — Project skeleton

```text
kiss-router/
├── pyproject.toml
├── config/
│   └── router.yaml
├── src/
│   └── kiss_router/
│       ├── config.py
│       ├── models.py
│       ├── rules.py
│       ├── client.py
│       ├── l1.py
│       ├── l2.py
│       └── orchestrator.py
└── tests/
    ├── test_rules.py
    ├── test_l1.py
    └── test_orchestrator.py
```

Keep this small.

---

## Step 2 — Configuration

Implement:

- YAML loading;
- Pydantic validation;
- model endpoint configuration;
- routing rule configuration.

Fail fast on invalid configuration.

---

## Step 3 — Rules Engine

Implement only:

- enabled flag;
- keyword `any`;
- prompt character comparison;
- first-match behavior;
- default route.

Test without models.

---

## Step 4 — Common Chat Client

Implement one OpenAI-compatible client.

Both L1 and L2 use it.

---

## Step 5 — L1

Implement:

- routing prompt;
- JSON schema;
- validation;
- one retry;
- fallback to L2.

---

## Step 6 — L2

Implement simple chat completion invocation.

No tools or agent loop yet.

The POC's purpose is routing, not tool orchestration.

---

## Step 7 — Orchestrator

Implement:

```text
Rules
  ↓
L1
  ↓
L2
```

with direct Rules → L2 bypass.

---

## Step 8 — Benchmark

Run the fixed evaluation set.

Collect:

- route;
- reason;
- latency;
- model calls;
- success.

---

# 24. Explicit Non-Goals

Do not implement in this POC:

- L3;
- Pi;
- MCP;
- RAG;
- tool registry;
- filesystem access;
- shell execution;
- multi-agent loops;
- vector databases;
- Redis;
- Kafka;
- LangChain;
- LangGraph;
- distributed inference;
- complex rule DSL.

These belong to later iterations only if justified.

---

# 25. Future Extension

After this POC is validated:

```text
              RULES
                |
                v
               L1
          +-----+-----+
          |           |
         L1           L2
                      |
                   complex
                      |
                      v
                  L3 / Pi
                  + Qwen 35B
```

The POC should therefore preserve the logical route IDs:

```text
l1
l2
l3
```

even though only L1 and L2 are implemented initially.

---

# 26. Final Architecture Decision

For the POC, adopt:

> **YAML Rules Engine → L1 Qwen 3.6 0.8B → L2 LFM2.5-8B-A1B**

with two important paths:

```text
Rules match
    ↓
   L2
```

and:

```text
Rules don't match
    ↓
   L1
    ↓
 +--+--+
 |     |
L1    L2
```

Both models use configurable OpenAI-compatible endpoints.

The Rules Engine is deterministic.

L1 is semantic.

L2 is the capable worker.

The orchestrator owns the flow.

---

# 27. Design Principles

### KISS

Keep the router small and explicit.

### YAGNI

Do not implement L3, tools, RAG or MCP yet.

### DRY

One model client for all OpenAI-compatible endpoints.

### POLA

Models cannot select arbitrary endpoints or bypass orchestration.

### Configuration over code

Routing behavior belongs in YAML.

### Measure before optimizing

Use real benchmark data to tune keyword lists and prompt-length thresholds.

---

# 28. Continuation Instructions

When continuing this POC in a new chat:

1. Use this document as the POC design baseline.
2. Implement Rules → L1 → L2 first.
3. Keep YAML as the source of routing configuration.
4. Use logical model IDs (`l1`, `l2`) rather than hard-coded endpoints.
5. Use a single OpenAI-compatible chat client.
6. Rules may bypass L1 and route directly to L2.
7. Unmatched requests go to L1.
8. L1 may return only `l1` or `l2`.
9. Invalid L1 JSON must not be guessed.
10. Keep the POC free of L3, Pi, tools, RAG and MCP.
11. Benchmark routing before expanding the architecture.
12. Do not replace Qwen 3.6 0.8B or LFM2.5-8B-A1B without new benchmark evidence.

---

# 29. One-Line Architecture

```text
YAML Rules → Qwen 3.6 0.8B Router → LFM2.5-8B-A1B Worker
```

with the optimization:

```text
obviously complex → skip L1 → L2
```

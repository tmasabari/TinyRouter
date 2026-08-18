# TinyRouter

A deliberately small local AI router for testing **Rules → L1 → L2/L3** routing.

The POC answers one question: can cheap deterministic routing plus a small local L1 avoid unnecessary calls to larger models without unacceptable quality loss?

## Architecture

```text
                         USER REQUEST
                              |
                     +--------+--------+
                     |                 |
                @l2 / @l3         no override
                     |                 |
                     v                 v
                  TARGET          RULES ENGINE
                                      |
                              +-------+-------+
                              |               |
                             L2              L1
                                             |
                                      +------+------+
                                      |             |
                                    answer         L2
```

User model markers have highest priority. Without a marker, YAML rules run first. L1 may answer the request or escalate to L2.

## Model Layers

| Layer | Purpose |
|---|---|
| L1 | Fast local model; routing + simple answers |
| L2 | Larger local model for medium/complex requests |
| L3 | Largest/strongest local model; direct user override in this POC |

All model servers use an OpenAI-compatible `/v1/chat/completions` API.

## User Model Override

A user can bypass rules and L1 by putting a marker at the **start of the first user message**:

```text
@l2 Explain this architecture.
```

or:

```text
@l3 Design the production system in detail.
```

TinyRouter removes the marker before sending the prompt to the selected model.

Supported markers:

```text
@l2 → configured L2 model
@l3 → configured L3 model
```

The marker is a routing control, not model-generated content. It is deterministic and has priority over YAML rules and L1.

If the selected layer is not configured, the request fails with a client error.

A normal request still follows:

```text
Rules → L2
Rules → L1 → answer
Rules → L1 → L2
```

A simple request requires **one L1 inference**, not two.

## Configuration

Routing is YAML-based. `config/router.yaml` defines the router, model endpoints, rules, and L1 prompt.

Example model configuration:

```yaml
models:
  - id: l1
    name: lfm2.5-1.2b
    endpoint: http://127.0.0.1:8081/v1
    model: lfm2.5-1.2b
    timeout_seconds: 30
    temperature: 0.0
    max_tokens: 256

  - id: l2
    name: lfm2.5-8b-a1b
    endpoint: http://127.0.0.1:8082/v1
    model: lfm2.5-8b-a1b
    timeout_seconds: 60
    temperature: 0.2
    max_tokens: 2048

  - id: l3
    name: qwen3.6-35b-a3b
    endpoint: http://127.0.0.1:8083/v1
    model: qwen3.6-35b-a3b
    timeout_seconds: 120
    temperature: 0.2
    max_tokens: 4096
```

Rules are evaluated top-to-bottom; the first enabled match wins.

```yaml
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
          any: [implement, refactor, debug, repository, source code]
      route: l2

  default_route: l1
```

Supported prompt-length operators:

```text
gt
gte
lt
lte
eq
```

Invalid configuration fails at startup.

## L1 Contract

L1 is both router and lightweight worker.

For an L1 answer:

```json
{"route":"l1","confidence":0.95,"reason_code":"simple_question","answer":"actual answer"}
```

For escalation:

```json
{"route":"l2","confidence":0.95,"reason_code":"complex_reasoning","answer":""}
```

L1 output is untrusted. Invalid JSON is retried once; a second invalid response falls back to L2. Low-confidence L1 decisions also escalate.

The model's self-reported confidence is a heuristic, not a calibrated probability. Benchmark quality must be measured separately.

## Router API

```text
POST http://127.0.0.1:8090/v1/chat/completions
```

Example normal request:

```json
{"model":"router","messages":[{"role":"user","content":"What is dependency injection?"}]}
```

Example direct L3 request:

```json
{"model":"router","messages":[{"role":"user","content":"@l3 Design a production-grade payment platform."}]}
```

The physical endpoints are controlled only by YAML. The client cannot provide an arbitrary endpoint.

## Installation

Requires Python 3.11+.

```bash
python -m venv .venv
pip install -e .
```

The only runtime dependency is PyYAML. HTTP uses the Python standard library.

## Run

Start TinyRouter:

```bash
tiny-router --config config/router.yaml
```

Default endpoint:

```text
http://127.0.0.1:8090/v1/chat/completions
```

The configured inference servers must already be running.

## Test

```bash
python -m pytest -v
```

Tests cover rules, configuration validation, L1/L2 orchestration, failure handling, and `@l2`/`@l3` overrides.

## Benchmark

The repository contains a 50-request set:

```text
10 simple
10 medium
10 complex
10 obvious coding
10 long-context
```

Run:

```bash
python benchmarks/run_benchmark.py
```

Results:

```text
benchmark-results/results.csv
benchmark-results/summary.json
```

The important measurements are:

```text
L1 handled
L1 escalations
Rules → L2
L2 calls avoided
L1 latency
Total latency
Token usage
L1 answer quality/error rate
```

Do not use Open WebUI for the first benchmark. Test TinyRouter directly so additional context and network overhead do not contaminate the experiment.

## Design Constraints

- **KISS** — keep the router small.
- **YAGNI** — add features only when measurements justify them.
- **DRY** — one shared model client.
- **POLA** — deterministic behavior from YAML and explicit user markers.

Do not add agents, RAG, MCP, vector databases, rule scripting, distributed tracing, queues, or load balancing to this POC without evidence that they are required.

## Repository Layout

```text
TinyRouter/
├── benchmarks/
├── config/router.yaml
├── docs/kiss_local_ai_router_poc_context.md
├── src/kiss_router/
│   ├── client.py
│   ├── config.py
│   ├── l1.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── rules.py
│   └── server.py
├── tests/
├── pyproject.toml
└── README.md
```

## Current Experiment

The current candidate configuration is:

```text
L1 → LFM2.5-1.2B-Instruct-Q6
L2 → LFM2.5-8B-A1B
L3 → Qwen3.6-35B-A3B
```

The direct `@l2`/`@l3` override exists so users can bypass routing when they explicitly need a stronger model. The benchmark should evaluate automatic routing separately from explicit overrides.

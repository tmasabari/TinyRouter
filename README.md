# TinyRouter

A deliberately small local AI router for testing **Rules → model capability → escalation**.

The POC answers one question:

> Can deterministic routing plus small local models reduce expensive-model calls without unacceptable quality loss?

## Architecture

```text
                         USER
                          |
                   optional @lN
                          |
                          v
                    ORCHESTRATOR
                          |
                    +-----+-----+
                    |           |
                override     automatic
                    |           |
                    v           v
                   Lx       RULE ENGINE
                                |
                                v
                               L1
                                |
                         +------+------+
                         |             |
                     can_handle     escalate
                         |             |
                         v             v
                      answer      RULE ENGINE
                                      |
                                      v
                                     L2
                                      |
                               ... -> L3
```

**Models do not select other models.** A model only reports:

```json
{"status":"can_handle","reason_code":"simple_question","answer":"actual answer"}
```

or:

```json
{"status":"escalate","reason_code":"complex_reasoning","answer":""}
```

The rule engine decides the next model.

## User Override

Put a marker at the start of a user message:

```text
@l2 Explain this architecture.
@l3 Design the production system.
```

The marker is removed before inference. An explicit override directly calls the selected configured model and bypasses automatic capability routing.

## Configuration

`config/router.yaml` controls models, endpoints, capability prompts, rules, escalation defaults, hop limits, and logging.

Example escalation chain:

```yaml
routing:
  max_hops: 3
  escalation_defaults:
    l1: l2
    l2: l3
```

Rules support:

```text
keywords.any
prompt_chars: gt/gte/lt/lte/eq
reason_codes.any
```

Rules run top-to-bottom; the first enabled match wins. A `source` can restrict a rule to a specific model.

## Async Logging

Logging uses Python's standard `QueueHandler` + `QueueListener`:

```text
request -> queue -> background listener -> console/file
```

Levels:

```text
ERROR WARNING INFO DEBUG TRACE
```

Configuration:

```yaml
logging:
  level: INFO
  console: true
  file: logs/tinyrouter.log
  queue_size: 4096
  include_content: false
```

Logging is intentionally non-blocking for normal request execution. Prompt/response content is not logged by default.

## Current Models

The sample configuration uses:

```text
L1 → LFM2.5-1.2B
L2 → LFM2.5-8B-A1B
L3 → Qwen3.6-35B-A3B
```

Change endpoints/model names in YAML to match your local llama-server instances.

## API

```text
POST http://127.0.0.1:8090/v1/chat/completions
```

Example:

```json
{"model":"router","messages":[{"role":"user","content":"What is dependency injection?"}]}
```

The API is OpenAI-compatible. Physical model endpoints are never accepted from the client.

## Installation

Python 3.11+:

```bash
python -m venv .venv
pip install -e .
```

Runtime dependencies are intentionally minimal: PyYAML plus Python standard-library HTTP/logging.

## Run

```bash
tiny-router --config config/router.yaml
```

## Test

```bash
python -m pytest -v
```

Tests cover configuration, rules, capability parsing, escalation, L1 → L2 → L3, overrides, cycle protection, and failure telemetry.

## Benchmark

The benchmark set contains:

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

Measure:

```text
L1/L2/L3 calls
L2 calls avoided
L1 routing overhead
Total latency
Escalation rate
Failures
Answer quality
```

## Design Rules

- **KISS** — no unnecessary abstractions.
- **YAGNI** — no production infrastructure until the POC proves it is needed.
- **DRY** — one shared HTTP client and one generic model worker.
- **POLA** — YAML controls routing; explicit user markers control explicit overrides.

Intentionally out of scope: RAG, MCP, vector databases, distributed tracing, databases, service discovery, complex rule DSLs, and LLM-as-judge.

## Repository Layout

```text
TinyRouter/
├── benchmarks/
├── config/router.yaml
├── docs/kiss_local_ai_router_poc_context.md
├── src/kiss_router/
│   ├── client.py
│   ├── config.py
│   ├── logger.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── rules.py
│   ├── server.py
│   └── worker.py
├── tests/
├── pyproject.toml
└── README.md
```

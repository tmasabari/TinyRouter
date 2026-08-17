# TinyRouter

A deliberately small local AI router for testing **Rules → L1 → L2** model routing.

The goal is not to build another agent framework. The goal is to measure whether a cheap deterministic rules layer and a fast 0.8B model can avoid unnecessary calls to a larger local model.

## Architecture

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

### Models

| Layer | Model | Purpose |
|---|---|---|
| L1 | Qwen 3.6 0.8B | Fast routing + simple requests |
| L2 | LFM2.5-8B-A1B | Medium-complexity reasoning |

Both model servers use an OpenAI-compatible `/v1/chat/completions` API.

## Why TinyRouter?

Sending every request to L2 is wasteful.

TinyRouter first checks cheap deterministic signals:

- configured keywords;
- prompt character length;
- rule order.

This gives three useful paths:

```text
Rules → L2
Rules → L1
Rules → L1 → L2
```

A simple request requires **one L1 inference**, not two. This was an important correction made during review of the first POC implementation.

## Configuration

Routing is YAML-based.

`config/router.yaml` defines:

- router host/port;
- L1 endpoint/model/settings;
- L2 endpoint/model/settings;
- routing rules;
- L1 confidence threshold.

Example:

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
          any:
            - implement
            - refactor
            - debug
      route: l2

  default_route: l1
```

Rules are evaluated top-to-bottom and the first enabled match wins.

Supported prompt-length operators:

```text
gt
gte
lt
lte
eq
```

Invalid configuration fails at startup rather than silently becoming a non-match.

## L1 Contract

L1 is both the router and the lightweight worker.

For a request it can handle:

```json
{
  "route": "l1",
  "confidence": 0.95,
  "reason_code": "simple_question",
  "answer": "..."
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

Only `l1` and `l2` are valid routes. L1 never selects a physical endpoint.

If L1 returns malformed JSON, TinyRouter retries once. If the second response is invalid, the request falls back to L2.

Low-confidence L1 decisions also escalate to L2.

## Router API

TinyRouter exposes an OpenAI-compatible endpoint:

```text
POST http://127.0.0.1:8090/v1/chat/completions
```

Example:

```bash
curl http://127.0.0.1:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router",
    "messages": [
      {"role": "user", "content": "What is dependency injection?"}
    ]
  }'
```

The physical L1/L2 endpoints are controlled only by `router.yaml`.

## Installation

Requires Python 3.11+.

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -e .
```

The only runtime dependency is PyYAML. HTTP communication uses the Python standard library.

## Run

Start the router with:

```bash
tiny-router --config config/router.yaml
```

or:

```bash
python -m kiss_router.server --config config/router.yaml
```

Default endpoint:

```text
http://127.0.0.1:8090/v1/chat/completions
```

The configured inference servers must already be running at the endpoints in `config/router.yaml`.

## Test

Run:

```bash
python -m pytest
```

The tests cover the core routing contract, including:

- deterministic rule matching;
- first-match behavior;
- configuration validation;
- Rules → L2 bypass;
- one-call L1 handling;
- L1 → L2 escalation;
- low-confidence escalation;
- malformed L1 output and retry/fallback;
- failure telemetry.

## Benchmark

The repository includes a fixed **50-request benchmark set**:

```text
10 simple
10 medium
10 complex
10 obvious coding
10 long-context
```

The prompts are in `benchmarks/test_set.json`. The long-context prompts are expanded at runtime so the repository does not contain 100 KB of duplicated text.

### 1. Start the model servers

Use your normal llama.cpp commands, with the endpoints configured as:

```text
Qwen 3.6 0.8B   → http://127.0.0.1:8081/v1
LFM2.5-8B-A1B   → http://127.0.0.1:8082/v1
TinyRouter      → http://127.0.0.1:8090/v1
```

### 2. Start TinyRouter

```bash
tiny-router --config config/router.yaml
```

### 3. Run the benchmark

From the repository root:

```bash
python benchmarks/run_benchmark.py
```

The default runner compares every prompt against:

```text
Baseline:   prompt → L2
Router:     prompt → TinyRouter → L1/L2
```

It performs one warm-up request against each path first, then measures all 50 prompts.

Results are written to:

```text
benchmark-results/results.csv
benchmark-results/summary.json
```

The CSV contains per-request latency, prompt size, route, source, L1 latency, escalation, and token usage where the model server reports it.

The router exposes benchmark-only metadata through response headers such as:

```text
X-TinyRouter-Route
X-TinyRouter-Source
X-TinyRouter-Model
X-TinyRouter-L1-Latency-Ms
X-TinyRouter-Total-Latency-Ms
X-TinyRouter-Escalation
```

These avoid adding a separate telemetry API to the POC.

### Useful options

Run three passes:

```bash
python benchmarks/run_benchmark.py --repeats 3
```

Use different endpoints:

```bash
python benchmarks/run_benchmark.py \
  --router http://127.0.0.1:8090/v1/chat/completions \
  --l2 http://127.0.0.1:8082/v1/chat/completions
```

Use a different result directory:

```bash
python benchmarks/run_benchmark.py --out benchmark-results/run-01
```

### Interpreting the result

The primary metric is **L2 calls avoided**.

For 50 requests, if TinyRouter produces:

```text
L1 handled       25
L1 escalated     10
Direct L2        15
Total L2 calls   25
```

then:

```text
L2 calls avoided = 50 - 25 = 25
L2 avoidance     = 50%
```

Also compare:

- baseline average latency vs router average latency;
- L1 routing latency;
- L1 escalation rate;
- route accuracy against the benchmark's expected routing hypothesis;
- token usage where available.

The expected routes are deliberately simple hypotheses: simple/medium → L1, complex/coding/long-context → L2. They are not a claim that every model decision is objectively wrong when it differs. Review misroutes manually before changing the rules or L1 prompt.

**Do not use Open WebUI for this benchmark.** It adds another context and network layer and makes the routing experiment harder to interpret. Benchmark the router endpoint directly first.

## Telemetry

The POC records routing events in memory.

Important measurements include:

```text
L1 latency/tokens = routing overhead
Total latency     = user-visible request cost
L2 latency/tokens = worker cost when escalation occurs
```

This is intentionally not backed by a database or distributed telemetry system yet.

## Repository Layout

```text
TinyRouter/
├── benchmarks/
│   ├── test_set.json
│   └── run_benchmark.py
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

## Design Constraints

TinyRouter intentionally follows:

- **KISS** — keep the router small;
- **YAGNI** — implement only what the experiment needs;
- **DRY** — one model client for L1 and L2;
- **POLA** — routing behavior should be predictable from YAML.

Do not add agents, RAG, MCP, vector databases, rule scripting, distributed tracing, load balancing, or complex retry systems until measurements justify them.

## Next Experiment

The next step is benchmarking, not adding architecture.

Compare:

```text
Baseline:
Request → L2

TinyRouter:
Request → Rules → L1/L2
```

Measure:

- percentage handled by L1;
- percentage routed directly to L2 by rules;
- L1 escalation rate;
- L1 routing latency;
- total latency;
- L2 calls avoided;
- token usage;
- answer quality/error rate.

The router is successful only if the routing overhead is outweighed by avoided L2 work without unacceptable quality loss.

## Documentation

The detailed POC user story, architecture decisions, review findings, corrected contracts, and next experiment are documented in:

`docs/kiss_local_ai_router_poc_context.md`

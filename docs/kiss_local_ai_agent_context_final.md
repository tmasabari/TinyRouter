# KISS Local AI Agent — User Story, Architecture & Implementation Context

**Project:** KISS Local AI Agent Routing  
**Owner:** Sabarinathan  
**Date:** 2026-08-17  
**Status:** Architecture baseline / implementation-ready  
**Purpose:** Context handoff for continuing the project in a new chat without re-litigating already-decided model choices.

---

# 1. Executive Decision

The system uses a three-level local AI architecture:

```text
                         USER
                           |
                           v
                +-----------------------+
                | KISS ORCHESTRATOR     |
                |-----------------------|
                | normalize request     |
                | L1 routing            |
                | policy / permissions  |
                | escalation            |
                | telemetry             |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                | L1: Qwen 3.6 0.8B    |
                | FAST ROUTER           |
                +-----------+-----------+
                            |
             +--------------+--------------+
             |                             |
         simple / low risk             capable worker
             |                             |
             v                             v
       L1 response                 +--------+--------+
                                  |                 |
                                  v                 v
                              L2 8B-A1B           L3 Pi
                              medium agent       + Qwen 35B
                                  |                 |
                                  | escalate        |
                                  +--------->--------+
                                                    |
                                           read / edit / bash
                                                    |
                                                    v
                                                  result
```

## Fixed model decisions

| Level | Stack | Responsibility |
|---|---|---|
| **L1** | Qwen 3.6 0.8B | Fast intent classification, routing, lightweight structured work |
| **L2** | LFM2.5-8B-A1B | Medium-complexity tool use, short planning, verification |
| **L3** | Pi + Qwen 3.6 35B | Full coding agent, repository work, deep reasoning |

These model decisions are **locked** unless new benchmark evidence or an explicit architecture decision changes them.

## Guiding principle

> **L1 routes. L2 operates. L3 engineers.**

The objective is not to maximize model size. The objective is:

> **Use the smallest capable model and escalate only when necessary.**

---

# 2. Source Reconciliation

Two project documents were reviewed:

1. The existing KISS continuation context.
2. The Gemini-revised user-story/architecture material.

The Gemini revision is largely consistent with the existing architecture. The final design below preserves the established decisions while resolving several implementation ambiguities.

## Important reconciliations

### A. L1 does not execute privileged tools

The earlier wording allowed an example such as:

```text
L1 -> currency.convert
```

That is misleading.

Correct:

```text
L1
 |
 | route decision
 v
Orchestrator
 |
 | schema + policy
 v
Tool Registry
 |
 v
Tool
```

L1 may recommend or classify a tool, but **the orchestrator owns execution**.

### B. Confidence is advisory, not the security boundary

A small model's confidence value is not mathematically trustworthy enough to determine permission.

Therefore:

```text
confidence -> routing signal
policy      -> security decision
```

### C. L3 should not always require a sequential L1 -> L2 -> L3 path

For coding/repository tasks:

```text
L1 -> L3
```

is preferred.

The architecture is hierarchical, but escalation does not mean every level must execute.

### D. Context should be progressively expanded

Do not send the complete conversation to every model.

```text
full conversation
      |
      v
current task + compact metadata
      |
      v
L1
      |
      v
normalized task
      |
      +----> L2 only if required
      |
      +----> L3 only with relevant context
```

This directly addresses the user's previous observation that large initial contexts can significantly increase local inference latency.

---

# 3. Problem Statement

Build a simple, local, configuration-driven agent system that avoids sending every request to Qwen 3.6 35B.

The system must:

- run primarily on the Ryzen 7 9700X + 64 GB DDR5 workstation;
- minimize latency and memory-bandwidth pressure;
- keep Qwen 3.6 35B available for genuinely difficult work;
- use progressively more capable models only when required;
- support strict structured JSON;
- support safe tool calling;
- use Pi as the mature coding-agent worker;
- avoid reimplementing Pi's coding loop;
- remain understandable and easy to modify;
- avoid unnecessary infrastructure;
- provide clean extension points for future RAG, MCP and Bonsai/ternary inference.

---

# 4. Hardware / Runtime Context

Current target workstation:

- AMD Ryzen 7 9700X
- 8 cores / 16 threads
- Zen 5 / AVX-512 capable
- 64 GB DDR5, dual-channel, 5600 MT/s
- MSI PRO X870E-P WiFi
- Crucial P510 1 TB Gen5 NVMe
- Windows 11
- WSL2 Ubuntu
- llama.cpp as primary local inference engine
- Integrated Radeon graphics

Current practical strategy:

> CPU/local inference is the baseline; future GPU changes must not alter the logical agent architecture.

The execution backend should remain replaceable.

---

# 5. Existing Benchmark Evidence

Qwen 3.6 0.8B has already been benchmarked and considered a good L1 candidate.

Observed approximately:

- prompt processing: ~562 tok/s
- generation: ~54 tok/s
- n-gram experiment: ~583 prompt tok/s and ~55 generation tok/s

The exact numbers are benchmark evidence, not contractual performance targets.

Existing heavy-model work has already established Qwen 3.6 35B as the L3 candidate.

The important architectural lesson is:

> Do not use the 35B model for work that a lower level can complete reliably.

---

# 6. User Story

## Epic

**As a local AI developer, I want a hierarchical local agent system that automatically selects the least expensive model capable of completing a task, so that routine requests are fast while difficult coding and reasoning tasks receive the full capability of Qwen 3.6 35B through Pi.**

---

# 7. User Stories and Acceptance Criteria

## US-001 — Fast request classification

**As a user, I want every request to first pass through Qwen 3.6 0.8B so that simple requests do not unnecessarily wake larger models.**

Acceptance criteria:

- L1 is Qwen 3.6 0.8B.
- L1 receives the current task plus minimal routing metadata.
- Full historical context is not sent by default.
- L1 returns strict structured JSON.
- L1 cannot directly execute privileged tools.
- Invalid L1 output is rejected and handled deterministically.
- L1 routing latency is measurable.

---

## US-002 — Configuration-driven routing

**As a system designer, I want model and routing behavior defined through configuration so that models can be changed without rewriting the orchestrator.**

Configuration must support at least:

- model endpoint/name;
- capability;
- level;
- context limit;
- timeout;
- retry count;
- escalation threshold;
- allowed tools;
- fallback;
- enabled/disabled state.

Example:

```yaml
models:
  l1:
    id: qwen3.6-0.8b
    endpoint: http://127.0.0.1:8081
    timeout_ms: 2000

  l2:
    id: lfm2.5-8b-a1b
    endpoint: http://127.0.0.1:8082
    timeout_ms: 10000

  l3:
    agent: pi
    model: qwen3.6-35b-a3b
```

Model identifiers must not be embedded throughout application code.

---

## US-003 — Medium-complexity agent work

**As a user, I want moderate tool workflows to use LFM2.5-8B-A1B so that the 35B model is reserved for difficult work.**

Examples:

- multiple related tool calls;
- structured extraction plus an action;
- lightweight research;
- short planning;
- result verification.

Acceptance criteria:

- L2 receives a normalized task.
- L2 can request only allowlisted tools.
- Tool calls are schema validated.
- Tool results are returned to L2.
- L2 can continue, finish, or escalate.
- Maximum tool-chain length is configurable.
- Repeated failures cause escalation.

---

## US-004 — Heavy coding-agent execution

**As a user, I want difficult software-engineering tasks delegated to Pi + Qwen 3.6 35B so that repository work is handled by the strongest local agent.**

Examples:

- repository inspection;
- feature implementation;
- refactoring;
- debugging;
- multi-file changes;
- architecture design;
- test/fix iterations.

Acceptance criteria:

- Pi owns the coding-agent loop.
- Qwen 3.6 35B is the L3 reasoning model.
- Pi can use filesystem and shell capabilities subject to policy.
- The orchestrator does not reimplement Pi's agent loop.
- L3 receives relevant context rather than the entire history whenever practical.
- Destructive operations remain policy controlled.

---

## US-005 — Safe tool execution

**As a system designer, I want tool calls validated outside the model so malformed or unsafe model output cannot directly execute privileged operations.**

Required flow:

```text
LLM output
    |
    v
JSON parsing
    |
    v
Pydantic/schema validation
    |
    v
Policy engine
    |
    +---- allowed --------> execute
    |
    +---- confirmation ---> user
    |
    +---- denied ---------> reject
```

The LLM is untrusted input.

---

## US-006 — Automatic escalation

**As a user, I want lower-level models to escalate when they cannot safely or reliably complete a task.**

Escalation signals:

- unsupported task type;
- low routing confidence;
- invalid structured output;
- context exceeds configured limit;
- tool-chain limit;
- repeated tool failures;
- contradictory tool results;
- explicit deep-reasoning request;
- repository/coding task;
- multi-file implementation;
- policy-required escalation;
- L2 determines that it cannot complete the task.

Important:

> Escalation is a deterministic orchestrator decision informed by the model, not a model-controlled privilege.

---

# 8. Routing Policy

## L1 — Qwen 3.6 0.8B

Primary role:

- intent classification;
- task classification;
- routing;
- lightweight structured extraction;
- simple Q&A;
- simple transformations;
- deciding whether a worker is needed.

L1 should be optimized for:

> fast, predictable, structured decisions.

---

## L2 — LFM2.5-8B-A1B

Primary role:

- moderate planning;
- tool selection;
- short tool loops;
- result verification;
- lightweight research;
- structured extraction;
- medium-complexity workflows.

L2 is the:

> medium agent.

---

## L3 — Pi + Qwen 3.6 35B

Primary role:

- software engineering;
- repository reasoning;
- debugging;
- architecture;
- complex synthesis;
- difficult multi-step workflows;
- filesystem modifications;
- repeated L1/L2 failures.

L3 is the:

> full engineering agent.

---

# 9. Routing Strategy

The routing algorithm should remain simple.

```text
                REQUEST
                   |
                   v
          +----------------+
          | Normalize      |
          | + metadata     |
          +-------+--------+
                  |
                  v
          +----------------+
          | L1 Qwen 0.8B   |
          +-------+--------+
                  |
          +-------+--------+
          |                |
        L1 OK           worker needed
          |                |
          v                v
       response      +-----+------+
                     |            |
                  L2 suitable   L3 required
                     |            |
                     v            v
                    L2           Pi
                     |            |
                  success      Qwen 35B
                     |            |
                     +-----+------+
                           |
                         result
```

For known high-complexity categories, L1 should route directly to L3.

Example:

```text
"Refactor authentication subsystem"
        |
        v
       L1
        |
        v
       L3
        |
        v
      Pi + 35B
```

Do not force:

```text
L1 -> L2 -> L3
```

when L2 clearly adds no value.

---

# 10. Strict L1 Routing Contract

The routing response should be intentionally small.

Recommended schema:

```json
{
  "route": "L1 | L2 | L3",
  "task_type": "qa | transform | tool | research | coding | architecture | other",
  "needs_tools": false,
  "needs_files": false,
  "needs_long_context": false,
  "confidence": 0.95,
  "reason_code": "simple_qa"
}
```

Use a finite `task_type` and `reason_code` vocabulary wherever possible.

Avoid allowing arbitrary natural-language routing instructions.

Why:

- smaller JSON;
- easier validation;
- easier testing;
- less hallucination surface;
- easier telemetry;
- easier future policy rules.

`reason_code` is for observability and debugging. It is not a security decision.

---

# 11. Normalized Task Contract

Do not pass raw L1 output directly to L2/L3.

The orchestrator should produce a normalized task:

```json
{
  "request_id": "uuid",
  "user_request": "string",
  "route": "L2",
  "task_type": "tool",
  "constraints": [],
  "cwd": null,
  "context": [],
  "available_tools": [],
  "attempt": 0
}
```

This creates a stable boundary between routing and execution.

---

# 12. Tool Contract

Recommended:

```json
{
  "tool": "currency.convert",
  "arguments": {
    "amount": 100,
    "from": "USD",
    "to": "INR"
  }
}
```

Do not require the model to provide a long explanation.

Tool execution should be:

```text
tool name
+
validated arguments
+
policy decision
```

The tool registry owns the actual implementation.

---

# 13. Policy Engine

The policy engine is deterministic.

Example:

```text
Tool Request
    |
    +-- known tool? -------- no ---> reject
    |
    +-- valid schema? ------ no ---> reject
    |
    +-- permitted level? --- no ---> reject
    |
    +-- permitted path? ---- no ---> reject
    |
    +-- destructive? ------- yes --> confirmation / deny
    |
    +-- timeout exceeded? -- yes --> terminate
    |
    +-----------------------------> execute
```

Examples of POLA controls:

- read-only vs write permission;
- allowed working directory;
- shell command restrictions;
- timeout;
- output-size limit;
- network permission;
- maximum tool calls;
- maximum retries.

---

# 14. L3 / Pi Boundary

Pi is an external worker.

The orchestrator should not reproduce:

- file-reading loops;
- edit loops;
- shell loops;
- compiler/test iteration;
- agent memory internals.

The orchestrator provides:

```text
task
+
relevant context
+
working directory
+
policy constraints
```

Pi performs:

```text
reason
 -> inspect
 -> modify
 -> execute
 -> test
 -> iterate
```

The result is returned to the orchestrator.

---

# 15. Context Management

Context is one of the main performance controls.

Maintain a compact state:

```text
AgentState
├── request
├── task_type
├── constraints
├── summary
├── relevant_files
├── relevant_tool_results
├── failures
└── attempt
```

Do not automatically propagate:

- entire conversation;
- unrelated files;
- old tool results;
- duplicated instructions;
- verbose model reasoning.

Preferred flow:

```text
Conversation
    |
    v
Task extraction
    |
    v
Compact state
    |
    v
L1
    |
    v
Normalized task
    |
    +--> L2 context
    |
    +--> L3 relevant context
```

---

# 16. Architecture Components

```text
+---------------------+
| CLI / UI / API      |
+----------+----------+
           |
           v
+---------------------+
| KISS Orchestrator   |
|---------------------|
| normalization       |
| routing             |
| state               |
| escalation          |
| policy              |
| telemetry           |
+----+-----------+----+
     |           |
     |           +------------------+
     v                              v
+-----------+                 +-------------+
| L1        |                 | Tool        |
| Qwen .8B |                 | Registry    |
+-----+-----+                 +------+------+
      |                              ^
      |                              |
      v                              |
+-----------+                         |
| L2        +-------------------------+
| LFM 8B    |
+-----+-----+
      |
      | escalate
      v
+---------------------+
| L3 Worker           |
| Pi + Qwen 35B       |
+----------+----------+
           |
     +-----+-----+
     |     |     |
    read  edit  bash
```

---

# 17. Technology Choices

## Phase 1 stack

Use:

- Python;
- Pydantic;
- YAML;
- httpx;
- pytest;
- standard logging / JSON logging.

Model access:

- llama.cpp HTTP API.

L3:

- Pi interface/RPC.

## Explicitly avoid initially

- LangChain;
- LangGraph;
- Kafka;
- Redis;
- Celery;
- Kubernetes;
- vector database;
- distributed queues;
- custom multi-agent framework.

Reason:

> No concrete requirement yet.

---

# 18. Repository Structure

Recommended:

```text
kiss-agent/
├── pyproject.toml
├── README.md
├── config/
│   └── agent.yaml
├── src/
│   └── kiss_agent/
│       ├── __init__.py
│       ├── app.py
│       ├── orchestrator/
│       │   ├── router.py
│       │   ├── state.py
│       │   └── escalation.py
│       ├── models/
│       │   ├── base.py
│       │   ├── llama_cpp.py
│       │   └── registry.py
│       ├── tools/
│       │   ├── base.py
│       │   ├── registry.py
│       │   └── executor.py
│       ├── policy/
│       │   └── engine.py
│       ├── workers/
│       │   └── pi.py
│       └── telemetry/
│           └── events.py
└── tests/
    ├── unit/
    ├── integration/
    └── evaluation/
```

Keep modules small.

---

# 19. Configuration Design

Example:

```yaml
system:
  default_timeout_ms: 10000
  max_escalations: 2
  max_tool_calls: 8

models:
  l1:
    id: qwen3.6-0.8b
    endpoint: http://127.0.0.1:8081
    timeout_ms: 2000

  l2:
    id: lfm2.5-8b-a1b
    endpoint: http://127.0.0.1:8082
    timeout_ms: 10000

  l3:
    agent: pi
    model: qwen3.6-35b-a3b
    endpoint: http://127.0.0.1:8083
    timeout_ms: 120000

routing:
  defaults:
    low_confidence_threshold: 0.70
    max_l2_tool_calls: 6
    max_l2_attempts: 2

  task_types:
    coding:
      level: l3

    architecture:
      level: l3

    simple_qa:
      level: l1

    simple_tool:
      level: l1

    multi_tool:
      level: l2

tools:
  enabled: []

policy:
  default: deny
```

The actual YAML should be implemented with a validated Pydantic configuration model.

---

# 20. ADRs

## ADR-001 — Hierarchical routing

**Decision:** L1 -> L2 -> L3 capability tiers.

**Reason:** Reduce unnecessary large-model inference and context cost.

---

## ADR-002 — Qwen 3.6 0.8B as L1

**Decision:** Fixed.

**Reason:** Already benchmarked successfully on the target workstation and fast enough for routing.

---

## ADR-003 — LFM2.5-8B-A1B as L2

**Decision:** Fixed.

**Reason:** Medium-capability local model with approximately 1B active parameters and suitable role for tool-oriented workflows.

---

## ADR-004 — Pi as L3 agent framework

**Decision:** Fixed.

**Reason:** Reuse an existing coding-agent loop rather than rebuilding it.

---

## ADR-005 — Qwen 3.6 35B as L3

**Decision:** Fixed.

**Reason:** Existing local benchmark/work and strongest selected reasoning/coding model.

---

## ADR-006 — Configuration-driven model selection

**Decision:** Fixed.

Model names/endpoints are configuration, not application logic.

---

## ADR-007 — KISS orchestrator

**Decision:** Python + Pydantic + YAML + HTTP APIs.

No heavyweight orchestration framework until required.

---

## ADR-008 — Routing and execution separation

**Decision:** Orchestrator routes; workers execute.

---

## ADR-009 — LLM is never the security boundary

**Decision:** All tool calls pass through external validation and policy.

---

## ADR-010 — Direct escalation is allowed

**Decision:** L1 may route directly to L3.

**Reason:** Avoid wasting L2 inference on tasks that are clearly beyond L2, especially repository coding and architecture work.

---

## ADR-011 — Context minimization

**Decision:** Pass only task-relevant context.

**Reason:** Large context materially increases local inference cost and latency.

---

# 21. Observability

Every request should produce structured events.

Example:

```json
{
  "request_id": "uuid",
  "timestamp": "2026-08-17T20:00:00+05:30",
  "route": "L2",
  "model": "lfm2.5-8b-a1b",
  "latency_ms": 850,
  "tokens_in": 220,
  "tokens_out": 38,
  "confidence": 0.91,
  "escalated": false,
  "tool_calls": 2,
  "success": true
}
```

Track:

- L1 latency;
- L2 latency;
- L3 latency;
- end-to-end latency;
- prompt tokens;
- generated tokens;
- escalation rate;
- false escalation rate;
- missed escalation rate;
- invalid JSON rate;
- tool success/failure;
- retries;
- RAM usage;
- CPU utilization.

Primary routing KPI:

> **L1 correct-route rate and L1 avoid-L3 rate.**

Quality KPI:

> **Task success rate compared with direct L3.**

Performance KPI:

> **End-to-end latency reduction compared with direct L3.**

---

# 22. Evaluation Strategy

Do not optimize only for routing accuracy.

Evaluate four dimensions:

```text
                 +----------------+
                 | Agent Quality  |
                 +-------+--------+
                         |
        +----------------+----------------+
        |                |                |
   latency           cost/CPU        correctness
        |                |                |
        +----------------+----------------+
                         |
                    escalation
```

Benchmark configurations:

1. **Direct L3**
2. **L1 only**
3. **L1 -> L2**
4. **L1 -> L2 -> L3**
5. **L1 -> L3 for coding**

Measure:

- task success;
- time to first token;
- total latency;
- tokens generated;
- model invocation count;
- escalation rate;
- failure recovery;
- JSON adherence.

The routing system is successful only if it reduces cost/latency **without materially reducing task success**.

---

# 23. Evaluation Dataset

Create a small deterministic benchmark before connecting all real models.

Categories:

```text
A. Simple QA
B. Transformation
C. Simple structured extraction
D. Simple tool request
E. Multi-tool request
F. Research
G. Coding
H. Architecture
I. Long-context
J. Invalid/ambiguous request
K. Tool misuse
L. Destructive request
M. Explicit escalation
```

Each case should contain:

```yaml
id:
request:
expected_route:
expected_tools:
expected_escalation:
risk:
```

Example:

```yaml
id: coding_001
request: "Refactor the authentication subsystem"
expected_route: L3
expected_tools: [filesystem, shell]
expected_escalation: false
risk: write
```

This makes routing regressions measurable.

---

# 24. Implementation Plan

## Phase 0 — Contracts first

Before real model integration:

- define Pydantic schemas;
- define configuration schema;
- define `ModelAdapter`;
- define `Tool`;
- define `ToolRegistry`;
- define `PolicyEngine`;
- define `AgentState`;
- define `Router`.

Use deterministic mocks.

### Exit criteria

All routing tests pass without loading a model.

---

## Phase 1 — Orchestrator skeleton

Implement:

- request normalization;
- configuration loading;
- state management;
- routing;
- escalation;
- telemetry;
- error handling.

### Exit criteria

A complete request can flow through mock L1/L2/L3 workers.

---

## Phase 2 — Real L1

Connect Qwen 3.6 0.8B through llama.cpp.

Implement:

- minimal routing prompt;
- strict JSON output;
- schema validation;
- retry on invalid JSON;
- deterministic escalation fallback.

### Exit criteria

L1 achieves acceptable routing accuracy on the benchmark suite.

---

## Phase 3 — Real L2

Connect LFM2.5-8B-A1B.

Implement:

- tool planning;
- allowlisted tool calls;
- tool-result loop;
- verification;
- escalation.

### Exit criteria

Medium tasks complete without L3 in the majority of suitable cases.

---

## Phase 4 — L3 / Pi

Connect Pi + Qwen 3.6 35B.

Implement:

- task delegation;
- relevant context packaging;
- workspace policy;
- result capture;
- timeout;
- escalation/result propagation.

### Exit criteria

Repository coding tasks can be delegated end-to-end.

---

## Phase 5 — Security hardening

Implement:

- default-deny tool policy;
- filesystem restrictions;
- shell restrictions;
- timeouts;
- output limits;
- retry limits;
- destructive-operation confirmation;
- audit logs.

### Exit criteria

No model output can bypass policy.

---

## Phase 6 — Benchmark and tune

Compare:

```text
Direct L3
L1
L1 -> L2
L1 -> L3
Full hierarchy
```

Tune:

- L1 prompt;
- routing thresholds;
- task categories;
- escalation limits;
- context packaging;
- model server settings.

Only tune after correctness is established.

---

# 25. Future Extensions

## RAG

Deferred.

When implemented:

```text
L1
 |
 +--> retrieval required?
 |
 v
Retriever
 |
 v
relevant context
 |
 +--> L2/L3
```

RAG is conditional, not automatic.

---

## MCP

Deferred.

MCP should be another tool provider:

```text
Tool Registry
├── native tools
├── local scripts
├── APIs
└── MCP tools
```

Do not make MCP a core dependency.

---

## Bonsai / Ternary

Deferred execution-layer optimization.

The routing architecture must remain unaware of kernel implementation.

Potential future path:

```text
Pi
 |
Qwen 35B
 |
llama.cpp API
 |
+-- standard quantization
+-- IQ quantization
+-- Bonsai / ternary backend
```

This allows kernel experiments without changing agent logic.

---

# 26. Non-Goals

Version 1 will not:

- create a general-purpose multi-agent framework;
- spawn unlimited agents;
- provide unrestricted filesystem access;
- add Kubernetes;
- add Kafka;
- add Redis;
- add Celery;
- add a vector database;
- implement RAG before routing works;
- implement MCP before the native tool registry works;
- implement Bonsai kernels as part of the orchestrator;
- optimize for cloud deployment.

---

# 27. Definition of Done

The first usable release is done when:

- [ ] L1 uses Qwen 3.6 0.8B.
- [ ] L2 uses LFM2.5-8B-A1B.
- [ ] L3 uses Pi + Qwen 3.6 35B.
- [ ] Routing is configuration-driven.
- [ ] L1 output is strictly validated.
- [ ] Tool execution is external to the LLM.
- [ ] Policy is default-deny.
- [ ] L1 can route directly to L3.
- [ ] Context is minimized at each level.
- [ ] Escalations are observable.
- [ ] Deterministic mock tests exist.
- [ ] Real-model benchmark tests exist.
- [ ] Direct-L3 baseline is measured.
- [ ] Full hierarchy is benchmarked against the baseline.

---

# 28. Continuation Instructions

For future chats, assume:

1. L1 = Qwen 3.6 0.8B.
2. L2 = LFM2.5-8B-A1B.
3. L3 = Pi + Qwen 3.6 35B.
4. These choices are fixed unless new benchmark evidence is introduced.
5. The orchestrator remains KISS.
6. No LangChain/LangGraph/Kafka/Redis/Kubernetes unless a concrete requirement appears.
7. Pi owns the L3 coding-agent loop.
8. LLMs are untrusted.
9. Tool calls always pass through schema + policy.
10. Full conversation history is not propagated automatically.
11. RAG, MCP and Bonsai are deferred.
12. The next implementation target is contracts + deterministic mocks + L1 integration.
13. Do not redesign the architecture merely to replace the selected models.

---

# 29. Final Architecture

```text
                              USER
                                |
                                v
                    +-----------------------+
                    | KISS ORCHESTRATOR     |
                    |-----------------------|
                    | normalize             |
                    | state                 |
                    | route                 |
                    | policy                |
                    | escalate              |
                    | telemetry             |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | L1                    |
                    | Qwen 3.6 0.8B         |
                    | FAST ROUTER           |
                    +-----------+-----------+
                                |
                +---------------+---------------+
                |                               |
             simple                         worker needed
                |                               |
                v                         +-----+-----+
             response                    |           |
                                         v           v
                                        L2          L3
                                   LFM2.5-8B-A1B   Pi + 35B
                                        |           |
                                        |           +--> read
                                        |           +--> edit
                                        |           +--> bash
                                        |
                                     escalate
                                        |
                                        +----------> L3
                                                    |
                                                    v
                                                  result
```

## Architecture slogan

> **L1 routes. L2 operates. L3 engineers.**

## Engineering principles

> **KISS** — keep the system understandable.  
> **YAGNI** — do not add infrastructure before it is needed.  
> **DRY** — one routing contract, one policy boundary, one tool registry.  
> **POLA** — models receive only the capabilities and context they need.

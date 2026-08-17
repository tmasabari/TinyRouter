# KISS Local AI Agent Architecture — Continuation Context

**Project:** Local AI Config / KISS Agent Routing
**Owner:** Sabarinathan
**Date:** 2026-08-17
**Purpose:** Context handoff for continuing the architecture and implementation in a new chat thread.

---

## 1. Executive Decision

The selected three-level local AI architecture is:

```text
                         USER
                           |
                           v
                 +----------------------+
                 | KISS ORCHESTRATOR    |
                 | Policy + Routing     |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | L1: Qwen 3.6 0.8B   |
                 | Fast Router / Utility|
                 +----------+-----------+
                            |
                    complexity / intent
                            |
               +------------+-------------+
               |                          |
               v                          v
     +----------------------+   +-------------------------+
     | L2: LFM2.5-8B-A1B   |   | L3: Pi + Qwen 3.6 35B |
     | Medium Agent         |   | Heavy Coding/Reasoning |
     +----------+-----------+   +-----------+-------------+
                |                           |
                |                           v
                |                    read / edit / bash
                |                           |
                +---------------------------+
```

### Fixed model decisions

| Level | Selected stack | Primary responsibility |
|---|---|---|
| **L1** | **Qwen 3.6 0.8B** | Fast intent classification, routing, lightweight tasks, structured decisions |
| **L2** | **LFM2.5-8B-A1B** | Medium-complexity tool use, multi-step tool planning, verification, lightweight agent work |
| **L3** | **Pi + Qwen 3.6 35B** | Full coding agent, repository work, deep reasoning, architecture, difficult multi-step tasks |

These are the **current architecture decisions**. Do not replace them with other models unless a later benchmark or explicit decision changes the ADR.

---

# 2. Problem Statement

The goal is to build a simple, local, configuration-driven AI agent system that avoids sending every request to a large 35B model.

The system should:

- run primarily on the existing Ryzen 7 9700X + 64 GB DDR5 workstation;
- minimize latency and memory bandwidth consumption;
- keep the large Qwen 3.6 35B model available for genuinely difficult work;
- use progressively more capable models only when required;
- support tool calling and structured JSON;
- use Pi as the mature coding-agent worker rather than reimplementing a coding-agent loop;
- remain simple enough to understand and modify;
- avoid unnecessary frameworks and infrastructure;
- eventually provide a clean foundation for RAG, MCP, and future Bonsai/ternary inference experiments.

---

# 3. Hardware Context

Current workstation:

- CPU: AMD Ryzen 7 9700X
- CPU topology: 8 cores / 16 threads, Zen 5
- AVX-512 capable
- RAM: 64 GB DDR5, dual-channel, currently 5600 MT/s
- Motherboard: MSI PRO X870E-P WiFi
- SSD: Crucial P510 1 TB Gen5 NVMe
- PSU: Deepcool PN1000D 1000W Gold
- Case: Cooler Master Elite 502
- OS: Windows 11
- Development/runtime environment: WSL2 Ubuntu
- Primary inference engine: llama.cpp
- Current dedicated GPU: none
- iGPU: integrated Radeon graphics; previous tests showed CPU-only llama.cpp inference is currently preferable for large models.

The system is CPU/memory-bandwidth oriented today. A future discrete GPU may change the execution strategy, but must not change the logical routing architecture.

---

# 4. Existing Performance Evidence

The user has already benchmarked Qwen 3.6 0.8B and found it to be a good practical small-model candidate.

Previously observed Qwen 3.6 0.8B performance was approximately:

- prompt processing: ~562 tokens/s
- generation: ~54 tokens/s
- an n-gram experiment reached approximately ~583 prompt tokens/s and ~55 generation tokens/s.

This makes Qwen 3.6 0.8B a strong L1 candidate because the router can make decisions much faster than the large model.

Existing Gemma 4 26B IQ4_XS benchmark:

- model size: ~12.65 GiB
- parameters: ~25.23B
- prompt 512: 57.59 t/s
- prompt 1024: 56.80 t/s
- generation: 13.35 t/s

Existing Qwen 3.6 35B-A3B MTP work has already demonstrated the suitability of Qwen 3.6 35B as the heavy reasoning/coding model.

Important principle:

> Do not use the large model to perform work that L1 or L2 can perform reliably.

---

# 5. User Story

## Epic

**As a local AI developer, I want a hierarchical local agent system that automatically selects the least expensive model capable of completing a task, so that routine requests are fast and cheap while complex coding/reasoning tasks receive the full capability of Qwen 3.6 35B through Pi.**

---

## US-001 — Fast request classification

**As a user,**  
I want every request to first pass through a very small local model,  
so that simple requests do not wake the large model.

### Acceptance criteria

- L1 uses Qwen 3.6 0.8B.
- L1 receives only the current task plus minimal required metadata.
- L1 returns a strict structured routing result.
- L1 does not receive the entire historical conversation by default.
- L1 should complete routine classification with very low latency.
- L1 must not directly execute dangerous tools.

---

## US-002 — Configuration-driven routing

**As a system designer,**  
I want routing decisions to be defined through configuration rather than hard-coded model names,  
so that models can be replaced or benchmarked without rewriting the orchestrator.

### Acceptance criteria

Routing configuration must allow:

- model selection;
- task capabilities;
- escalation thresholds;
- tool permissions;
- context limits;
- timeouts;
- retry policy;
- fallback model;
- enabled/disabled models.

Example conceptual configuration:

```yaml
levels:
  l1:
    model: qwen3.6-0.8b
  l2:
    model: lfm2.5-8b-a1b
  l3:
    agent: pi
    model: qwen3.6-35b-a3b
```

---

## US-003 — Medium-complexity tool execution

**As a user,**  
I want medium-complexity requests to use LFM2.5-8B-A1B,  
so that multi-step tool tasks do not unnecessarily consume the 35B model.

Examples:

- several related API calls;
- simple research workflows;
- structured extraction followed by actions;
- tool-result verification;
- short multi-step plans;
- moderate-context tasks.

Acceptance criteria:

- L2 can receive a normalized task from L1.
- L2 can select from an allowlisted tool registry.
- L2 can generate structured tool calls.
- L2 can inspect tool results.
- L2 can decide whether to continue or escalate.
- L2 escalates to L3 when task complexity exceeds configured limits.

---

## US-004 — Heavy coding-agent execution

**As a user,**  
I want difficult software-engineering tasks to be delegated to Pi + Qwen 3.6 35B,  
so that the strongest local model handles repository inspection, coding, debugging and architecture.

Examples:

- inspect a repository;
- implement a feature;
- refactor code;
- diagnose build failures;
- modify multiple files;
- design a large architecture;
- run tests;
- iterate based on compiler/test results.

Acceptance criteria:

- Pi remains responsible for the agent loop.
- Qwen 3.6 35B is the L3 reasoning model.
- Pi can use filesystem and shell tools.
- The orchestrator does not reimplement Pi's tool loop.
- L3 receives only the relevant task/context whenever practical.
- Dangerous/destructive operations remain subject to policy controls.

---

## US-005 — Safe tool execution

**As a system designer,**  
I want tool calls validated outside the model,  
so that malformed or unsafe model output cannot directly execute privileged operations.

Required flow:

```text
Model
  |
  v
Structured tool request
  |
  v
Schema validation
  |
  v
Policy engine
  |
  +--> allowed ------> execute
  |
  +--> confirmation -> ask user
  |
  +--> denied -------> reject
```

The model is never the security boundary.

---

## US-006 — Escalation

**As a user,**  
I want the system to escalate automatically when a lower-level model is uncertain or incapable,  
so that small models do not fail silently.

Escalation signals may include:

- low confidence;
- unsupported task type;
- tool-chain length;
- context size;
- number of files;
- number of tool calls;
- repeated failures;
- invalid JSON;
- tool-result contradiction;
- explicit request for deep reasoning;
- coding/repository task;
- user request for high-quality architecture.

---

# 6. Routing Policy

The initial routing policy should remain simple.

## L1 — Qwen 3.6 0.8B

Use for:

- intent classification;
- request classification;
- simple JSON generation;
- task routing;
- lightweight transformations;
- simple question answering;
- deciding whether a tool is potentially relevant;
- deciding whether L2/L3 is required.

L1 should be extremely cheap.

---

## L2 — LFM2.5-8B-A1B

Use for:

- tool selection requiring judgment;
- multiple related tool calls;
- moderate planning;
- tool-result verification;
- short agent loops;
- structured extraction from moderately complex inputs;
- lightweight research;
- tasks that need more semantic judgment than L1.

L2 should be considered the **medium agent**.

---

## L3 — Pi + Qwen 3.6 35B

Use for:

- repository coding;
- debugging;
- architecture;
- deep reasoning;
- large multi-step workflows;
- difficult tool chains;
- complex document/code synthesis;
- tasks requiring filesystem modifications;
- tasks that repeatedly fail at L1/L2.

L3 is the **full agent**.

---

# 7. Routing Examples

## Example A — simple tool

User:

> "Convert 100 USD to INR."

```text
L1 Qwen 0.8B
    |
    +--> simple structured request
    |
    v
currency.convert
```

No L2/L3.

---

## Example B — moderate tool workflow

User:

> "Find my manager, check her availability and suggest two suitable meeting slots."

```text
L1
 |
 +--> multi-step tool task
 |
 v
L2 LFM2.5-8B-A1B
 |
 +--> people.lookup
 +--> calendar.check
 +--> generate options
```

L3 is unnecessary unless L2 fails.

---

## Example C — coding

User:

> "Review this repository and refactor the authentication subsystem."

```text
L1
 |
 +--> coding/repository task
 |
 v
L3
 |
 v
Pi
 |
 v
Qwen 3.6 35B
 |
 +--> read
 +--> grep/search
 +--> edit
 +--> bash
 +--> test
 +--> iterate
```

L2 is skipped.

---

# 8. Architecture Decision Records

## ADR-001 — Use hierarchical routing

**Decision:** Adopt three capability tiers.

```text
L1 -> L2 -> L3
```

**Rationale:**

- minimizes expensive inference;
- reduces context passed to large models;
- keeps latency low;
- provides clear failure/escalation boundaries;
- enables independent model benchmarking.

**Rejected alternative:** Send every request directly to Qwen 35B.

Reason: unnecessarily expensive and slow.

---

## ADR-002 — Qwen 3.6 0.8B is L1

**Decision:** Use Qwen 3.6 0.8B as the first-stage router.

**Rationale:**

- already benchmarked successfully on the target workstation;
- approximately 54–55 generation tok/s in existing tests;
- capable enough for classification and lightweight reasoning;
- much cheaper than L2/L3;
- known local deployment path.

**Rejected alternatives:** FunctionGemma, LFM2.5-350M and other tiny models as primary L1.

They remain benchmark candidates/specialists, but the existing Qwen 0.8B benchmark is the current baseline.

---

## ADR-003 — LFM2.5-8B-A1B is L2

**Decision:** Use LFM2.5-8B-A1B as the medium agent.

**Rationale:**

- MoE architecture gives a larger parameter pool with approximately 1B active parameters;
- designed for tool-oriented agent workflows;
- provides a meaningful capability jump over sub-billion-parameter routers;
- avoids invoking 35B for moderate workflows.

---

## ADR-004 — Pi is L3 agent framework

**Decision:** Use Pi rather than building a custom coding-agent loop.

**Rationale:**

Pi already provides the basic coding-agent primitives and agent loop required for:

- reading files;
- editing files;
- executing shell commands;
- iterative coding workflows.

The custom system should focus on orchestration and routing rather than reproducing Pi's agent loop.

---

## ADR-005 — Qwen 3.6 35B is L3 model

**Decision:** Use Qwen 3.6 35B-A3B as the primary L3 reasoning model.

**Rationale:**

- already part of the user's local inference workflow;
- strong coding/reasoning candidate;
- MTP support already investigated;
- suitable for difficult local software-engineering tasks.

---

## ADR-006 — Configuration over hard-coded routing

**Decision:** Model selection must be configuration-driven.

Bad:

```python
if complex:
    use_qwen()
```

Preferred:

```yaml
routing:
  coding:
    level: l3

  simple_tool:
    level: l1

  multi_tool:
    level: l2
```

This allows future experiments without architectural rewrites.

---

## ADR-007 — Keep the orchestrator KISS

Do NOT initially introduce:

- LangChain;
- LangGraph;
- Redis;
- Kafka;
- Kubernetes;
- vector database;
- complex multi-agent framework;
- distributed task queue.

Start with:

```text
Python
+ configuration
+ llama.cpp HTTP API
+ Pi RPC
+ Pydantic/schema validation
```

Add infrastructure only when a concrete requirement appears.

---

## ADR-008 — Separate routing from execution

The router decides:

```text
WHAT should happen?
WHO should do it?
```

The worker decides:

```text
HOW should it happen?
```

Therefore:

```text
Orchestrator
     |
     +--> L1
     |
     +--> L2
     |
     +--> Pi/L3
```

Pi remains responsible for the detailed coding-agent loop.

---

## ADR-009 — Security outside the LLM

Never allow raw LLM output to execute a tool.

Required:

```text
LLM
 ↓
JSON schema
 ↓
policy
 ↓
permission
 ↓
execution
```

The model is not trusted code.

---

# 9. Proposed Component Architecture

```text
                    +----------------------+
                    |       CLI / UI        |
                    +-----------+----------+
                                |
                                v
                    +----------------------+
                    |  KISS ORCHESTRATOR   |
                    |----------------------|
                    | request normalization|
                    | routing              |
                    | policy               |
                    | escalation           |
                    | telemetry            |
                    +-----------+----------+
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
            +---------------+       +---------------+
            | L1 Qwen 0.8B  |       | Tool Registry |
            +-------+-------+       +-------+-------+
                    |                       |
                    | route                 |
                    v                       |
            +---------------+               |
            | L2 LFM2.5     |---------------+
            | 8B-A1B        |
            +-------+-------+
                    |
                    | escalate
                    v
            +----------------------+
            | L3 Pi                |
            | Qwen 3.6 35B         |
            +----------+-----------+
                       |
              +--------+--------+
              |        |        |
             read     edit     bash
```

---

# 10. Logical Interfaces

## Router input

```json
{
  "request": "string",
  "conversation_summary": "optional string",
  "cwd": "optional path",
  "available_tools": []
}
```

## L1 output

```json
{
  "level": "L1 | L2 | L3",
  "task_type": "string",
  "needs_tools": true,
  "needs_files": false,
  "needs_long_context": false,
  "confidence": 0.0,
  "reason": "short explanation"
}
```

## Tool request

```json
{
  "tool": "tool.name",
  "arguments": {},
  "reason": "short reason"
}
```

The exact schema should be tightened during implementation.

---

# 11. Context Management Decision

Do not send the entire historical context to every layer.

Preferred:

```text
Full conversation
       |
       v
short task summary
       |
       v
L1
       |
       v
normalized task
       |
       +--> L2 only when necessary
       |
       +--> L3 only with relevant context
```

This is especially important because previous experiments showed that very large initial contexts can significantly increase local inference latency.

The orchestrator should eventually maintain:

- current task;
- compact conversation summary;
- relevant files;
- relevant tool results;
- explicit user constraints;
- previous failed attempts.

---

# 12. Future RAG Decision

RAG is not part of the first implementation.

When added:

```text
L1
 |
 +--> determine whether retrieval is needed
 |
 v
Retriever
 |
 +--> relevant documents/code
 |
 v
L2 or L3
```

RAG should be invoked conditionally rather than automatically for every request.

---

# 13. Future MCP Decision

MCP is also deferred.

When introduced:

```text
Model
  |
  v
Tool Registry
  |
  +--> native tools
  +--> MCP tools
  +--> local scripts
  +--> APIs
```

The orchestrator should treat MCP as another tool-provider mechanism rather than making the entire architecture dependent on MCP.

---

# 14. Future Bonsai Integration

Bonsai/ternary inference is an independent execution-layer project.

It should eventually sit underneath L3 or another large-model backend:

```text
Pi
 |
 v
Qwen 35B
 |
 v
llama.cpp / Bonsai
 |
 v
AVX-512 / optimized ternary kernels
```

Do not couple Bonsai implementation to the router.

The router only cares that a model backend exposes the required interface.

This preserves the ability to benchmark:

- Q4;
- IQ4_XS;
- Q2;
- ternary/Bonsai;

without changing the agent architecture.

---

# 15. Observability Requirements

Every request should eventually record:

```json
{
  "request_id": "...",
  "timestamp": "...",
  "selected_level": "L1",
  "model": "qwen3.6-0.8b",
  "latency_ms": 0,
  "tokens_in": 0,
  "tokens_out": 0,
  "confidence": 0.0,
  "escalated": false,
  "tool_calls": 0,
  "success": true
}
```

Important metrics:

- L1 latency;
- L2 latency;
- L3 latency;
- escalation rate;
- false escalation rate;
- missed escalation rate;
- tool-call success;
- invalid JSON rate;
- model token usage;
- RAM usage;
- CPU utilization;
- end-to-end latency.

The goal is to eventually answer:

> "How often does L1 correctly avoid L3?"

That is one of the primary success metrics.

---

# 16. Success Criteria

The first production-quality version is successful if:

1. Simple requests normally finish at L1.
2. Medium tool workflows normally finish at L2.
3. Complex coding tasks go directly to L3.
4. L1 does not need the full conversation history.
5. L2 does not receive unnecessary context.
6. L3 receives relevant context and has access to Pi's tools.
7. Invalid tool calls are rejected before execution.
8. Model selection can be changed entirely through configuration.
9. Every escalation is observable.
10. The architecture remains understandable without a large orchestration framework.

---

# 17. Initial Implementation Plan

## Phase 1 — Skeleton

Build:

```text
kiss-agent/
├── orchestrator/
├── models/
├── tools/
├── policy/
├── config/
├── telemetry/
└── tests/
```

Implement:

- configuration loader;
- request object;
- response object;
- routing contract;
- model adapter interface.

---

## Phase 2 — L1

Connect:

```text
Qwen 3.6 0.8B
       |
       v
llama.cpp server
```

Implement:

- classification;
- JSON routing;
- confidence;
- basic escalation.

---

## Phase 3 — L2

Connect:

```text
LFM2.5-8B-A1B
```

Implement:

- tool registry;
- tool selection;
- multi-step execution;
- result verification;
- escalation.

---

## Phase 4 — L3

Connect:

```text
Pi RPC
   |
Qwen 3.6 35B
```

Implement:

- coding tasks;
- repository context;
- filesystem policy;
- shell policy;
- result propagation.

---

## Phase 5 — Evaluation

Create a fixed benchmark suite covering:

- simple questions;
- JSON;
- tool selection;
- negative tool cases;
- argument extraction;
- multi-tool workflows;
- coding requests;
- escalation;
- malicious/destructive requests.

Compare:

```text
L1 only
L1 -> L2
L1 -> L2 -> L3
direct L3
```

Measure end-to-end latency and quality.

---

# 18. Non-Goals

The first version will NOT attempt to:

- build a general-purpose multi-agent framework;
- automatically spawn unlimited agents;
- perform autonomous background tasks;
- give models unrestricted filesystem access;
- use every available local model;
- implement distributed inference;
- implement Bonsai kernels;
- build RAG before routing works;
- add MCP before the basic tool registry works;
- optimize for cloud deployment.

---

# 19. Guiding Principle

The architecture should follow:

```text
        USE THE SMALLEST CAPABLE MODEL
                    |
                    v
             ESCALATE ONLY
             WHEN NECESSARY
                    |
                    v
        USE THE BIG MODEL FOR
        HIGH-VALUE REASONING
```

Or more simply:

> **L1 decides. L2 acts. L3 engineers.**

Where:

- **L1 — Qwen 3.6 0.8B:** decides what kind of work is required.
- **L2 — LFM2.5-8B-A1B:** performs moderate tool-oriented work.
- **L3 — Pi + Qwen 3.6 35B:** performs serious software-engineering and reasoning work.

---

# 20. Continuation Instructions for the Next Chat

When continuing this project, assume the following decisions are already made:

1. The three-level architecture is fixed:
   - L1 = Qwen 3.6 0.8B
   - L2 = LFM2.5-8B-A1B
   - L3 = Pi + Qwen 3.6 35B

2. The architecture must remain KISS.

3. Routing must be configuration-driven.

4. Pi is the L3 coding-agent worker, not something to be rewritten.

5. LLMs are never the security boundary.

6. Tool execution requires external schema/policy validation.

7. Full conversation history should not automatically propagate between layers.

8. RAG and MCP are future extensions, not prerequisites.

9. Bonsai/ternary inference is a future backend optimization and must remain decoupled from routing.

10. The next practical step is to implement **Phase 1 + Phase 2**:
    - repository skeleton;
    - configuration schema;
    - model adapter;
    - Qwen 3.6 0.8B L1 router;
    - strict routing JSON schema;
    - basic escalation logic;
    - benchmark/test harness.

11. Do not re-litigate the model-selection decision unless new benchmark evidence is explicitly introduced.

---

## Final Architecture

```text
                           USER
                            |
                            v
                  +---------------------+
                  | KISS ORCHESTRATOR   |
                  |                     |
                  | policy              |
                  | config              |
                  | routing             |
                  | escalation          |
                  | telemetry           |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  | L1                  |
                  | Qwen 3.6 0.8B       |
                  |                     |
                  | FAST ROUTER         |
                  +----------+----------+
                             |
                  +----------+----------+
                  |                     |
              simple/tool           complex
                  |                     |
                  v                     v
                  L1                    L2
                                        |
                              +---------+---------+
                              |                   |
                          succeeds            difficult
                              |                   |
                              v                   v
                            result               L3
                                                  |
                                        +---------+---------+
                                        |                   |
                                       Pi              Qwen 35B
                                        |                   |
                                  read/edit/bash       reasoning
                                        |                   |
                                        +---------+---------+
                                                  |
                                                  v
                                               result
```

**Architecture slogan:**

> **L1 routes. L2 operates. L3 engineers.**

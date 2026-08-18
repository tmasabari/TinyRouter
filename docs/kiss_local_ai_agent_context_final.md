# KISS Local AI Agent — Requirements & Context

**Project:** KISS Local AI Agent  
**Owner:** Sabarinathan  
**Status:** Post-POC architecture baseline

> This document supersedes the earlier model-specific agent context. The TinyRouter POC is now the source of architectural learning.

## 1. Executive decision

Build a local, configuration-driven AI agent platform with logical capability levels rather than hard-coded models.

```text
USER
  |
  v
+--------------------+
| KISS ORCHESTRATOR  |
| normalize          |
| rules              |
| routing            |
| escalation         |
| policy             |
| telemetry          |
+---------+----------+
          |
          v
   configured worker
     |          |
 can_handle   escalate
     |          |
     v          v
  RESULT     RULE ENGINE
                 |
                 v
             next worker
```

Core principle:

> **Models report capability. The rule engine/orchestrator controls routing.**

The smallest capable worker should normally handle the request, but no model is permanently tied to L1, L2, or L3.

## 2. Model-level abstraction

L1, L2 and L3 are **logical capability levels**, not model names.

Current local deployments are examples and benchmark candidates only:

| Level | Current candidate | Role |
|---|---|---|
| L1 | Qwen 3.6 0.8B / LFM2.5-1.2B candidates | Fast, cheap general worker |
| L2 | LFM2.5-8B-A1B candidate | Medium reasoning/tool worker |
| L3 | Pi + a strong local model candidate | Coding/deep reasoning worker |

These are replaceable. Future models may occupy any level without changing the logical architecture.

**Do not encode model names, versions, quantizations, or inference backends into business logic or requirements.**

## 3. POC learnings incorporated

### 3.1 Model confidence is not a routing authority

Small models produced confidently incorrect answers during testing. Generated confidence is therefore not a correctness guarantee and is removed from the core routing contract.

Optional confidence-like telemetry may exist, but it must not be treated as a security boundary or correctness guarantee.

### 3.2 Models do not select physical destinations

A worker returns only a capability result:

```json
{"status":"can_handle","reason_code":"simple_question","answer":"..."}
```

or:

```json
{"status":"escalate","reason_code":"complex_reasoning","answer":""}
```

The rule engine decides the next logical level.

### 3.3 L1 may answer

L1 is not merely a classifier. If it believes it can complete the task, it may return `can_handle` and its answer is returned.

### 3.4 Escalation is not necessarily sequential

The routing graph may contain:

```text
L1 -> L2
L1 -> L3
L2 -> L3
```

Do not force L1 -> L2 -> L3 when an intermediate worker adds no value.

### 3.5 Explicit user override

Users may request a logical level directly:

```text
@l1 ...
@l2 ...
@l3 ...
```

An explicit override takes precedence over automatic routing and is removed before the target worker receives the request.

## 4. Requirements

### R1 — Configuration-driven workers

Configuration defines logical levels, endpoints/adapters, model identifiers, timeouts, retries, capabilities, enabled state, and fallback behavior.

### R2 — Capability contract

Every model worker implements the same minimal contract:

```text
can_handle | escalate
reason_code
answer/result
```

No worker-specific routing classes.

### R3 — Deterministic routing policy

The rule engine may use simple configurable signals such as keywords, prompt length, task metadata, source level, reason codes, context size, risk, and availability.

Rules are policy, not an attempt to reproduce an LLM.

### R4 — Safety boundary

LLM output is untrusted input. Tool execution requires schema validation and deterministic policy evaluation before execution.

### R5 — Context minimization

Do not propagate the full conversation automatically. Maintain compact task state and pass only relevant context, files, and tool results.

### R6 — Reliability

The system must provide:

- per-worker timeout;
- bounded retries;
- invalid-response handling;
- model-unavailable handling;
- maximum routing hops;
- cycle detection;
- no-valid-route failure;
- graceful shutdown.

### R7 — Observability

Every request/hop has a correlation ID and structured telemetry for routing, model, latency, tokens, escalation, failures, and tool calls.

Logging is asynchronous/non-blocking with configurable ERROR/WARNING/INFO/DEBUG/TRACE levels and clean resource shutdown.

### R8 — Backend independence

The logical architecture must not depend on llama.cpp, a particular quantization, CPU/GPU mode, or model provider.

## 5. User stories

### US-001 — Automatic routing

As a user, I want the system to select the smallest configured worker capable of completing my request.

### US-002 — Explicit level override

As a user, I want to explicitly select L1/L2/L3 when I know which capability I need.

### US-003 — Capability-based escalation

As a system, I want a lower worker to report inability without selecting the next worker itself.

### US-004 — Safe tool execution

As a system, I want all model-generated tool requests validated outside the model.

### US-005 — Minimal context

As a system, I want each worker to receive only the context required for its task.

### US-006 — Observable execution

As an operator, I want to trace every routing hop and model invocation without blocking the request path.

## 6. Agent state

Use a small normalized state:

```text
AgentState
├── request_id
├── user_request
├── task_type
├── constraints
├── summary
├── current_level
├── relevant_files
├── relevant_tool_results
├── reason_code
├── attempt
└── visited_levels
```

Avoid storing or propagating unnecessary model reasoning.

## 7. Tool and policy model

```text
MODEL
  |
  v
structured tool request
  |
  v
schema validation
  |
  v
policy engine
  +--> deny
  +--> confirmation
  +--> execute
```

Policy should support tool allowlists, level permissions, working-directory restrictions, shell restrictions, timeouts, output limits, network permissions, retry limits, and destructive-operation confirmation/deny.

## 8. L3 boundary

Pi or another coding agent is an external worker. The orchestrator supplies task, relevant context, workspace, and policy constraints. It must not reimplement the coding-agent loop.

## 9. Evaluation requirements

Benchmark the hierarchy against a direct strongest-worker baseline.

Measure:

- task success;
- answer correctness;
- routing correctness;
- false escalation;
- missed escalation;
- end-to-end latency;
- TTFT;
- input/output tokens;
- worker invocation count;
- context size;
- CPU/RAM usage;
- tool success/failure;
- timeout/retry behavior.

Include simple, medium, complex, coding, long-context, reasoning-boundary, ambiguous, invalid-output, tool-misuse, destructive, and explicit-override cases.

A router is successful only when it reduces latency/resource usage without materially reducing task success.

## 10. Non-goals

Do not add LangChain/LangGraph, Redis, Kafka, Kubernetes, distributed queues, a vector database, a general multi-agent framework, RAG, MCP, or Bonsai/ternary execution until a concrete requirement justifies them.

RAG, MCP, and alternative inference kernels are extension points, not architectural prerequisites.

## 11. Engineering principles

- **KISS:** prefer the smallest understandable implementation.
- **YAGNI:** do not implement speculative infrastructure.
- **DRY:** one worker contract, one policy boundary, one routing mechanism.
- **POLA:** each component behaves according to its narrow responsibility.

## 12. Definition of done for the agent foundation

- [ ] Logical L1/L2/L3 levels are configurable.
- [ ] Models can be replaced without application-code changes.
- [ ] Capability contract is validated.
- [ ] Rule engine controls escalation.
- [ ] `@lN` overrides work.
- [ ] Hop/cycle protection works.
- [ ] Context is minimized.
- [ ] Tool execution is policy controlled.
- [ ] Async logging and telemetry work.
- [ ] Deterministic tests cover routing and failure paths.
- [ ] Real-model evaluation compares hierarchy with direct strongest-worker execution.

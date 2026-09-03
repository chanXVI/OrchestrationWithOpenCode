# Agent Orchestration Sandbox

## Purpose and delivery contract

This specification defines a Python control plane for accepting a repository coding task, running a bounded multi-agent workflow in an isolated Docker sandbox, and returning a reviewable result. It is a first-release design for `uv`, FastAPI, Typer, SQLite, the OpenAI Agents SDK, and OpenRouter's OpenAI-compatible API.

The caller's checkout is never edited and no run creates a commit. A successful terminal result contains a unified Git diff, changed-file manifest, captured validation report, independent reviewer verdict, and audit metadata. The caller may apply the returned diff separately.

The control plane and sandbox have distinct trust domains:

* The control plane owns credentials, policy, durable state, lifecycle operations, and artifact storage.
* A sandbox is fresh for each run and may inspect or edit only its disposable Git worktree. It receives no Docker socket, host shell, database access, or model credentials.
* Models request tool work through the control plane; the control plane validates every tool request against run policy before dispatching it into the sandbox.

The renderable diagrams are in [agent-orchestration-diagram.md](agent-orchestration-diagram.md), using standard Markdown `mermaid` fences supported by VS Code's Markdown preview.

## Scope and non-goals

The first workflow supports one repository task at a time and returns a patch, rather than merging it. SQLite is the initial persistence backend behind a repository interface; production multi-writer scale, arbitrary interactive terminals, and automatic commits are out of scope. Images, OpenRouter account setup, network proxy implementation, and exact package allowlists are external deployment configuration, but their interfaces are specified below.

## Interfaces

### REST API

`POST /runs` creates a run. The service resolves a local repository reference or a server-configured repository locator, records the request, and begins intake asynchronously.

```json
{
  "repository": {"kind": "local_path", "value": "/srv/repos/example", "ref": "main"},
  "task": "Add a parser for the configuration format and tests.",
  "model_overrides": {
    "planner": "openai/gpt-4.1-mini",
    "implementer": "openai/gpt-4.1"
  },
  "limits": {"cpu": 2.0, "memory_mb": 4096, "pids": 256, "timeout_seconds": 1800}
}
```

`repository.kind` is `local_path` or a configured locator kind. Untrusted URLs are not accepted as arbitrary clone targets in this release. `task` is nonempty, has a service-configured maximum size, and must not request caller-checkout mutation. Model overrides may name only configured role models. Limits are bounded by server policy.

The response is `202 Accepted`:

```json
{"id":"run_01J...","status":"queued","stage":"intake","created_at":"2026-09-03T18:00:00Z"}
```

`GET /runs/{id}` returns the durable run view: `status`, `stage`, timestamps, approval checkpoint (if any), retry count, ordered event summaries, error summary, and result metadata. It does not expose secrets or raw internal paths.

`POST /runs/{id}/approve` and `POST /runs/{id}/reject` each accept `{"approval_id":"appr_...","note":"optional"}`. They are idempotent for the same resolved decision. Only the currently pending approval can be resolved; a stale or mismatched request returns `409`. A rejection terminates the run as `rejected` and triggers cleanup.

`GET /runs/{id}/artifacts` returns `409` until a terminal result has been packaged. For completed or failed runs it returns signed/downloadable artifact references plus metadata:

```json
{
  "diff": {"uri":"artifact://run_.../patch.diff", "sha256":"..."},
  "changed_files": {"uri":"artifact://run_.../changed-files.json"},
  "validation": {"uri":"artifact://run_.../validation.json"},
  "review": {"uri":"artifact://run_.../review.json"},
  "result": {"uri":"artifact://run_.../result.json"}
}
```

Use standard error envelopes: `400` malformed payload, `404` unknown run, `409` invalid state transition, `422` policy-invalid request, and `503` unavailable executor/model provider. Event and artifact routes must enforce the service's caller authorization policy.

### CLI

The Typer CLI is an HTTP client, keeping authorization and policy decisions in the service:

```text
orchestrator run create PATH --task TEXT [--ref REF] [--model ROLE=ID] [--cpu N] [--memory-mb N] [--timeout-seconds N]
orchestrator run status RUN_ID
orchestrator run approve RUN_ID APPROVAL_ID [--note TEXT]
orchestrator run reject RUN_ID APPROVAL_ID [--note TEXT]
orchestrator run artifacts RUN_ID [--output DIRECTORY]
```

`artifacts --output` downloads only files enumerated by the service response and verifies their SHA-256 values. The CLI never invokes Docker or operates on the submitted checkout.

## Configuration and model access

Dependencies are managed by `uv`; the service package exposes `api`, `cli`, `orchestration`, `storage`, `sandbox`, `policy`, and `artifacts` modules. Required configuration is server-owned:

```toml
[models]
planner = "openai/gpt-4.1-mini"
implementer = "openai/gpt-4.1"
reviewer = "openai/gpt-4.1"
summarizer = "openai/gpt-4.1-mini"

[sandbox]
image = "registry.example/agent-sandbox@sha256:..."
network_mode = "egress-proxy"
allowed_hosts = ["openrouter.ai", "pypi.org", "files.pythonhosted.org"]
max_cpu = 4.0
max_memory_mb = 8192
max_timeout_seconds = 3600
```

`OPENROUTER_API_KEY` remains only in the control-plane secret store. The OpenAI Agents SDK client uses an OpenAI-compatible `base_url` set to OpenRouter and selects the configured model for the role. The model-facing tool layer is a control-plane service: it executes sandbox actions and sends only sanitized result data back to the agent. No API key, database URL, host path, or raw environment dump is included in prompts, tool schemas, container mounts, or artifacts.

Role overrides are allowlist validated and recorded in immutable run configuration. Changing default configuration affects new runs only.

## Durable state and storage

Define a `RunRepository` protocol so SQLite can later be replaced with Postgres. SQLite runs with foreign keys enabled, WAL mode, migration-managed schema, and short transactional state changes. Store artifact payloads in an artifact backend; SQLite holds immutable references, checksums, sizes, and content types.

| Table | Essential data |
| --- | --- |
| `runs` | ID, request JSON, snapshot/ref identity, model map, limits, status, stage, timestamps, retry count, terminal error/result metadata |
| `checkpoints` | run ID, monotonic sequence, LangGraph-compatible state JSON, graph version, created time |
| `approvals` | ID, run ID, policy findings JSON, proposed actions digest, status, resolver/note, timestamps |
| `events` | run ID, sequence, timestamp, type, stage, sanitized payload JSON; append-only |
| `agent_outputs` | run ID, role, attempt, prompt digest, output artifact reference, status, timing/model metadata |
| `artifacts` | run ID, logical name, URI, SHA-256, size, media type, created time |

All transitions update `runs`, append an event, and checkpoint graph state in one transaction. Worker startup claims nonterminal, non-waiting runs using a lease; expired leases are recovered by reloading the latest checkpoint. A run with a `waiting_approval` checkpoint is never resumed until a valid approval decision is recorded. Checkpoint state is JSON-serializable and includes only references to large output, never unbounded transcripts.

Shared graph state includes: run ID; immutable task/request; repository snapshot and disposable worktree identity; plan and requested validation commands; policy findings and approval state; sanitized tool transcript references; diff and changed-file references; validation results; reviewer decision and repair instructions; retry count; and terminal result/error.

## Workflow

The orchestrator is a LangGraph-compatible persisted state graph. Agent calls use the OpenAI Agents SDK and structured output schemas. Every stage writes an event and checkpoint. Terminal transitions package available evidence before cleanup.

1. **Intake** validates the API request and repository allowlist, resolves the immutable source ref, and asks the sandbox manager to create a disposable worktree from that snapshot. It rejects dirty source checkout use or snapshots an allowed repository via an implementation-defined read-only mechanism. The mounted worktree is never the caller's checkout.
2. **Planner** uses read-only repository inspection tools and returns a structured, executable plan: files likely affected, ordered edits, assumptions, and exact validation commands. It cannot edit or execute arbitrary commands.
3. **Risk evaluator** compares the plan and requested commands with policy. Findings for protected paths, destructive commands, credential-like data, privilege escalation, or unapproved network need create a durable approval. Low-risk plans proceed automatically; risk-gated plans enter `waiting_approval`.
4. **Implementer** receives the approved plan and uses only scoped sandbox tools. It may inspect the worktree, edit files under the worktree root, execute approved commands, view `git status`/`git diff`, and collect artifacts. Each edit and command is path/command checked by the mediator.
5. **Validator** runs only the approved checks under the same sandbox limits. It stores command, sanitized stdout/stderr, exit code, duration, and timeout/resource-limit classification. A validation failure goes to review with the evidence; it is not silently retried.
6. **Independent reviewer** receives task, plan, changed-file manifest, diff, and validation evidence. It must output `approve`, `reject`, or one bounded `repair` request. The reviewer has no edit tools. A repair returns to implementer only if `retry_count < 1`, increments it transactionally, and may not expand beyond the originally approved scope. Otherwise the run is terminal `failed_review`.
7. **Finalizer** generates `patch.diff`, `changed-files.json`, `validation.json`, `review.json`, and `result.json`, records checksums, marks the run terminal, and invokes cleanup in a `finally` path. Cleanup outcome is separately audited; a cleanup failure is surfaced without discarding the result.

`status` is one of `queued`, `running`, `waiting_approval`, `completed`, `rejected`, `failed_validation`, `failed_review`, `failed_policy`, `failed_executor`, `failed_model`, or `cancelled`. `stage` identifies the current graph node, including `intake`, `planning`, `risk_evaluation`, `implementation`, `validation`, `review`, `finalization`, and `cleanup`.

## Agents and tool contracts

| Role | Input and required output | Granted tools |
| --- | --- | --- |
| Planner | Task + sanitized repo inventory; executable plan and validation commands | `repo_list`, `repo_read`, `repo_search` (read-only) |
| Implementer | Approved plan + prior evidence; scoped changes and tool calls | `repo_list`, `repo_read`, `repo_search`, `edit_file`, `run_approved`, `git_status`, `git_diff`, `collect_artifact` |
| Reviewer | Task, plan, diff, changed files, validation evidence; verdict schema | none |
| Summarizer/finalizer | Structured evidence; result summary schema | artifact reads only |

`edit_file(path, patch)` accepts a relative normalized path, rejects symlinks escaping the worktree, rejects protected paths without explicit approval, and applies a patch atomically within the mounted root. `run_approved(command_id, arguments)` resolves only to a command pre-approved by policy; no shell string, redirection, chaining, substitution, or arbitrary environment is accepted. It uses an argv array, fixed working directory, minimal environment, output/time caps, and a per-command timeout. `repo_read`/`repo_search` cap bytes and redact configured secret patterns. `collect_artifact` can only collect fixed logical result types from the output mount.

The mediator records request and result digests, duration, exit classification, and policy decision. It rejects shell escape routes, absolute host paths, device files, mounts, Docker APIs, and inherited ambient credentials.

## Risk and approval policy

Policy is deterministic and versioned per run. It evaluates both planner output and mediated tool requests. At minimum, require approval for:

* paths matching configured protected patterns (for example `.github/workflows/**`, deployment manifests, ownership/security controls, or `.env*`);
* filesystem-destructive operations, repository history rewrites, package lock regeneration outside allowed task scope, or commands classified as destructive;
* credential discovery, modification, or output patterns;
* privilege changes, setuid/capability operations, service control, and container/mount requests;
* any egress destination outside the configured allowlist, including new dependency/source hosts.

The approval record displays the matched rules, affected paths/commands, plan digest, policy version, and expiration. Approval applies only to that digest and run; any material plan change invalidates it and creates a new checkpoint. Rejection cannot be overridden by an agent.

## Docker sandbox boundary

For each run, the sandbox manager makes a new `git worktree` (or equivalent copy) from the resolved immutable snapshot, creates a fresh output directory, starts one container, and later removes the worktree/container. The input mount is the disposable worktree read-write only because implementation needs it; it is not a mount of the caller checkout. Output is a separate write-only-to-agent/result-readable-to-control-plane directory. No other host directories are mounted.

Container requirements:

* pinned, read-only base image; non-root UID/GID; read-only root filesystem with explicit writable temp/worktree/output mounts;
* `cap-drop=ALL`, `no-new-privileges`, restrictive seccomp/AppArmor (or equivalent), no Docker socket, no host PID/network/IPC namespaces, and no device access beyond required defaults;
* enforced CPU, memory, PID, disk/output, and wall-clock limits; a control-plane watchdog records timeout/OOM/PID failures distinctly;
* default-deny egress. When dependency installation is required, use a policy-controlled proxy that resolves and allows only configured hosts. Direct network modes and arbitrary DNS are unavailable;
* minimal fixed environment, no inherited process environment, and no secret files or credentials mounted. Model invocation occurs at the control plane, not inside the container.

The implementation should launch Docker with an explicit argv invocation and fixed options, never model-provided arguments. A startup probe records container ID only in restricted audit metadata. The finalizer always attempts `stop/remove` and worktree removal; cleanup is idempotent and safe after process restart.

## Observability and artifacts

Events are append-only and sanitized before persistence. Preserve stage started/completed/failed events, policy decisions, approval resolutions, model/provider error categories, tool request/result digests, validation outcomes, artifact checksums, and cleanup outcome. Do not persist API keys, authorization headers, full secret matches, or uncontrolled command environment. Redaction happens before logs, events, prompts, and artifact packaging.

`validation.json` holds an array of check results with approved command ID/argv, exit code, duration, stdout/stderr artifact references or truncation metadata, and `passed`. `review.json` contains reviewer model metadata, verdict, rationale, evidence references, and bounded repair instructions. `result.json` links every artifact and records the source snapshot, policy/config versions, terminal status, and timestamps.

## Test and acceptance plan

Run tests under `uv` (for example, `uv run pytest`) with unit tests isolated from real Docker/OpenRouter by interfaces and fakes.

* API and CLI: creation, validation errors, status lookup, approval/rejection and idempotency, artifacts, authorization behavior, and restart/resume from SQLite checkpoints.
* Orchestration: mocked OpenRouter/Agents SDK normal completion; reviewer repair then approval; failed validation; rejected approval; retry exhaustion; malformed model output; model and tool failures.
* Storage: transactional event/checkpoint transitions, expired leases, waiting-approval non-resumption, migration compatibility, artifact checksum verification.
* Docker integration: isolated worktree does not modify source checkout; container and worktree cleanup; resource-limit reporting; blocked non-allowlisted egress; no credentials inside container; symlink/path escape rejection.
* Acceptance: run a small repository task; assert a nonempty diff, passing captured tests, independent reviewer approval, terminal `completed`, and a downloadable bundle whose checksums match.

## Implementation milestones

1. Scaffold the `uv` package, configuration parser, schemas, SQLite repository, and FastAPI/Typer interfaces with fake executor/model implementations.
2. Implement persisted graph transitions, approval endpoints, artifact packaging, restart recovery, and interface-level tests.
3. Add OpenAI Agents SDK/OpenRouter adapter and structured role schemas; retain deterministic fakes for tests.
4. Add Docker worktree manager, command mediator, egress proxy integration, and security-focused integration tests.
5. Exercise the acceptance scenario in a controlled repository and document deployed image digest, policy version, and allowed hosts.

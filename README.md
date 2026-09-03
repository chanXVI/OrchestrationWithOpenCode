# Agent Orchestration Sandbox

A first-release design for a Python service that accepts repository coding tasks, runs a bounded multi-agent workflow in an isolated Docker sandbox, and returns a reviewable patch instead of changing the caller's checkout.

## What it is designed to provide

- A FastAPI control plane and Typer CLI for creating, tracking, approving, and retrieving runs.
- A persisted workflow for intake, planning, risk evaluation, implementation, validation, review, finalization, and cleanup.
- One disposable Git worktree and least-privilege container per run.
- Durable run state in SQLite and evidence artifacts including a diff, changed-file manifest, validation report, reviewer verdict, and audit metadata.
- Policy-gated tools, approval checkpoints, default-deny network access, and server-held model credentials.

The caller's checkout is never edited and runs do not create commits. The returned patch can be reviewed and applied separately.

## Documentation

The complete design, API and CLI contracts, safety model, persistence strategy, and implementation milestones are in [the orchestration specification](docs/agent-orchestration.md).

Renderable component, lifecycle, and security-boundary diagrams are in [the Mermaid diagrams](docs/agent-orchestration-diagram.md). Open that file with a Markdown preview that supports Mermaid (for example, VS Code's Markdown preview).

## Planned stack

Python, `uv`, FastAPI, Typer, SQLite, the OpenAI Agents SDK, OpenRouter's OpenAI-compatible API, and Docker.

## Project status

This repository currently contains the architecture and delivery specification. Implementation is planned in the milestones documented above.

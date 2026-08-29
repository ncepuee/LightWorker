# Codex native subagent bridge

LightWorker v0.6.0 separates durable task control from native Codex execution.
It does **not** replace native subagents with `codex exec`.

## Protocol

1. Submit a task with `execution_channel: "native_subagent"`.
2. The local scheduler validates routing and moves it to `awaiting_native_dispatch`.
3. The active Codex parent calls `claim_native_dispatches` with a stable `host_id`.
4. For every returned ticket, the parent calls its native `spawn_agent` tool using the ticket objective, model, reasoning effort, workspace, and safety limits.
5. Immediately call `native_subagent_started` with the returned thread ID.
6. Wait using Codex's native thread wait control. Send `native_subagent_event` progress events while the child is still running.
7. Call `native_subagent_completed` with a concise structured result or terminal error.

The ticket lease prevents another host from spawning the same task. If a host dies before acknowledging a child, an expired lease is returned to `awaiting_native_dispatch` for a later host to claim.

## Cancellation

Cancelling a native task in LightWorker records the intent immediately. If the task has a `native_thread_id`, the parent Codex host must also call its native interrupt control for that thread; LightWorker cannot reach into the desktop session to terminate it directly.

## Result contract

The terminal result should include a short `summary`, files changed, verification performed, and any blocker. The full subagent transcript remains in the Codex thread; LightWorker stores the thread identifier and compact audit events only.

# Kube-Sentinel Backend Milestone Tracker

## Scope Lock
- No UI or CLI frontend implementation work before Milestones `M1` to `M3` are complete and accepted.
- Validation is raw terminal only for these milestones.
- First tool scope is fixed to Kubernetes **Pod** manifest generation and execution.

## Status Legend
- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

---

## Milestone ID: M0
**Title:** Scope Lock and Execution Criteria  
**Status:** `NOT_STARTED`

### Tasks
1. Freeze project scope to backend-only until `M1` to `M3` pass.
2. Freeze validation mode to raw terminal interaction.
3. Confirm first tool target is Pod YAML generation and optional apply.
4. Define acceptance gates for each milestone before implementation.

### DoD
1. Scope and sequence are documented and agreed.
2. All milestone gates are explicit and unambiguous.
3. No active tasks reference Textual UI implementation.

### Tests
1. Checklist review against roadmap document.
2. Verify no new UI/frontend files are introduced during `M1` to `M3`.

### Evidence
1. Written approval note in project tracking doc or chat record.
2. Link to this tracker and approved roadmap.

---

## Milestone ID: M1
**Title:** Chat Functionality 100% In-Memory  
**Status:** `NOT_STARTED`

### Tasks
1. Finalize chat service contract (`stream`, `clear_history`, optional `get_history`).
2. Ensure deterministic system prompt initialization and reset behavior.
3. Enforce turn lifecycle: append user input, stream response, persist assistant output.
4. Implement rollback behavior for failed stream attempts.
5. Fix streaming update path to mutate the same content field used for rendering/output.
6. Add explicit error handling categories (configuration, provider, stream interruption).
7. Add terminal REPL harness for raw chat interaction.
8. Add unit tests for history initialization, ordering, reset, and failure rollback.
9. Add streaming tests for token aggregation and stream finalization.

### DoD
1. In-memory multi-turn chat works reliably in terminal.
2. History consistency is preserved across success and failure paths.
3. Reset behavior fully clears active context and re-initializes system prompt.
4. All planned `M1` tests pass locally.

### Tests
1. Unit: chat history lifecycle and ordering integrity.
2. Unit: failure rollback does not corrupt history.
3. Unit: streamed token aggregation equals final assistant message.
4. Manual terminal: multi-turn context retention.
5. Manual terminal: reset/new chat clears context.
6. Manual terminal: interrupted/failed stream recovers correctly.

### Evidence
1. Test run output summary (`passed/failed`) for `M1` test set.
2. Terminal transcript snippets for manual checks.
3. Short defect log for any known non-blocking issues.

---

## Milestone ID: M2
**Title:** Chat History Persistence (Database)  
**Status:** `NOT_STARTED`

### Tasks
1. Select persistence backend for first implementation (recommended: SQLite).
2. Define storage abstraction (`ChatHistoryStore`) with in-memory and DB implementations.
3. Create schema for `conversations` and `messages`.
4. Implement repository operations: create, append, load, list, clear/delete.
5. Integrate persistence with chat service via config switch.
6. Preserve in-memory mode as fallback and for fast tests.
7. Implement startup restore behavior (resume vs new conversation policy).
8. Define reset semantics for persistent sessions.
9. Add persistence tests for restart recovery and message ordering.
10. Add error-path handling tests for partial failures.

### DoD
1. Chat history survives process restart.
2. Message ordering remains correct and deterministic.
3. Reset behavior is consistent between in-memory and persisted modes.
4. All planned `M2` tests pass locally.

### Tests
1. Unit: repository CRUD and ordering.
2. Integration: save conversation, restart process, reload conversation.
3. Integration: multiple conversations remain isolated.
4. Integration: reset action updates persistent state correctly.
5. Failure-path: partial write or DB exception handling.

### Evidence
1. DB schema snapshot or migration artifact.
2. Test output summary for persistence test suite.
3. Terminal proof of restart-and-restore workflow.

---

## Milestone ID: M3
**Title:** First Tool - Pod YAML Writer and Executor  
**Status:** `NOT_STARTED`

### Tasks
1. Finalize tool input contract (`name`, `image`, `namespace`, optional command/args/env/resources, `output_path`, `apply` flag).
2. Finalize tool output contract (file path, summary, execution status, stdout/stderr).
3. Implement deterministic Pod manifest generator (`apiVersion: v1`, `kind: Pod`).
4. Implement strict input validation (name, image required, namespace defaults, resource shape).
5. Implement safe file-write and overwrite policy.
6. Implement execution modes:
7. Generate-only.
8. Dry-run apply.
9. Real apply with explicit confirmation gate.
10. Add tests for YAML generation snapshots.
11. Add tests for validation failures and command invocation behavior.
12. Wire tool usage into raw terminal workflow (non-UI).
13. Validate with manual kubectl checks in test namespace.

### DoD
1. Tool reliably generates valid Pod YAML from terminal flow.
2. Dry-run and apply flows behave predictably with clear error reporting.
3. Input validation blocks malformed manifests before write/apply.
4. All planned `M3` tests pass locally.

### Tests
1. Unit: manifest generation snapshot tests.
2. Unit: validation test matrix for required/optional fields.
3. Unit/integration: command invocation behavior (mocked and/or sandboxed).
4. Manual terminal: generate manifest file.
5. Manual terminal: `kubectl apply --dry-run=client`.
6. Manual terminal: real apply in non-production namespace.
7. Manual terminal: verify Pod state (`get`, `describe`, optional logs).

### Evidence
1. Generated sample Pod YAML artifact path(s).
2. Test output summary for tool suite.
3. Terminal command transcripts for dry-run and real apply.
4. Verification output showing created Pod status.

---

## Milestone ID: M4
**Title:** Pause and Reassessment Gate  
**Status:** `NOT_STARTED`

### Tasks
1. Produce implementation summary for `M1` to `M3`.
2. List known risks, defects, and technical debt.
3. Propose next-step options (more tools, hardening, or frontend phase).
4. Stop for explicit go/no-go decision before new scope.

### DoD
1. A complete phase report exists with objective pass/fail status.
2. Risks and unresolved items are documented with severity.
3. No new scope begins without explicit approval.

### Tests
1. Milestone checklist audit for `M1`, `M2`, and `M3`.
2. Traceability check: each DoD item has linked evidence.

### Evidence
1. Final phase report document.
2. Linked test summaries and terminal validation outputs.
3. Explicit approval record for the next phase.

---

## Traceability Matrix
| Milestone ID | Depends On | Blocks | Exit Gate |
|---|---|---|---|
| M0 | None | M1, M2, M3, M4 | Scope and acceptance criteria approved |
| M1 | M0 | M2, M3, M4 | In-memory chat fully stable and tested |
| M2 | M1 | M3, M4 | Persistence stable across restart and reset |
| M3 | M1, M2 | M4 | Pod tool generate/dry-run/apply validated |
| M4 | M1, M2, M3 | Frontend phase | Explicit go/no-go decision |


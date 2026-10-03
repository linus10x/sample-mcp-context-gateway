# SAMPLE: MCP context gateway with approval controls

> **Illustrative sample on synthetic data by Kunjar Bhaduri, Bhaduri Advisory. Synthetic accounts and deliberately fake tokens only. Built by AI coding tools under my direction. No client relationship, real system connection or money movement. Revised October 2, 2026 (America/Chicago).**

An agent needs a controlled path from account context to an action. This server demonstrates tenant boundaries, tool scopes, reviewable approvals, execution-time checks and an audit record that commits with local state. It supports the [SnapLogic Applied AI Architect mandate](https://jobs.lever.co/snaplogic/3d408fe5-5fbb-4402-9c36-54a2bf2b9b59) and CRM/AI work. The scoring harness is the separate Engineering Analytics CTO sample.

## Run and inspect

Python 3.10+, standard library only for the main demo and tests. From this repository:

```bash
python3 demo.py
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

The demo checks 19 expectations and exits 0 only if all pass. Strict wire parsing rejects non-JSON constants, overflowing floating-point numbers and duplicate object members before dispatch; invalid request IDs produce a valid error with null ID. Tool `_meta`, when supplied, must be an object. The tests cover validation, scopes, tenant isolation, expiry/replay, stale quote/contract checks, concurrent approval, audit failure rollback and anchored tail verification. See [VERIFICATION.md](VERIFICATION.md) for actual results. CI repeats these commands; a workflow file does not establish a hosted CI pass.

Optional experiment: `uv run --with mcp python interop/sdk_client_check.py`, using the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk). The SDK experiment passed with `mcp 2.3.0` and Python 3.12.14 (runs on October 2 and 3, 2026, CT): it initialized the server, listed all seven tools and rejected a cross-tenant read. Docker remains unbuilt/unverified. Record the SDK version for future runs. The server implements a stdio subset with protocol `2025-06-18`, not all MCP methods or production HTTP transport.

## Seven tools

| Tool | Scope | Behavior |
|---|---|---|
| `search_accounts`, `get_account`, `list_pending` | `crm.read` | Own tenant only; foreign objects look missing. Pending actions expose parameters, expected state and expiry for review. |
| `set_lead_tier` | `crm.write` | Always pending; approval requires the prior tier still to match. |
| `quote_price` | `quotes.write` | Through 10% discount: direct quote; above 10% through 20%: pending; negative or above 20%: denied. |
| `request_deposit` | `payments.request` | Signed contract/current quote required. Cumulative deposit intent for the account, including the proposed amount, must fit within 50% of the current quote. Always pending. |
| `approve_action` | `actions.approve` | Same tenant, different principal; five-minute expiry. Rechecks quote/contract prerequisites and consumes the action. A stale/expired approval is denied and removed. |

Thresholds and expiry are invented example policies. Money uses integer cents. Numeric inputs must be finite, at most two decimal places and within an absolute sample limit of one million. Zero/negative deposit amounts are denied. `APPROVED_AND_APPLIED` means applied to local synthetic state, never a real payment.

The token table assigns approval scope to a synthetic human identity. It demonstrates separation of principals, not verified human identity. A real IdP must enforce human approver groups and prevent agent identities acquiring that privilege.

## Atomic state and audit

`GATEWAY_STATE` selects SQLite (default `state.sqlite3`). Each tool call uses `BEGIN IMMEDIATE`. State and the hash-chained audit event commit together; insert/commit failure rolls back local state and yields no success result. Local concurrent writers serialize. The existing chain is checked before each call. Full-state JSON storage and full-chain scanning are intentionally small-sample choices, not a high-volume design.

Successful, denied, missing-record and argument-error calls are audited when the transaction can commit. Malformed JSON, other protocol methods and requests while storage is unusable are not committed tool events. Raw argument values are omitted to avoid recording customer notes. Relevant action IDs are logged. Production needs an approved object/version/redaction policy.

Offline snapshot export:

```bash
GATEWAY_STATE=state.sqlite3 python3 -c "from gateway import store; print(store.export('audit.jsonl'))"
```

The returned `{count, hash}` is an anchor. `audit.verify(path)` detects edits and internal chain gaps. **A valid prefix cannot reveal tail deletion.** `audit.verify(path, anchor)` also detects truncation if that anchor was separately retained and trusted. A database administrator can rewrite everything and recompute hashes. External anchoring/WORM storage is not implemented. Export failure does not undo previously committed actions.

This replaces the old two-file JSON state/audit design. Old JSON state is not migrated; do not pass it as the SQLite path. `GATEWAY_AUDIT` is no longer a runtime setting.

## Production boundary

Real work adds validated IdP tokens, transport/session lifecycle, provider adapters, idempotency/outbox processing, authenticated webhooks, reconciliation, database access controls/backups, external audit anchors and security/load tests. SQLite cannot atomically commit a remote CRM write or payment. The [runbook](DEPLOYMENT_RUNBOOK.md) identifies customer-environment acceptance work.

Publication requires owner approval. This synthetic demonstration supports an implementation discussion; it does not establish production delivery history or certify security.

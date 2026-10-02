# SAMPLE: MCP context gateway with scoped access, human approval and an audit trail

> **Sample / illustrative work by Kunjar Bhaduri (Bhaduri Advisory). Synthetic data only. Not a client deliverable, not production software, and not connected to any real system or company.** Built October 2, 2026, by AI coding tools under my direction; the runs below were done that day.

## Which bids it answers
Written as a work sample for public postings that ask for MCP / AI-agent integration with enterprise controls: an applied AI architect contract for an enterprise agent platform (context layer over MCP, SSO/OAuth, firewalled deployment) and an AI-native sales platform build on top of an existing CRM (guardrails before pricing, contracts and payments). **Illustrative sample on synthetic data. No client relationship.**

## The problem it shows
When an AI agent is connected to business systems through MCP, the hard part is rarely the tool call itself. It's making the connection safe to leave running: the agent should see only its own tenant's data, hold only the scopes it needs, never change records or move money without a person approving, and leave a record someone else can check.

This sample is a small MCP server (JSON-RPC 2.0 over stdio, Python standard library only) in front of a synthetic sales CRM. It exposes seven tools:

| Tool | Scope needed | What the policy does |
|---|---|---|
| `search_accounts`, `get_account`, `list_pending` | `crm.read` | Reads only the caller's tenant. Another tenant's record looks exactly like a missing one (no existence leak). |
| `set_lead_tier` | `crm.write` | Never writes directly. Returns `PENDING_APPROVAL` with an action id. |
| `quote_price` | `quotes.write` | Discount up to 10%: allowed. Over 10% to 20%: needs human approval. Over 20%: denied. |
| `request_deposit` | `payments.request` | Denied unless the contract is signed, an approved quote exists and the amount is at most 50% of it. Even then it only becomes `PENDING_APPROVAL`. |
| `approve_action` | `actions.approve` | A human approves. The approver must be a different principal from the requester, and in the same tenant. |

Every `tools/call` is appended to a hash-chained JSON Lines audit log. Editing or deleting a record breaks the chain and `audit.verify()` reports the first bad line.

Other behaviour: unknown or extra arguments are rejected (JSON-RPC `-32602`), tool schemas set `additionalProperties: false`, a policy refusal is a normal tool result (`isError: false`) with named checks, malformed JSON gets `-32700`, and any unexpected exception becomes `-32603` with no stack trace and never an ALLOW. The server refuses to start without a known bearer token (exit 3).

## Run it (about 2 minutes, Python 3.10+)
```bash
python3 demo.py                              # 19 scripted expectations; exit 0 only if all hold
python3 -m unittest discover -s tests -v     # 13 tests
uv run --with mcp python interop/sdk_client_check.py   # optional: drives it with the official MCP Python SDK client
```

## Test runs (Oct 2, 2026, Linux, Python 3.13.5)
- `demo.py`: 19/19 expectations held, exit 0.
- Unit tests: 13 passed.
- Interop: the official MCP Python SDK client (`mcp` 2.3.0) initialized the server (protocol `2025-06-18`), listed the 7 tools, and got `NOT_FOUND` for a cross-tenant read.
- The Dockerfile was **not** built or run.

## Limits (read these before relying on any of it)
- **Synthetic data and fake tokens.** The token table stands in for an identity provider. A real deployment would use the MCP Streamable HTTP transport with OAuth 2.1 access tokens validated against the customer's IdP (issuer, audience, expiry, JWKS rotation), which this sample does not implement.
- **One principal per stdio session.** No concurrency control on the JSON state file; a real system uses a database with transactions.
- **The audit log is tamper-evident, not tamper-proof.** Anyone who can rewrite the whole file can recompute the chain. Anchor the head hash outside the system in production.
- **`request_deposit` only records intent.** No payment provider is called.
- Thresholds (10%, 20%, 50%) are illustrative, not recommendations.
- No load, security or penetration testing was done. No certification or compliance claim of any kind.

## Where it lives
github.com/linus10x/sample-mcp-context-gateway, made public after an accuracy review.

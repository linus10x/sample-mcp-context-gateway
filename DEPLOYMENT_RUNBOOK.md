# SAMPLE runbook: putting an MCP gateway into a customer's firewalled environment

> Sample / illustrative. Written for the synthetic gateway in this folder. It describes the checks I would run; it is not a record of any real deployment.

## Before the first call with the customer's engineers
1. **Network path.** Where will the gateway run (customer VPC, on-prem Docker host, or SaaS)? List every outbound destination it needs (model API, IdP, the systems it reads). Get the egress allowlist approved in writing before day one; this is the usual pilot blocker.
2. **Identity.** Which IdP (Entra ID, Okta, Google)? Agree the OAuth 2.1 flow, token audience, scopes per tool, and token lifetime. Decide who may hold an approval scope; it should be a named group, never the agent's service identity.
3. **Data boundary.** Which tenants, objects and fields the agent may read. Default deny for anything not listed. Decide what must never leave the network (for example, free-text notes).
4. **Write and money actions.** List them. Each one gets a human approval step and a named approver group. Agree thresholds with the business owner, not the engineers.

## Deploy
5. Run as a non-root user with a read-only filesystem except the state and audit paths.
6. Secrets come from the customer's vault at run time, never baked into the image.
7. Ship the audit log to the customer's logging system and anchor the head hash daily.
8. Health check: `ping` plus a `tools/list` with a read-only token.

## Prove it before go-live (acceptance tests)
9. Read-only token cannot write (expect DENY with the scope check named).
10. Cross-tenant read returns NOT_FOUND, not an error that reveals existence.
11. Agent cannot approve its own action; approver must differ from requester.
12. Over-limit discount or deposit is denied with the named check.
13. Extra or malformed arguments are rejected.
14. Edit one audit record in a copy of the log and confirm verification fails at that line.

## Hand-off
15. One-page runbook for the customer's on-call team: start, stop, rotate tokens, read the audit log, what each decision code means.
16. A short list of what was deliberately left out of the pilot and why.

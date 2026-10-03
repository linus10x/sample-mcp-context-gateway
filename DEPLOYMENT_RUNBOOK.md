# SAMPLE: customer-environment acceptance runbook

> Fictional deployment plan, not a completed installation. Kunjar Bhaduri, Bhaduri Advisory, with AI drafting assistance under my direction. Runnable code uses synthetic data and fake identity tokens.

## Agree the boundary

Agree the business outcome, system scope and acceptance owner. Map VPC/on-prem hosting, model/IdP/CRM destinations, proxy/TLS requirements, DNS, the egress allowlist and prohibited outbound data. Obtain customer network approval before committing to a deployment date.

Choose real transport and OAuth/IdP authentication. Validate issuer, audience, expiry, key rotation and least-privilege scopes against the customer's IdP. Approval rights belong to an approved human group. The sample token table is not that implementation. Define field ownership, permitted reads/writes, commercial thresholds, expiry, contract/quote versions and cumulative payment limits. Customer/retrieved text is untrusted input, never authority to expand tools.

## Build and deploy

Use reviewed dependencies/images, runtime secrets, a non-root process, scoped storage access and persistent backups. The Dockerfile is an unverified sketch. For this sample, persist the SQLite path and journal files; do not use the obsolete two-file audit scheme. For production, select a transactional store suited to volume and availability requirements.

Remote changes require durable intents/outbox processing, provider idempotency and reconciliation. Log object/action/version IDs under an approved redaction policy. Export to an independent logging system and retain trusted external anchors. Define health/queue/policy/transaction-failure alerts, rollback, recovery and credential rotation.

## Acceptance before real actions

| Exercise | Evidence required |
|---|---|
| Identity/privilege | Invalid/expired tokens fail; unauthorized identity cannot read/write/approve |
| Tenant boundary | Foreign records/actions look missing; no cross-tenant data or error leakage |
| Human review | Exact action/version inspectable; requester cannot approve |
| Stale state/expiry | Quote/contract/tier change and expiry block stale execution |
| Money/retries | Concurrent limits hold; repeated callback/action cannot duplicate external charge |
| Storage/audit failure | Injected failure commits no local action; remote recovery independently reconciles |
| Audit boundary | Middle edit fails; tail deletion fails against independently stored trusted anchor |
| Prompt injection | Untrusted text cannot bypass tool, approval, suppression or tenant policy |
| Recovery | Isolated restore and rollback meet approved targets, including usable application |
| Network | Approved firewall/proxy/IdP paths exercised in actual customer environment |

Keep sandbox and controlled live checks distinct. Customer accepts the tested scope with open risks recorded. Handoff includes owners, thresholds, runbooks, model/prompt configuration, dependency versions, stop switches, recovery evidence and rollback decisions. No exercise in this document is claimed complete.

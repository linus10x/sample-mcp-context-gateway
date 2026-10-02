"""SAMPLE MCP server (JSON-RPC 2.0 over stdio, Python standard library only).

One stdio session = one principal, identified by the bearer token in MCP_BEARER.
Shows: scope checks per tool, tenant isolation, strict argument validation, human approval
(separation of duties) before any write or money movement, and a hash-chained audit log.
Synthetic data only. See README.md for limits."""
import copy, json, os, sys, uuid

from . import audit, data, policy

PROTOCOL_VERSION = "2025-06-18"
TIERS = {"A", "B", "C"}

TOOLS = {
    "search_accounts": {
        "description": "Search the caller's tenant for accounts whose name contains the query.",
        "args": {"query": (str, True), "limit": (int, False)},
    },
    "get_account": {
        "description": "Return one account in the caller's tenant.",
        "args": {"account_id": (str, True)},
    },
    "set_lead_tier": {
        "description": "Propose a lead-tier change. Never applied until a human approves it.",
        "args": {"account_id": (str, True), "tier": (str, True), "reason": (str, True)},
    },
    "quote_price": {
        "description": "Quote a plan with a discount. Small discounts pass; larger ones need approval; large ones are denied.",
        "args": {"account_id": (str, True), "plan": (str, True), "discount_pct": (float, True)},
    },
    "request_deposit": {
        "description": "Request a deposit. Requires a signed contract, an approved quote, and human approval.",
        "args": {"account_id": (str, True), "amount": (float, True)},
    },
    "list_pending": {
        "description": "List actions in the caller's tenant waiting for human approval.",
        "args": {},
    },
    "approve_action": {
        "description": "Approve a pending action. The approver must not be the requester.",
        "args": {"action_id": (str, True)},
    },
}


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ---------------------------------------------------------------- state
def _state_path():
    return os.environ.get("GATEWAY_STATE", "state.json")


def _audit_path():
    return os.environ.get("GATEWAY_AUDIT", "audit.jsonl")


def load_state():
    p = _state_path()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"accounts": copy.deepcopy(data.ACCOUNTS), "pending": {}, "approved_quotes": {}}


def save_state(st):
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    os.replace(tmp, _state_path())


# ---------------------------------------------------------------- helpers
def validate_args(tool, args):
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    spec = TOOLS[tool]["args"]
    unknown = sorted(set(args) - set(spec))
    if unknown:
        raise RpcError(-32602, f"unknown argument(s): {', '.join(unknown)}")
    out = {}
    for name, (typ, required) in spec.items():
        if name not in args:
            if required:
                raise RpcError(-32602, f"missing argument: {name}")
            continue
        v = args[name]
        if typ is float and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        if isinstance(v, bool) or not isinstance(v, typ):
            raise RpcError(-32602, f"argument {name} must be {typ.__name__}")
        if typ is str and not (0 < len(v) <= 200):
            raise RpcError(-32602, f"argument {name} must be 1-200 characters")
        out[name] = v
    return out


def result(decision, **fields):
    payload = {"decision": decision, **fields}
    return {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
            "structuredContent": payload, "isError": False}


def tenant_account(st, principal, account_id):
    # Another tenant's account looks exactly like a missing one: no existence leak.
    return st["accounts"].get(principal["tenant"], {}).get(account_id)


def new_pending(st, principal, kind, params, summary):
    aid = "act-" + uuid.uuid4().hex[:10]
    st["pending"][aid] = {"tenant": principal["tenant"], "requested_by": principal["subject"],
                          "kind": kind, "params": params, "summary": summary}
    return aid


# ---------------------------------------------------------------- tools
def call_tool(principal, tool, args):
    st = load_state()
    if tool == "search_accounts":
        q = args["query"].lower()
        limit = max(1, min(args.get("limit", 10), 50))
        rows = [{"account_id": k, "name": v["name"], "tier": v["tier"]}
                for k, v in sorted(st["accounts"].get(principal["tenant"], {}).items())
                if q in v["name"].lower()][:limit]
        return result("ALLOW", accounts=rows)

    if tool == "get_account":
        acct = tenant_account(st, principal, args["account_id"])
        if acct is None:
            return result("NOT_FOUND", account_id=args["account_id"])
        return result("ALLOW", account_id=args["account_id"], account=acct)

    if tool == "set_lead_tier":
        acct = tenant_account(st, principal, args["account_id"])
        if acct is None:
            return result("NOT_FOUND", account_id=args["account_id"])
        if args["tier"] not in TIERS:
            return result("DENY", checks=[["tier_is_valid", False]])
        aid = new_pending(st, principal, "set_lead_tier", args,
                          f"Change {args['account_id']} tier {acct['tier']} -> {args['tier']}: {args['reason']}")
        save_state(st)
        return result("PENDING_APPROVAL", action_id=aid)

    if tool == "quote_price":
        acct = tenant_account(st, principal, args["account_id"])
        if acct is None:
            return result("NOT_FOUND", account_id=args["account_id"])
        if args["plan"] not in data.LIST_PRICE:
            return result("DENY", checks=[["plan_exists", False]])
        decision, checks = policy.discount_decision(args["discount_pct"])
        total = round(data.LIST_PRICE[args["plan"]] * (1 - args["discount_pct"] / 100), 2)
        if decision == "ALLOW":
            st["approved_quotes"][f"{principal['tenant']}/{args['account_id']}"] = total
            save_state(st)
            return result("ALLOW", total=total, checks=checks)
        if decision == "PENDING_APPROVAL":
            aid = new_pending(st, principal, "quote_price", dict(args, total=total),
                              f"Quote {args['plan']} at {args['discount_pct']}% off = {total}")
            save_state(st)
            return result("PENDING_APPROVAL", action_id=aid, total=total, checks=checks)
        return result("DENY", checks=checks)

    if tool == "request_deposit":
        acct = tenant_account(st, principal, args["account_id"])
        if acct is None:
            return result("NOT_FOUND", account_id=args["account_id"])
        q = st["approved_quotes"].get(f"{principal['tenant']}/{args['account_id']}")
        decision, checks = policy.deposit_checks(acct, q, args["amount"])
        if decision == "DENY":
            return result("DENY", checks=checks)
        aid = new_pending(st, principal, "request_deposit", args,
                          f"Deposit request {args['amount']} on {args['account_id']} (approved quote {q})")
        save_state(st)
        return result("PENDING_APPROVAL", action_id=aid, checks=checks)

    if tool == "list_pending":
        rows = [{"action_id": k, **{f: v[f] for f in ("kind", "summary", "requested_by")}}
                for k, v in sorted(st["pending"].items()) if v["tenant"] == principal["tenant"]]
        return result("ALLOW", pending=rows)

    if tool == "approve_action":
        act = st["pending"].get(args["action_id"])
        if act is None or act["tenant"] != principal["tenant"]:
            return result("NOT_FOUND", action_id=args["action_id"])
        if act["requested_by"] == principal["subject"]:
            return result("DENY", checks=[["approver_differs_from_requester", False]])
        p = act["params"]
        if act["kind"] == "set_lead_tier":
            st["accounts"][act["tenant"]][p["account_id"]]["tier"] = p["tier"]
        elif act["kind"] == "quote_price":
            st["approved_quotes"][f"{act['tenant']}/{p['account_id']}"] = p["total"]
        elif act["kind"] == "request_deposit":
            # A real system would call the payment provider here. The sample only records intent.
            st.setdefault("deposit_requests", []).append({"tenant": act["tenant"], **p})
        del st["pending"][args["action_id"]]
        save_state(st)
        return result("APPROVED_AND_APPLIED", action_id=args["action_id"], kind=act["kind"])

    raise RpcError(-32602, f"unknown tool: {tool}")


# ---------------------------------------------------------------- JSON-RPC
def handle(msg, principal):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        raise RpcError(-32600, "invalid request")
    method, params = msg["method"], msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                "serverInfo": {"name": "sample-mcp-context-gateway", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": t["description"], "inputSchema": {
            "type": "object", "additionalProperties": False,
            "properties": {a: {"type": {"str": "string", "int": "integer", "float": "number"}[ty.__name__]}
                           for a, (ty, _) in t["args"].items()},
            "required": [a for a, (_, req) in t["args"].items() if req]}} for n, t in TOOLS.items()]}
    if method == "tools/call":
        tool = params.get("name")
        if tool not in TOOLS:
            raise RpcError(-32602, f"unknown tool: {tool}")
        args = validate_args(tool, params.get("arguments", {}))
        ok, need = policy.has_scope(principal, tool)
        if not ok:
            res = result("DENY", checks=[["scope:" + need, False]])
        else:
            res = call_tool(principal, tool, args)
        audit.append(_audit_path(), {"subject": principal["subject"], "tenant": principal["tenant"],
                                     "tool": tool, "args": args,
                                     "decision": res["structuredContent"]["decision"]})
        return res
    raise RpcError(-32601, f"method not found: {method}")


def main():
    principal = data.TOKENS.get(os.environ.get("MCP_BEARER", ""))
    if principal is None:
        sys.stderr.write("refusing to start: MCP_BEARER missing or unknown\n")
        sys.exit(3)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        is_notification = isinstance(msg, dict) and "id" not in msg
        try:
            res = handle(msg, principal)
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "result": res}
        except RpcError as e:
            out = {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                   "error": {"code": e.code, "message": e.message}}
        except Exception:  # fail closed: never leak a stack trace, never return ALLOW
            out = {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                   "error": {"code": -32603, "message": "internal error"}}
        if is_notification:
            continue
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

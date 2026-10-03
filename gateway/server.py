"""Synthetic stdio MCP gateway. Seven tools; one principal per session.
Local state and audit are atomic. No live CRM, identity provider or money movement.
"""
import json, math, os, sys, time, uuid
from decimal import Decimal, ROUND_HALF_UP
from . import __version__, data, policy, store
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



def load_state():
    with store.transaction() as (_, st):
        return st

def save_state(st):
    # Administrative fixture helper, not a client tool. Use transaction() for live calls.
    with store.transaction() as (_, current):
        current.clear()
        current.update(st)

def validate_args(tool, args):
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    spec = TOOLS[tool]["args"]
    if set(args)-set(spec):
        raise RpcError(-32602, "unknown argument(s)")
    out = {}
    for name, (typ, required) in spec.items():
        if name not in args:
            if required:
                raise RpcError(-32602, "missing argument: "+name)
            continue
        v = args[name]
        if typ is float and isinstance(v, int) and not isinstance(v, bool):
            try:
                v = float(v)
            except OverflowError:
                raise RpcError(-32602, "number outside sample range")
        if isinstance(v, bool) or not isinstance(v, typ):
            raise RpcError(-32602, "argument "+name+" must be "+typ.__name__)
        if typ is str and not (0 < len(v) <= 200 and v.strip()):
            raise RpcError(-32602, "argument "+name+" must be 1-200 nonblank characters")
        if typ is float and (not math.isfinite(v) or abs(v) > 1_000_000 or Decimal(str(v)).as_tuple().exponent < -2):
            raise RpcError(-32602, "number must be finite, within sample range, and at most two decimal places")
        if name == "limit" and not 1 <= v <= 50:
            raise RpcError(-32602, "limit must be 1-50")
        out[name] = v
    return out

def cents(v):
    return int((Decimal(str(v))*100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def result(decision, **fields):
    payload = {"decision": decision, **fields}
    return {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True, allow_nan=False)}],
            "structuredContent": payload, "isError": False}

def tenant_account(st, principal, account_id):
    return st["accounts"].get(principal["tenant"], {}).get(account_id)

def key(principal, account_id):
    return principal["tenant"]+"/"+account_id

def new_pending(st, principal, kind, params, summary, expected):
    aid = "act-"+uuid.uuid4().hex
    st["pending"][aid] = {"tenant": principal["tenant"], "requested_by": principal["subject"],
        "kind": kind, "params": params, "summary": summary, "expected": expected, "expires_at": time.time()+300}
    return aid

def deposit_checks(st, principal, account_id, acct, quote, amount_cents):
    used = sum(r["amount_cents"] for r in st["deposit_requests"]
        if r["tenant"] == principal["tenant"] and r["account_id"] == account_id)
    checks = [("contract_signed", acct["contract"] == "signed"),
              ("approved_quote_exists", quote is not None), ("amount_positive", amount_cents > 0),
              ("amount_within_deposit_share", quote is not None and used+amount_cents <= quote["total_cents"]//2)]
    return checks

def call_tool(principal, tool, args, st):
    if tool == "search_accounts":
        rows = [{"account_id": k, "name": v["name"], "tier": v["tier"]}
            for k, v in sorted(st["accounts"].get(principal["tenant"], {}).items()) if args["query"].lower() in v["name"].lower()][:args.get("limit", 10)]
        return result("ALLOW", accounts=rows)
    if tool == "list_pending":
        rows = [{"action_id": k, **{f: v[f] for f in ("kind", "summary", "requested_by", "expires_at", "params", "expected")}}
            for k, v in sorted(st["pending"].items()) if v["tenant"] == principal["tenant"]]
        return result("ALLOW", pending=rows)
    if tool == "approve_action":
        act = st["pending"].get(args["action_id"])
        if act is None or act["tenant"] != principal["tenant"]:
            return result("NOT_FOUND", action_id=args["action_id"])
        if act["requested_by"] == principal["subject"]:
            return result("DENY", checks=[["approver_differs_from_requester", False]])
        p = act["params"]
        acct = tenant_account(st, principal, p["account_id"])
        q = st["approved_quotes"].get(key(principal, p["account_id"]))
        checks = [("approval_not_expired", time.time() < act["expires_at"]), ("account_exists", acct is not None)]
        if acct is not None:
            if act["kind"] == "set_lead_tier":
                checks += [("tier_unchanged", acct["tier"] == act["expected"]["tier"])]
            else:
                checks += [("quote_unchanged", q == act["expected"]["quote"])]
                if act["kind"] == "request_deposit":
                    checks += deposit_checks(st, principal, p["account_id"], acct, q, p["amount_cents"])
        if not all(v for _, v in checks):
            del st["pending"][args["action_id"]]
            return result("DENY", checks=checks)
        if act["kind"] == "set_lead_tier":
            acct["tier"] = p["tier"]
        elif act["kind"] == "quote_price":
            st["approved_quotes"][key(principal, p["account_id"])] = p["quote"]
        elif act["kind"] == "request_deposit":
            st["deposit_requests"].append({"tenant": act["tenant"], "quote_id": q["id"], **p})
        else:
            raise ValueError("unknown pending kind")
        del st["pending"][args["action_id"]]
        return result("APPROVED_AND_APPLIED", action_id=args["action_id"], kind=act["kind"])

    acct = tenant_account(st, principal, args["account_id"])
    if acct is None:
        return result("NOT_FOUND", account_id=args["account_id"])
    if tool == "get_account":
        return result("ALLOW", account_id=args["account_id"], account=acct)
    if tool == "set_lead_tier":
        if args["tier"] not in TIERS:
            return result("DENY", checks=[["tier_is_valid", False]])
        aid = new_pending(st, principal, tool, args, "Change tier on "+args["account_id"], {"tier": acct["tier"]})
        return result("PENDING_APPROVAL", action_id=aid)
    q = st["approved_quotes"].get(key(principal, args["account_id"]))
    if tool == "quote_price":
        if args["plan"] not in data.LIST_PRICE:
            return result("DENY", checks=[["plan_exists", False]])
        decision, checks = policy.discount_decision(args["discount_pct"])
        if decision == "DENY":
            return result(decision, checks=checks)
        total_cents = int((Decimal(str(data.LIST_PRICE[args['plan']]))*(Decimal(100)-Decimal(str(args['discount_pct'])))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        quote = {"id": "quote-"+uuid.uuid4().hex, "total_cents": total_cents, "plan": args["plan"]}
        if decision == "ALLOW":
            st["approved_quotes"][key(principal, args["account_id"])] = quote
            return result("ALLOW", total=total_cents/100, checks=checks)
        aid = new_pending(st, principal, tool, dict(args, quote=quote), "Approve quote on "+args["account_id"], {"quote": q})
        return result("PENDING_APPROVAL", action_id=aid, total=total_cents/100, checks=checks)
    if tool == "request_deposit":
        amount = cents(args["amount"])
        checks = deposit_checks(st, principal, args["account_id"], acct, q, amount)
        if not all(v for _, v in checks):
            return result("DENY", checks=checks)
        aid = new_pending(st, principal, tool, dict(args, amount_cents=amount), "Request deposit on "+args["account_id"], {"quote": q})
        return result("PENDING_APPROVAL", action_id=aid, checks=checks)
    raise RpcError(-32602, "unknown tool")

def handle(msg, principal):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        raise RpcError(-32600, "invalid request")
    if "id" in msg and not valid_id(msg["id"]):
        raise RpcError(-32600, "invalid request id")
    method, params = msg["method"], msg.get("params", {})
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        if not isinstance(params, dict):
            raise RpcError(-32602, "params must be an object")
        return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "sample-mcp-context-gateway", "version": __version__}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": t["description"], "inputSchema": {
            "type": "object", "additionalProperties": False,
            "properties": {a: argument_schema(a, ty) for a, (ty, _) in t["args"].items()},
            "required": [a for a, (_, req) in t["args"].items() if req]}} for n, t in TOOLS.items()]}
    if method != "tools/call":
        raise RpcError(-32601, "method not found")
    error, res = None, None
    with store.transaction() as (db, st):
        tool = params.get("name") if isinstance(params, dict) else None
        try:
            if "id" not in msg:
                raise RpcError(-32600, "tools/call requires a request id")
            if not isinstance(params, dict) or set(params)-{"name", "arguments", "_meta"}:
                raise RpcError(-32602, "invalid tools/call params")
            if "_meta" in params and not isinstance(params["_meta"], dict):
                raise RpcError(-32602, "_meta must be an object")
            if not isinstance(tool, str) or tool not in TOOLS:
                raise RpcError(-32602, "unknown tool")
            args = validate_args(tool, params.get("arguments", {}))
            ok, need = policy.has_scope(principal, tool)
            res = call_tool(principal, tool, args, st) if ok else result("DENY", checks=[["scope:"+need, False]])
        except RpcError as e:
            error = e
        # Values are not logged: avoids storing raw customer/free-text arguments.
        event = {"subject": principal["subject"], "tenant": principal["tenant"], "tool": tool if isinstance(tool, str) and len(tool) <= 200 else "invalid",
                 "decision": "ARGUMENT_ERROR" if error else res["structuredContent"]["decision"]}
        if error:
            event["error_code"] = error.code
        elif res["structuredContent"].get("action_id"):
            event["action_id"] = res["structuredContent"]["action_id"]
        store.append(db, event)
    if error:
        raise error
    return res

def valid_id(value):
    return (not isinstance(value, bool) and isinstance(value, (str, int, float, type(None)))
            and (not isinstance(value, float) or math.isfinite(value)))

def argument_schema(name, typ):
    if typ is str:
        schema = {"type":"string", "minLength":1, "maxLength":200, "pattern":r"\S"}
        if name == "tier":
            schema["enum"] = sorted(TIERS)
        return schema
    if typ is int:
        return {"type":"integer", "minimum":1, "maximum":50}
    return {"type":"number", "minimum":-1_000_000, "maximum":1_000_000, "multipleOf":0.01}

def response_id(msg):
    value = msg.get("id") if isinstance(msg, dict) else None
    return value if valid_id(value) else None

def reject_constant(_):
    raise ValueError("non-JSON constant")

def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON number")
    return number

def unique_members(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate JSON member")
        out[k] = v
    return out

def main():
    principal = data.TOKENS.get(os.environ.get("MCP_BEARER", ""))
    if principal is None:
        sys.stderr.write("refusing to start: MCP_BEARER missing or unknown\n")
        sys.exit(3)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line, parse_constant=reject_constant, parse_float=finite_float,
                             object_pairs_hook=unique_members)
        except (ValueError, RecursionError):
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        is_notification = (isinstance(msg, dict) and "id" not in msg and msg.get("jsonrpc") == "2.0"
                           and isinstance(msg.get("method"), str))
        try:
            res = handle(msg, principal)
            out = {"jsonrpc": "2.0", "id": response_id(msg), "result": res}
        except RpcError as e:
            out = {"jsonrpc": "2.0", "id": response_id(msg),
                   "error": {"code": e.code, "message": e.message}}
        except Exception:  # fail closed: never leak a stack trace, never return ALLOW
            out = {"jsonrpc": "2.0", "id": response_id(msg),
                   "error": {"code": -32603, "message": "internal error"}}
        if is_notification:
            continue
        sys.stdout.write(json.dumps(out, allow_nan=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

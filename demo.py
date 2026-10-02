"""SAMPLE demo on synthetic data. Exits 0 only if every expected decision holds."""
import json, os, shutil, sys, tempfile

from client import Session
from gateway import audit

work = tempfile.mkdtemp(prefix="gw-demo-")
agent = Session("tok-agent-acme", work)
human = Session("tok-human-acme", work)
bot = Session("tok-readonly-acme", work)
rows, ok_all = [], True


def expect(label, got, want):
    global ok_all
    ok = got == want
    ok_all &= ok
    rows.append((("PASS" if ok else "FAIL"), label, got))


expect("1 tools/list returns 7 tools", len(agent.rpc("tools/list")["result"]["tools"]), 7)
expect("2 search inside own tenant", [a["account_id"] for a in agent.tool("search_accounts", query="co")["accounts"]], ["A-100"])
expect("3 other tenant's account is invisible", agent.tool("get_account", account_id="G-200")["decision"], "NOT_FOUND")
expect("4 read-only bot cannot write", bot.tool("set_lead_tier", account_id="A-100", tier="A", reason="x")["decision"], "DENY")
r = agent.tool("set_lead_tier", account_id="A-100", tier="A", reason="Re-engaged, asked for pricing")
expect("5 agent write is held for approval", r["decision"], "PENDING_APPROVAL")
expect("6 agent cannot approve (no approve scope)", agent.tool("approve_action", action_id=r["action_id"])["decision"], "DENY")
expect("7 human approves, change applied", human.tool("approve_action", action_id=r["action_id"])["decision"], "APPROVED_AND_APPLIED")
expect("8 tier now A", agent.tool("get_account", account_id="A-100")["account"]["tier"], "A")
expect("9 25% discount denied", agent.tool("quote_price", account_id="A-100", plan="growth", discount_pct=25)["decision"], "DENY")
q = agent.tool("quote_price", account_id="A-100", plan="growth", discount_pct=15)
expect("10 15% discount needs approval", q["decision"], "PENDING_APPROVAL")
expect("11 deposit before quote approval denied", agent.tool("request_deposit", account_id="A-100", amount=1000)["decision"], "DENY")
human.tool("approve_action", action_id=q["action_id"])
d = agent.tool("request_deposit", account_id="A-101", amount=500)
expect("12 deposit with no signed contract denied", (d["decision"], dict(d["checks"])["contract_signed"]), ("DENY", False))
expect("13 deposit above 50% of quote denied", agent.tool("request_deposit", account_id="A-100", amount=2000)["decision"], "DENY")
d = agent.tool("request_deposit", account_id="A-100", amount=1700)
expect("14 valid deposit still needs a human", d["decision"], "PENDING_APPROVAL")
expect("15 human approves deposit", human.tool("approve_action", action_id=d["action_id"])["decision"], "APPROVED_AND_APPLIED")
bad = agent.rpc("tools/call", {"name": "get_account", "arguments": {"account_id": "A-100", "__import__": "os"}})
expect("16 unexpected argument rejected (JSON-RPC -32602)", bad.get("error", {}).get("code"), -32602)
expect("17 malformed JSON rejected (-32700)", agent.raw("{not json").get("error", {}).get("code"), -32700)

for s in (agent, human, bot):
    s.close()
apath = os.path.join(work, "audit.jsonl")
ok, n, _ = audit.verify(apath)
expect("18 audit chain verifies", ok, True)
lines = open(apath).read().splitlines()
rec = json.loads(lines[2]); rec["decision"] = "ALLOW"; lines[2] = json.dumps(rec, sort_keys=True)
open(apath, "w").write("\n".join(lines) + "\n")
ok2, _, bad_line = audit.verify(apath)
expect("19 edited audit record is detected", (ok2, bad_line), (False, 3))

w = max(len(r[1]) for r in rows)
for status, label, got in rows:
    print(f"{status}  {label.ljust(w)}  -> {got}")
print(f"\n{sum(r[0] == 'PASS' for r in rows)}/{len(rows)} expectations held; {n} audit records written.")
shutil.rmtree(work)
sys.exit(0 if ok_all else 1)

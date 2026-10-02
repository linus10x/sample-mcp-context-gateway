import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from gateway import audit, data, policy, server  # noqa: E402
from client import Session  # noqa: E402


class InProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GATEWAY_STATE"] = os.path.join(self.tmp, "s.json")
        os.environ["GATEWAY_AUDIT"] = os.path.join(self.tmp, "a.jsonl")

    def call(self, token_or_principal, tool, **args):
        p = data.TOKENS[token_or_principal] if isinstance(token_or_principal, str) else token_or_principal
        return server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": tool, "arguments": args}}, p)["structuredContent"]

    def test_scope_denied_is_a_normal_result(self):
        r = self.call("tok-readonly-acme", "quote_price", account_id="A-100", plan="growth", discount_pct=5)
        self.assertEqual(r["decision"], "DENY")
        self.assertEqual(r["checks"], [["scope:quotes.write", False]])

    def test_requester_cannot_approve_own_action(self):
        both = {"tenant": "acme", "subject": "user:does-both", "scopes": ["crm.write", "actions.approve"]}
        aid = self.call(both, "set_lead_tier", account_id="A-101", tier="B", reason="test")["action_id"]
        r = self.call(both, "approve_action", action_id=aid)
        self.assertEqual(r["checks"], [["approver_differs_from_requester", False]])

    def test_cross_tenant_approval_looks_missing(self):
        aid = self.call("tok-agent-acme", "set_lead_tier", account_id="A-101", tier="B", reason="t")["action_id"]
        globex_approver = {"tenant": "globex", "subject": "user:g", "scopes": ["actions.approve"]}
        self.assertEqual(self.call(globex_approver, "approve_action", action_id=aid)["decision"], "NOT_FOUND")

    def test_discount_bands(self):
        self.assertEqual(policy.discount_decision(10)[0], "ALLOW")
        self.assertEqual(policy.discount_decision(10.01)[0], "PENDING_APPROVAL")
        self.assertEqual(policy.discount_decision(20)[0], "PENDING_APPROVAL")
        self.assertEqual(policy.discount_decision(20.01)[0], "DENY")
        self.assertEqual(policy.discount_decision(-1)[0], "DENY")

    def test_auto_discount_creates_approved_quote_and_allows_deposit_request(self):
        self.assertEqual(self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)["total"], 1500.0)
        self.assertEqual(self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=750)["decision"], "PENDING_APPROVAL")
        self.assertEqual(self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=750.01)["decision"], "DENY")

    def test_contract_sent_is_not_signed(self):
        self.call("tok-agent-acme", "quote_price", account_id="A-102", plan="starter", discount_pct=0)
        r = self.call("tok-agent-acme", "request_deposit", account_id="A-102", amount=100)
        self.assertEqual(dict(map(tuple, r["checks"]))["contract_signed"], False)

    def test_argument_validation(self):
        p = data.TOKENS["tok-agent-acme"]
        for args in ({"account_id": 7}, {}, {"account_id": "A-100", "extra": 1}, {"account_id": ""}, {"account_id": "x" * 201}):
            with self.assertRaises(server.RpcError) as cm:
                server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "get_account", "arguments": args}}, p)
            self.assertEqual(cm.exception.code, -32602)
        with self.assertRaises(server.RpcError):  # bool is not a number here
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "quote_price", "arguments": {"account_id": "A-100", "plan": "growth", "discount_pct": True}}}, p)

    def test_unknown_method_and_invalid_request(self):
        p = data.TOKENS["tok-agent-acme"]
        with self.assertRaises(server.RpcError) as cm:
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "resources/write"}, p)
        self.assertEqual(cm.exception.code, -32601)
        with self.assertRaises(server.RpcError) as cm:
            server.handle({"id": 1, "method": "ping"}, p)
        self.assertEqual(cm.exception.code, -32600)

    def test_schema_forbids_extra_properties(self):
        tools = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, data.TOKENS["tok-agent-acme"])["tools"]
        self.assertTrue(all(t["inputSchema"]["additionalProperties"] is False for t in tools))

    def test_every_call_is_audited_and_chain_verifies(self):
        self.call("tok-agent-acme", "search_accounts", query="a")
        self.call("tok-readonly-acme", "set_lead_tier", account_id="A-100", tier="A", reason="r")
        ok, n, _ = audit.verify(os.environ["GATEWAY_AUDIT"])
        self.assertTrue(ok)
        self.assertEqual(n, 2)

    def test_deleted_audit_record_is_detected(self):
        for _ in range(3):
            self.call("tok-agent-acme", "search_accounts", query="a")
        path = os.environ["GATEWAY_AUDIT"]
        lines = open(path).read().splitlines()
        open(path, "w").write("\n".join(lines[:1] + lines[2:]) + "\n")
        self.assertFalse(audit.verify(path)[0])


class Subprocess(unittest.TestCase):
    def test_refuses_to_start_without_token(self):
        env = dict(os.environ, MCP_BEARER="", PYTHONPATH=HERE)
        p = subprocess.run([sys.executable, "-m", "gateway.server"], cwd=HERE, env=env, input="", capture_output=True, text=True)
        self.assertEqual(p.returncode, 3)

    def test_corrupt_state_fails_closed(self):
        tmp = tempfile.mkdtemp()
        open(os.path.join(tmp, "state.json"), "w").write("{corrupt")
        s = Session("tok-agent-acme", tmp)
        r = s.rpc("tools/call", {"name": "get_account", "arguments": {"account_id": "A-100"}})
        s.close()
        self.assertEqual(r["error"]["code"], -32603)
        self.assertNotIn("result", r)


if __name__ == "__main__":
    unittest.main()

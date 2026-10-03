import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from gateway import audit, data, policy, server, store  # noqa: E402
from client import Session  # noqa: E402


class InProcess(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        from unittest.mock import patch
        env = patch.dict(os.environ, {"GATEWAY_STATE": os.path.join(self.tmp, "s.sqlite3")})
        env.start()
        self.addCleanup(env.stop)
        os.environ["GATEWAY_STATE"] = os.path.join(self.tmp, "s.sqlite3")
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
        for args in ({"account_id": 7}, {}, {"account_id": "A-100", "extra": 1}, {"account_id": ""}, {"account_id": "x" * 201}, {"account_id": " "*200+"A"}):
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
        schemas = {t["name"]:t["inputSchema"] for t in tools}
        self.assertEqual(schemas["set_lead_tier"]["properties"]["tier"]["enum"], ["A","B","C"])
        self.assertEqual(schemas["search_accounts"]["properties"]["limit"]["minimum"], 1)
        self.assertEqual(schemas["search_accounts"]["properties"]["limit"]["maximum"], 50)
        self.assertEqual(schemas["set_lead_tier"]["properties"]["reason"]["maxLength"], 200)

    def test_every_call_is_audited_and_chain_verifies(self):
        self.call("tok-agent-acme", "search_accounts", query="a")
        self.call("tok-readonly-acme", "set_lead_tier", account_id="A-100", tier="A", reason="r")
        store.export(os.environ["GATEWAY_AUDIT"])
        ok, n, _ = audit.verify(os.environ["GATEWAY_AUDIT"])
        self.assertTrue(ok)
        self.assertEqual(n, 2)

    def test_deleted_audit_record_is_detected(self):
        for _ in range(3):
            self.call("tok-agent-acme", "search_accounts", query="a")
        path = os.environ["GATEWAY_AUDIT"]
        store.export(path)
        with open(path) as f:
            lines = f.read().splitlines()
        with open(path, "w") as f:
            f.write("\n".join(lines[:1] + lines[2:]) + "\n")
        self.assertFalse(audit.verify(path)[0])


    def test_argument_errors_are_audited(self):
        with self.assertRaises(server.RpcError):
            self.call("tok-agent-acme", "get_account", account_id="A-100", unexpected="no")
        self.assertEqual(store.records()[-1]["decision"], "ARGUMENT_ERROR")

    def test_nonfinite_and_precision_rejected(self):
        for v in (float('nan'), float('inf'), float('-inf'), 0.001, 10**1000):
            with self.assertRaises(server.RpcError):
                self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=v)

    def test_stale_quote_or_contract_denies_deposit(self):
        for change in ("quote", "contract"):
            self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
            aid = self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=750)["action_id"]
            if change == "quote":
                self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=5)
            else:
                with store.transaction() as (_, st):
                    st["accounts"]["acme"]["A-100"]["contract"] = "none"
            self.assertEqual(self.call("tok-human-acme", "approve_action", action_id=aid)["decision"], "DENY")
            self.assertFalse(server.load_state()["deposit_requests"])

    def test_expiry_and_replay(self):
        aid = self.call("tok-agent-acme", "set_lead_tier", account_id="A-100", tier="A", reason="x")["action_id"]
        with store.transaction() as (_, st):
            st["pending"][aid]["expires_at"] = 0
        self.assertEqual(self.call("tok-human-acme", "approve_action", action_id=aid)["decision"], "DENY")
        self.assertEqual(self.call("tok-human-acme", "approve_action", action_id=aid)["decision"], "NOT_FOUND")
        self.assertEqual(server.load_state()["accounts"]["acme"]["A-100"]["tier"], "B")

    def test_concurrent_deposits_cannot_exceed_limit(self):
        from concurrent.futures import ThreadPoolExecutor
        self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
        aids = [self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=750)["action_id"] for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(lambda aid: self.call("tok-human-acme", "approve_action", action_id=aid)["decision"], aids))
        self.assertCountEqual(decisions, ["APPROVED_AND_APPLIED", "DENY"])
        self.assertEqual(len(server.load_state()["deposit_requests"]),1)

    def test_audit_insert_failure_rolls_back_action(self):
        from unittest.mock import patch
        self.call("tok-agent-acme", "search_accounts", query="a")
        before = server.load_state()
        with patch.object(store, 'append', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.call("tok-agent-acme", "set_lead_tier", account_id="A-100", tier="A", reason="x")
        self.assertEqual(server.load_state(),before)
        self.assertEqual(len(store.records()),1)

    def test_tail_truncation_needs_and_is_detected_by_anchor(self):
        for _ in range(2):
            self.call("tok-agent-acme", "search_accounts", query="a")
        path = os.environ["GATEWAY_AUDIT"]
        anchor = store.export(path)
        with open(path) as f:
            lines = f.readlines()
        with open(path,'w') as f:
            f.writelines(lines[:-1])
        self.assertTrue(audit.verify(path)[0])  # intentional boundary: prefix alone is valid
        self.assertFalse(audit.verify(path,anchor)[0])

    def test_corrupt_chain_blocks_future_actions(self):
        self.call("tok-agent-acme", "search_accounts", query="a")
        with store.transaction() as (db,_):
            db.execute("UPDATE events SET body=? WHERE seq=1", ('{"hash":"invalid"}',))
        with self.assertRaises(ValueError):
            self.call("tok-agent-acme", "set_lead_tier", account_id="A-100", tier="A", reason="x")

    def test_notifications_cannot_mutate(self):
        with self.assertRaises(server.RpcError):
            server.handle({"jsonrpc":"2.0","method":"tools/call","params":{"name":"set_lead_tier","arguments":{"account_id":"A-100","tier":"A","reason":"x"}}},data.TOKENS["tok-agent-acme"])
        self.assertFalse(server.load_state()["pending"])

    def test_replaced_quote_does_not_reset_account_deposit_limit(self):
        self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
        aid = self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=750)["action_id"]
        self.call("tok-human-acme", "approve_action", action_id=aid)
        self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
        self.assertEqual(self.call("tok-agent-acme", "request_deposit", account_id="A-100", amount=1)["decision"], "DENY")

    def test_pending_review_shows_exact_terms_and_expected_state(self):
        aid = self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="growth", discount_pct=15)["action_id"]
        pending = self.call("tok-human-acme", "list_pending")["pending"]
        action = next(p for p in pending if p["action_id"] == aid)
        self.assertEqual(action["params"]["quote"]["total_cents"], 340000)
        self.assertEqual(action["expected"], {"quote": None})

    def test_stale_pending_quote_cannot_overwrite_new_quote(self):
        aid = self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="growth", discount_pct=15)["action_id"]
        self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
        self.assertEqual(self.call("tok-human-acme", "approve_action", action_id=aid)["decision"], "DENY")
        self.assertEqual(server.load_state()["approved_quotes"]["acme/A-100"]["total_cents"], 150000)

    def test_actual_commit_failure_rolls_back_state_and_audit(self):
        import sqlite3
        from unittest.mock import patch
        self.call("tok-agent-acme", "search_accounts", query="a")
        before, count = server.load_state(), len(store.records())
        real_connect = sqlite3.connect
        with real_connect(os.environ["GATEWAY_STATE"]) as db:
            db.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE child(pid INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)')
            db.execute('CREATE TRIGGER fail_commit AFTER INSERT ON events BEGIN INSERT INTO child VALUES (1); END')
        def connected(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            db.execute('PRAGMA foreign_keys=ON')
            return db
        with patch.object(store.sqlite3, 'connect', side_effect=connected):
            with self.assertRaises(sqlite3.IntegrityError):
                self.call("tok-agent-acme", "quote_price", account_id="A-100", plan="starter", discount_pct=0)
        self.assertEqual(server.load_state(), before)
        self.assertEqual(len(store.records()), count)

    def test_metadata_is_an_object(self):
        for value in (None, 1, [], True):
            with self.assertRaises(server.RpcError):
                server.handle({"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"set_lead_tier", "arguments":{"account_id":"A-100", "tier":"A", "reason":"x"}, "_meta":value}},data.TOKENS["tok-agent-acme"])
        self.assertFalse(server.load_state()["pending"])


class Subprocess(unittest.TestCase):
    def session(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        s = Session("tok-agent-acme",tmp.name)
        self.addCleanup(s.close)
        return s

    def test_invalid_wire_ids_return_null(self):
        s = self.session()
        for bad in ({"x":1}, [], False):
            r = s.raw(json.dumps({"jsonrpc":"2.0", "id":bad, "method":"ping"}))
            self.assertEqual(r, {"jsonrpc":"2.0", "id":None, "error":{"code":-32600, "message":"invalid request id"}})
        for valid in ("id", 1, 1.5, None):
            r = s.raw(json.dumps({"jsonrpc":"2.0", "id":valid, "method":"ping"}))
            self.assertEqual(r["id"],valid)
            self.assertIn("result",r)

    def test_non_json_metadata_never_dispatches_mutation(self):
        s = self.session()
        for value in ('NaN','Infinity','-Infinity','1e309'):
            line = '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"set_lead_tier","arguments":{"account_id":"A-100","tier":"A","reason":"x"},"_meta":'+value+'}}'
            r = s.raw(line)
            self.assertEqual(r["id"],None)
            self.assertEqual(r["error"]["code"],-32700)
        self.assertFalse(s.tool("list_pending")["pending"])

    def test_duplicate_members_and_invalid_envelopes(self):
        s = self.session()
        r = s.raw('{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}')
        self.assertEqual(r["error"]["code"],-32700)
        r = s.raw('{"method":1}')
        self.assertEqual(r["error"]["code"],-32600)
        self.assertIsNone(r["id"])

    def test_refuses_to_start_without_token(self):
        env = dict(os.environ, MCP_BEARER="", PYTHONPATH=HERE)
        p = subprocess.run([sys.executable, "-m", "gateway.server"], cwd=HERE, env=env, input="", capture_output=True, text=True)
        self.assertEqual(p.returncode, 3)

    def test_corrupt_state_fails_closed(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp = tmpdir.name
        with open(os.path.join(tmp, "state.sqlite3"), "w") as f:
            f.write("{corrupt")
        s = Session("tok-agent-acme", tmp)
        r = s.rpc("tools/call", {"name": "get_account", "arguments": {"account_id": "A-100"}})
        s.close()
        self.assertEqual(r["error"]["code"], -32603)
        self.assertNotIn("result", r)


if __name__ == "__main__":
    unittest.main()

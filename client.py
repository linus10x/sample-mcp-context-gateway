"""Tiny stdio MCP client used by the demo and tests (one subprocess per principal)."""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


class Session:
    def __init__(self, token, workdir):
        env = dict(os.environ, MCP_BEARER=token,
                   GATEWAY_STATE=os.path.join(workdir, "state.json"),
                   GATEWAY_AUDIT=os.path.join(workdir, "audit.jsonl"),
                   PYTHONPATH=HERE)
        self.p = subprocess.Popen([sys.executable, "-m", "gateway.server"], cwd=HERE, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "sample-client", "version": "0"}})
        self.notify("notifications/initialized")

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def raw(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def rpc(self, method, params=None):
        self.n += 1
        return self.raw(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}))

    def tool(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        return r["result"]["structuredContent"] if "result" in r else r

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)

"""Optional interop check: drive the sample server with the official MCP Python SDK client.
Run:  uv run --with mcp python interop/sdk_client_check.py"""
import asyncio, os, sys, tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main():
    tmp = tempfile.mkdtemp()
    params = StdioServerParameters(command=sys.executable, args=["-m", "gateway.server"], cwd=HERE,
                                   env={"MCP_BEARER": "tok-agent-acme", "PYTHONPATH": HERE,
                                        "GATEWAY_STATE": os.path.join(tmp, "s.json"),
                                        "GATEWAY_AUDIT": os.path.join(tmp, "a.jsonl")})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = await s.list_tools()
            res = await s.call_tool("get_account", {"account_id": "G-200"})
            print("server:", init.server_info.name, "| protocol:", init.protocol_version)
            print("tools:", [t.name for t in tools.tools])
            print("cross-tenant get_account ->", res.structured_content)
            assert res.structured_content["decision"] == "NOT_FOUND"
    print("SDK interop check passed")

asyncio.run(main())

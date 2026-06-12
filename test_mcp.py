#!/usr/bin/env python3
"""Smoke test for the MCP server (python askpet.py --mcp).

Spawns the server as a subprocess and speaks newline-delimited JSON-RPC
over its pipes — the same way a real MCP client does. Offline.
"""

import json
import subprocess
import sys


class McpClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "askpet.py", "--mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            encoding="utf-8", bufsize=1)
        self._id = 0

    def request(self, method, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, f"server closed the pipe on {method}"
        reply = json.loads(line)
        assert reply.get("id") == self._id, f"id mismatch on {method}: {reply}"
        return reply

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def call_tool(self, name, arguments):
        reply = self.request("tools/call", {"name": name, "arguments": arguments})
        result = reply["result"]
        text = result["content"][0]["text"]
        if result.get("isError"):
            return {"_error": text}
        return json.loads(text)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def main():
    c = McpClient()
    try:
        # Handshake
        init = c.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test_mcp", "version": "0"},
        })["result"]
        assert init["serverInfo"]["name"] == "AskPet", init
        assert "tools" in init["capabilities"], init
        c.notify("notifications/initialized")
        print(f"initialize OK (protocol {init['protocolVersion']})")

        # Tool list
        tools = c.request("tools/list")["result"]["tools"]
        names = {t["name"] for t in tools}
        expected = {"ask", "build_prompt", "list_library", "search_library", "get_item"}
        assert names == expected, names
        assert all(t["description"] and t["inputSchema"] for t in tools)
        print(f"tools/list OK ({len(tools)} tools)")

        # ask: task -> prompt with recommendation
        r = c.call_tool("ask", {"message": "intune compliance policy for new laptops"})
        assert r["type"] == "prompt", r
        assert r["prompt"].startswith("# "), r["prompt"][:60]
        assert r["template"] and r["modules"], r
        print(f"ask(task) OK -> template={r['template']}, dest={r['destination']}")

        # ask: short/vague task -> clarifying questions present
        r = c.call_tool("ask", {"message": "outlook keeps crashing"})
        assert r.get("clarifying_questions"), r
        print(f"ask(vague) OK -> {len(r['clarifying_questions'])} clarifying questions")

        # ask: help question -> KB answer, no prompt
        r = c.call_tool("ask", {"message": "when should I start a fresh chat?"})
        assert r["type"] == "help_answer" and "handoff" in r["answer"].lower(), r
        print("ask(help question) OK -> knowledge-base answer")

        # ask: typo/shorthand cleanup runs
        r = c.call_tool("ask", {"message": "ps scirpt to audit o365 grps"})
        assert "PowerShell" in r["interpreted_as"], r["interpreted_as"]
        assert "Microsoft 365" in r["interpreted_as"], r["interpreted_as"]
        print(f"ask(typos) OK -> interpreted as: {r['interpreted_as']!r}")

        # build_prompt with clarification answers -> answers become context
        r = c.call_tool("build_prompt", {
            "task": "outlook keeps crashing",
            "answers": ["everyone in finance, since Tuesday",
                        "error 0x80004005 after the May update"]})
        assert "Context I will provide" in r["prompt"], r["prompt"][-400:]
        assert "0x80004005" in r["prompt"], r["prompt"][-400:]
        print("build_prompt(answers) OK -> answers folded into prompt context")

        # list_library: all kinds, sane counts
        r = c.call_tool("list_library", {})
        counts = {k: len(v) for k, v in r.items()}
        assert counts["templates"] >= 40 and counts["modules"] >= 60 and counts["skills"] >= 80, counts
        print(f"list_library OK -> {counts}")

        # list_library: single kind
        r = c.call_tool("list_library", {"kind": "module"})
        assert list(r) == ["modules"], list(r)
        print("list_library(kind) OK")

        # search_library finds the handoff content
        r = c.call_tool("search_library", {"query": "handoff new chat"})
        kinds = {x["kind"] for x in r["results"]}
        assert r["results"] and "skill" in kinds, r
        print(f"search_library OK -> {len(r['results'])} results, kinds={kinds}")

        # get_item round-trip from search
        top = r["results"][0]
        item = c.call_tool("get_item", {"kind": top["kind"], "key": top["key"]})
        assert item["body"], item
        print(f"get_item OK -> {item['kind']}:{item['key']}")

        # get_item: bad key -> in-band error with close-match hint
        r = c.call_tool("get_item", {"kind": "module", "key": "plan_frist"})
        assert "_error" in r and "plan_first" in r["_error"], r
        print("get_item(bad key) OK -> error suggests close match")

        # unknown method -> JSON-RPC error
        reply = c.request("bogus/method")
        assert reply.get("error", {}).get("code") == -32601, reply
        print("unknown method OK -> -32601")

        # ping
        assert c.request("ping")["result"] == {}
        print("ping OK")
    finally:
        c.close()
    print("MCP SMOKE TEST PASSED")


if __name__ == "__main__":
    main()

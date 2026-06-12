#!/usr/bin/env python3
"""Battery runner: push realistic chat messages through the MCP ask tool
and print compact routing results for quality review. Dev tool, offline."""

import sys
from test_mcp import McpClient

BATTERY = [
    # --- help / best-practice questions (should hit the KB, not build prompts)
    ("help", "how do I write better prompts?"),
    ("help", "what context should I include when asking for help?"),
    ("help", "can I trust what the AI tells me?"),
    ("help", "should I use codex or chatgpt for a powershell script?"),
    ("help", "what are agent modules?"),
    ("help", "why do you always add a plan first step?"),
    # --- troubleshooting
    ("fixit", "outlook keeps crashing when opening calendar invites"),
    ("fixit", "users cant login to vpn since this morning"),
    ("fixit", "sharepoint site disappeared for one user"),
    ("fixit", "laptops not getting the new wifi profile from intune"),
    # --- scripting / execution
    ("exec", "ps script to disable entra accounts inactive 90 days"),
    ("exec", "automate intune stale device cleanup with graph api"),
    ("exec", "python script to parse iis logs for 500 errors"),
    ("exec", "bulk update ad group memberships from a csv"),
    ("exec", "azure function that syncs okta groups to entra"),
    # --- planning / writing
    ("plan", "plan our migration from okta to entra id"),
    ("plan", "draft a change request for the exchange 2019 upgrade"),
    ("plan", "document our laptop onboarding process in confluence"),
    ("plan", "summarize this incident for the executive team"),
    ("plan", "jira ticket for replacing the aging file server"),
    # --- policy / compliance
    ("policy", "intune compliance policy for new laptops"),
    ("policy", "set up conditional access for contractors"),
    ("policy", "mfa rollout plan for the warehouse staff"),
    # --- project-specific
    ("deckside", "fix the deckside announcer tab pdf parsing bug"),
    ("handoff", "make me a handoff prompt for this chat"),
    # --- vague (should ask clarifying questions)
    ("vague", "help with email"),
    ("vague", "the server thing again"),
    ("vague", "i need a script"),
    # --- mixed intent
    ("mixed", "investigate why backups fail every sunday and write a runbook"),
    ("mixed", "diagram our network for the auditors"),
    # --- round 2: privacy + more phrasings
    ("help", "do you send my data anywhere?"),
    ("help", "is this local or does it use chatgpt?"),
    ("help", "how do i hand off this conversation to a new chat?"),
    ("fixit", "phishing email reported by a user in accounting"),
    ("fixit", "sentinelone flagged malware on a sales laptop"),
    ("fixit", "printer queue stuck on the print server"),
    ("fixit", "my docker container wont start on the build server"),
    ("exec", "kql query for failed sign-ins last week"),
    ("exec", "renew the wildcard cert before it expires next month"),
    ("exec", "set up github actions to lint our powershell repo"),
    ("exec", "automate user offboarding with a logic app"),
    ("exec", "powersehll scirpt for intune complaince policy"),
    ("plan", "write a postmortem for yesterdays vpn outage"),
    ("plan", "compare ninjaone vs connectwise for rmm"),
    ("plan", "draft comms to all staff about the email outage"),
    ("plan", "license report for m365 e5 usage"),
    ("plan", "onboard 15 new hires starting next monday"),
    ("plan", "restore a deleted onedrive file for a leaver"),
    ("plan", "explain the difference between gpo and intune policies"),
    ("exec", "review this terraform for security issues"),
]


def main():
    c = McpClient()
    problems = []
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18",
                                 "capabilities": {},
                                 "clientInfo": {"name": "battery", "version": "0"}})
        c.notify("notifications/initialized")
        for category, message in BATTERY:
            r = c.call_tool("ask", {"message": message})
            if r["type"] == "help_answer":
                print(f"[{category:8s}] {message!r}\n  -> HELP: {r['answer'][:90]!r}...")
                if category != "help":
                    problems.append((category, message, "unexpected help answer"))
                continue
            qs = r.get("clarifying_questions", [])
            mods = ",".join(r["modules"])
            sks = ",".join(r["skills"])
            print(f"[{category:8s}] {message!r}\n"
                  f"  -> dest={r['destination']!r} template={r['template']} q={len(qs)}\n"
                  f"     modules=[{mods}] skills=[{sks}]")
            if category == "help":
                problems.append((category, message, "expected help answer, got prompt"))
            if category == "vague" and not qs:
                problems.append((category, message, "expected clarifying questions"))
    finally:
        c.close()
    print(f"\n{len(BATTERY)} messages sent.")
    if problems:
        print(f"{len(problems)} flagged:")
        for cat, msg, why in problems:
            print(f"  [{cat}] {msg!r}: {why}")
    else:
        print("No category mismatches flagged (manual quality review still applies).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Mega battery: generate thousands of chat messages (role tasks x
phrasings) and run them through the recommendation brain directly,
flagging weak routing. Same logic the MCP ask tool calls; direct import
keeps thousands of messages fast. Dev tool, offline.

Usage: python mega_battery.py [--verbose]
"""

import sys
from collections import defaultdict

import promptmate as pm

DEFAULT_MODULES = {"plan_first", "harness", "validation"}
GENERIC_TEMPLATES = {"chatgpt_planning", "codex_execution"}

# area -> (expect_specialist, [task seeds])
SEEDS = {
    # --- non-technical roles (new content) ---
    "chief_of_staff": (True, [
        "prep me for the board meeting next week",
        "write a decision memo on opening a second office",
        "draft okrs for the operations team next quarter",
        "put together the leadership update for friday",
        "build the agenda for the strategy offsite",
        "track the action items from the exec staff meeting",
        "write the exec summary of this 30 page report",
        "prepare talking points for the all hands",
    ]),
    "exec_assistant": (True, [
        "manage my boss's calendar, he is double booked all week",
        "find a time for 6 people across 3 time zones",
        "reschedule the quarterly review without losing the room",
        "block focus time on the team's calendar",
        "plan travel arrangements for the london trip",
        "build an itinerary for the customer visit",
        "triage an inbox with 800 unread emails",
        "draft an out of office message for the holidays",
    ]),
    "email": (True, [
        "draft an email to decline a vendor meeting politely",
        "write an email asking finance for the budget numbers",
        "reply to this angry email from a partner",
        "write a follow up email after the demo call",
        "cold email to a potential supplier",
        "email the team about the new parking rules",
        "email my manager asking for a raise conversation",
        "write a follow-up email for an unpaid invoice",
    ]),
    "notes_notion": (True, [
        "turn these meeting notes into action items",
        "take minutes from this transcript",
        "organize my notes, they are scattered everywhere",
        "tidy my notes from the conference",
        "set up a clean notion workspace for the team",
        "build a notion tracker for our projects",
        "create a note taking system i will stick with",
        "transcribe and summarize this voice memo",
    ]),
    "office_docs": (True, [
        "make this word document look professional",
        "add a table of contents to my word doc",
        "set up a mail merge for 200 customer letters",
        "create a sop for the monthly close process",
        "format the document with consistent styles",
        "write a doc template for project proposals",
        "fix the page numbers in a google doc",
        "turn this outline into a polished google doc",
    ]),
    "spreadsheets": (True, [
        "vlookup formula to match employee ids across two sheets",
        "pivot table to summarize spend by department",
        "formula to flag duplicate rows in excel",
        "conditional formatting to highlight overdue items",
        "clean up a messy spreadsheet with merged cells",
        "sumif across multiple tabs",
        "build a budget tracker in google sheets",
        "xlookup that returns multiple columns",
    ]),
    "presentation": (True, [
        "outline a slide deck for the quarterly business review",
        "turn this report into a 10 slide presentation",
        "build a pitch deck for the new service",
        "write speaker notes for my keynote",
        "make a one-pager from this proposal",
        "powerpoint structure for the training session",
        "google slides for the team offsite recap",
        "shorten my 40 slide deck to 15",
    ]),
    "notebooklm": (True, [
        "summarize these pdfs in notebooklm",
        "use notebooklm to study these contracts",
        "make an audio overview of the research papers",
        "ask questions grounded in my uploaded sources",
        "compare what my sources say about pricing",
        "notebook lm setup for the team's research",
    ]),
    "hr": (True, [
        "write a job description for an office manager",
        "interview questions for a customer success role",
        "draft my self review for the year",
        "performance review feedback for a direct report",
        "offer letter for the marketing hire",
        "plan new hire orientation for next month",
        "draft questions for the engagement survey",
        "prepare an exit interview guide",
    ]),
    "sales": (True, [
        "write a sales proposal for the acme deal",
        "follow up email after the discovery call",
        "clean up the crm before the pipeline review",
        "handle the pricing objection from the prospect",
        "renewal email for a customer at risk",
        "sales deck for the enterprise pitch",
        "win-back email for churned customers",
        "quote for a customer asking for volume discount",
    ]),
    "marketing": (True, [
        "linkedin post announcing our new feature",
        "newsletter for november",
        "content calendar for next quarter",
        "blog post about the customer case study",
        "press release for the partnership",
        "landing page copy for the webinar",
        "social media plan for the product launch",
        "seo improvements for the pricing page",
    ]),
    "support": (True, [
        "reply to an angry customer asking for a refund",
        "apology email for the shipping delay",
        "canned responses for the top 10 questions",
        "help center article for password resets",
        "handle an escalation from a churn risk account",
        "work through the ticket backlog faster",
        "csat survey follow-up process",
        "customer complaint about billing twice",
    ]),
    "finance": (True, [
        "explain the budget variance for q3",
        "forecast next quarter's software spend",
        "chase unpaid invoices politely",
        "reconciliation of the corporate card statements",
        "build the budget for the new team",
        "expense report cleanup before month end",
        "purchase request justification for new laptops",
        "spend report by cost center",
    ]),
    "project_mgmt": (True, [
        "project plan for the office move",
        "kickoff for the website redesign project",
        "raid log for the erp rollout",
        "status update for stakeholders",
        "workback schedule from the launch date",
        "retrospective for the last sprint",
        "timeline for the audit preparation",
        "track dependencies across three teams",
    ]),
    "events": (True, [
        "plan the company offsite in september",
        "run of show for the annual kickoff",
        "venue and catering for 80 people",
        "webinar invite and registration page",
        "team building event for a remote team",
        "save the date for the holiday party",
    ]),
    "legal": (True, [
        "review this contract before we sign",
        "summarize the nda terms",
        "redline the msa against our standard terms",
        "prep questions for legal review of the sow",
        "check the renewal terms in the vendor contract",
        "terms of service summary for the new app",
    ]),
    # --- IT regression seeds (should stay specialist) ---
    "it_core": (True, [
        "ps script to disable inactive entra accounts",
        "outlook keeps crashing when opening calendar invites",
        "intune compliance policy for new laptops",
        "set up conditional access for contractors",
        "bulk update ad group memberships from a csv",
        "renew the wildcard cert before it expires",
        "add a fortigate rule for the new vlan",
        "automate the nightly sftp transfer of payroll files",
    ]),
    # --- vague (clarifying questions expected, generic OK) ---
    "vague": (False, [
        "help with a doc",
        "i need an email",
        "fix my spreadsheet",
        "plan something for the team",
    ]),
}

WRAPPERS = [
    "{t}",
    "can you help me {t}",
    "i need to {t}",
    "help me {t}",
    "{t} please",
    "{t} for my boss",
    "{t} by friday",
    "hey, {t}",
    "need help: {t}",
    "{t} asap",
    "could you {t}",
    "pls {t}",
    "{t} today",
    "{t} this week",
    "quick one: {t}",
    "{t} - thanks!",
]


def main():
    verbose = "--verbose" in sys.argv
    spell = pm.SpellHelper()
    total = 0
    flagged = defaultdict(list)
    help_hits = 0
    for area, (expect_specialist, tasks) in SEEDS.items():
        for t in tasks:
            for w in WRAPPERS:
                msg = w.format(t=t)
                total += 1
                if pm.answer_help_question(msg):
                    help_hits += 1
                    flagged[area].append((msg, "help-answer-for-task"))
                    continue
                cleaned = pm.clean_text(msg, spell)
                rec = pm.recommend(cleaned)
                if not expect_specialist:
                    continue
                flags = []
                if rec["template"] in GENERIC_TEMPLATES and not rec["skills"]:
                    flags.append("generic+no-skills")
                if set(rec["modules"]) <= DEFAULT_MODULES:
                    flags.append("default-modules-only")
                if flags:
                    flagged[area].append((msg, ",".join(flags), rec["template"]))
    print(f"{total} messages generated and routed.")
    n_flagged = sum(len(v) for v in flagged.values())
    print(f"{n_flagged} flagged ({100 * n_flagged / total:.1f}%), "
          f"{help_hits} help-answer misfires.\n")
    for area, items in sorted(flagged.items(), key=lambda kv: -len(kv[1])):
        uniq_tasks = {i[0].replace("can you help me ", "").replace("i need to ", "")
                      for i in items}
        print(f"[{area}] {len(items)} flagged")
        shown = items if verbose else items[:4]
        for i in shown:
            print(f"    {i}")
        if not verbose and len(items) > 4:
            print(f"    ... +{len(items) - 4} more")


if __name__ == "__main__":
    main()

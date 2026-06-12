#!/usr/bin/env python3
"""Gemma battery: push ~200 realistic asks through the local-AI lanes
(the exact system prompts the chat uses) and grade the outputs with
format-level checks. Results land in gemma_battery_results.json for
deeper quality review. Run: python gemma_battery.py [--limit N]

Routing-only cases assert the lane decision without calling the model.
"""

import json
import re
import sys
import time

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spell = pm.SpellHelper()

# --- payloads -----------------------------------------------------------------
REWRITE_PAYLOADS = [
    "hey can u send me the q3 report from yesterday i need it asap thx",
    "im gonna be out sick tomorrow so the 9am with dave needs to move to thursday",
    "the server thing broke again last nite, johns looking at it but its probly the disk like last time",
    "we cant do the deadline friday, vendor didnt ship the parts till the 10th so were 2 weeks behind",
    "good job everyone on the migration, only 3 tickets and nothing major, beers on me friday",
    "i checked w/ accounting and the invoice 4482 for $12,500 was paid on may 28 so they should stop emailing us",
    "the wifi in building 2 keeps droping, like every hour, started after the update on tuesday",
    "pls tell the new guy mark hes gotta do the security training before friday or hr gets mad",
]
REWRITE_STYLES = [
    "rewrite this to sound professional: {x}",
    "make this clearer: {x}",
    "shorten this: {x}",
    "fix the grammar and spelling: {x}",
    "make this friendlier: {x}",
]

EMAILS = [
    "write an email asking IT for a second monitor",
    "write an email asking finance for the updated budget numbers by friday",
    "draft an email to decline a vendor meeting politely",
    "draft an email to decline the conference invitation, im traveling that week",
    "write a follow up email after the demo call with acme on tuesday",
    "write a follow-up email for invoice 2291 which is 30 days overdue",
    "write an out of office message for june 20 to june 27, back monday",
    "write an email to the team about the parking lot closing next week",
    "write an email asking my manager for friday off",
    "write an email thanking sarah for covering my shift",
    "draft an email to reschedule the 1:1 with my manager to thursday",
    "write an email to a customer apologizing for the late shipment",
    "write an email asking the landlord to fix the office ac",
    "write an email introducing our new helpdesk tech jordan to the company",
    "draft an email asking the team to submit timesheets by end of day",
    "write an email to hr asking how many vacation days i have left",
    "write an email asking a colleague to review my slide deck by wednesday",
    "draft an email telling a recruiter im not interested but politely",
    "write an email to the building manager about the broken elevator",
    "write an email reminding everyone about the security training due friday",
    "write an email asking the vendor for a quote on 25 laptops",
    "draft an email to a client moving our meeting from 2pm to 4pm",
    "write an email announcing the office will close early on july 3",
    "write an email asking for an extension on the project deadline",
    "write an email to support about my order arriving damaged",
    "draft a thank you email after a job interview",
    "write an email asking the team who can cover on-call this weekend",
    "write an email telling a customer their refund was processed",
    "draft an email to schools IT asking to whitelist our app",
    "write an email nudging legal about the contract sent two weeks ago",
    "write an email to the team celebrating that we hit the quarterly goal",
    "draft an email asking my mentor for 30 minutes of advice",
    "write an email to a noisy neighbor about the construction hours, keep it friendly",
    "write an email canceling my gym membership",
    "draft an email asking the hotel for a late checkout",
    "write an email to the soccer team parents about saturdays game moving to 9am",
    "write an email asking the coach if my kid can miss practice thursday",
    "draft an email to the hoa about the broken streetlight",
    "write an email rsvping yes to the wedding for two people",
    "write an email asking the dentist to reschedule my appointment",
]

SUMMARY_TEXTS = [
    ("meeting notes", "the meeting covered three things. first the budget overrun of $40k on the warehouse project, mostly from the steel price increase. second we agreed to move the go-live from august 15 to september 1 because testing is behind. third maria will hire two contractors for the data migration, starting july. next meeting is june 25."),
    ("incident report", "at 2:14am the primary database server ran out of disk space and the app went down for 47 minutes. the on-call engineer cleared old log files to restore service at 3:01am. root cause is the log rotation job that was disabled during last months maintenance and never re-enabled. action items: re-enable rotation, add disk alerts at 80 percent, review other servers for the same issue."),
    ("product update", "version 2.4 ships with single sign on support, a redesigned dashboard, and csv export. the mobile app now works offline and syncs when reconnected. pricing stays the same for existing customers but new signups after july 1 pay the updated rates. support for the legacy api ends december 31."),
    ("policy change", "starting october 1 all employees must use the password manager for work credentials. personal browser password storage will be disabled by policy. shared team passwords move to team vaults by september 15, and the it team will run migration sessions every tuesday and thursday in september. exceptions require a written waiver from the security team."),
    ("trip report", "the vendor visit went well. their factory can handle our volume with a 6 week lead time, 4 weeks if we commit to quarterly orders. unit cost came in at $11.20 which is 8 percent below the current supplier. quality looked good but their packaging line is manual which worries me for the holiday rush. they offered net 60 terms. recommend we run a 500 unit pilot order."),
]
SUMMARY_STYLES = [
    "summarize this: {x}",
    "summarize this for my boss: {x}",
    "give me the key points: {x}",
]

ANSWERS = [
    # IT-flavored
    "what does dns actually do?",
    "what is dhcp in simple terms?",
    "whats the difference between http and https?",
    "what is a vpn and when should i use one?",
    "how does mfa stop phishing?",
    "what is a vlan?",
    "whats the difference between ram and storage?",
    "what does a firewall actually block?",
    "what is single sign on?",
    "whats the difference between a switch and a router?",
    "what is conditional access in plain english?",
    "what does end of life mean for software?",
    "what is a sandbox environment?",
    "whats the difference between backup and sync?",
    "what is zero trust security?",
    "what does it mean when a cert expires?",
    "what is bandwidth vs latency?",
    "whats an api in simple terms?",
    "what is the cloud actually?",
    "what does encryption at rest mean?",
    "why do passwords need to be long instead of complex?",
    "what is a phishing simulation?",
    "whats the difference between intune and group policy?",
    "what is an ip address?",
    "what does rebooting actually fix?",
    # general knowledge
    "why is the sky blue?",
    "who wrote romeo and juliet?",
    "what causes inflation?",
    "how do vaccines work?",
    "what is compound interest?",
    "why do we have time zones?",
    "what is the difference between weather and climate?",
    "how does a microwave heat food?",
    "what makes sourdough different from regular bread?",
    "why do cats purr?",
    # quick math / practical
    "what is 15% of 240?",
    "how many ounces in a liter?",
    "if a meeting starts at 2pm pacific what time is that in eastern?",
    "whats 20% tip on an $86 bill?",
    "how many work days are in a typical year?",
    # how-to / advice-shaped
    "how do i politely leave a meeting that is running long?",
    "how do i ask for a raise?",
    "whats a good way to remember peoples names?",
    "how do i stop procrastinating on big tasks?",
    "how should i prepare for a performance review?",
    "whats the best way to take notes in a meeting?",
    "how do i tell a coworker their music is too loud?",
    "how long should a cover letter be?",
    "what should i ask in a job interview?",
    "how do i make my home wifi faster?",
    # definitions / comparisons
    "whats the difference between a 401k and an ira?",
    "what is a deductible in insurance?",
    "whats the difference between gross and net pay?",
    "what does escrow mean?",
    "whats the difference between a lease and a loan?",
    "what is depreciation in simple terms?",
    "whats the difference between margin and markup?",
    "what does fiscal year mean?",
    "what is a kpi?",
    "whats the difference between a vision and a mission statement?",
]

# routing-only: these must NOT go local (no model call)
ROUTING_ONLY = [
    ("write a powershell script to disable inactive accounts", None),
    ("how do i write a python script to parse logs?", None),
    ("summarize this meeting transcript", None),
    ("make this sound friendlier", None),
    ("proofread this paragraph for me", None),
    ("triage an inbox with 800 unread emails", None),
    ("plan our migration from okta to entra", None),
    ("intune compliance policy for new laptops", None),
    ("fix the deckside announcer pdf parsing bug", None),
    ("bulk update ad groups from a csv", None),
]

PREAMBLE_RX = re.compile(
    r"^(sure|okay|ok[,.! ]|of course|certainly|absolutely|great|got it|"
    r"here('s| is| you go)|i('ve| have) (rewritten|drafted|summarized)|"
    r"below is|this is (the|a) (rewritten|summary|draft))", re.IGNORECASE)
META_RX = re.compile(r"as an ai|language model|i (cannot|can't) (help|assist)",
                     re.IGNORECASE)


def check(lane, prompt, out):
    flags = []
    o = out.strip()
    if not o:
        return ["empty"]
    if PREAMBLE_RX.match(o):
        flags.append("preamble")
    if META_RX.search(o):
        flags.append("meta")
    if "```" in o:
        flags.append("code-fence")
    payload = prompt.split(":", 1)[1].strip() if ":" in prompt else prompt
    if lane == "rewrite":
        if o.lower() == payload.lower():
            flags.append("unchanged")
        if len(o) > len(payload) * 3 + 80:
            flags.append("bloated")
        nums = re.findall(r"\$?\d[\d,.]*", payload)
        missing = [n for n in nums if n not in o]
        if nums and len(missing) > len(nums) / 2:
            flags.append("numbers-lost")
    elif lane == "email":
        if not re.match(r"subject\s*:", o, re.IGNORECASE):
            flags.append("no-subject")
        if len(o.split()) > 220:
            flags.append("too-long")
        if "\n" not in o:
            flags.append("no-body")
    elif lane == "summarize":
        if len(o) > len(payload):
            flags.append("longer-than-input")
        nums = re.findall(r"\$?\d[\d,.]*", payload)
        kept = [n for n in nums if n in o]
        if nums and len(kept) < len(nums) / 3:
            flags.append("numbers-lost")
    elif lane == "answer":
        if len(o) > 1400:
            flags.append("rambling")
    return flags


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    battery = []
    for x in REWRITE_PAYLOADS:
        for style in REWRITE_STYLES:
            battery.append(("rewrite", style.format(x=x)))
    battery.extend(("email", e) for e in EMAILS)
    for _, x in SUMMARY_TEXTS:
        for style in SUMMARY_STYLES:
            battery.append(("summarize", style.format(x=x)))
    battery.extend(("answer", a) for a in ANSWERS)
    if limit:
        battery = battery[:limit]

    models = pm.ollama_models()
    model = pm.pick_local_model(models)
    assert model, "Ollama not running"
    print(f"{len(battery)} model questions + {len(ROUTING_ONLY)} routing checks, model={model}")

    # routing-only checks (no model call)
    wrong = 0
    for msg, expected in ROUTING_ONLY:
        got = pm.local_ai_lane(msg, pm.recommend(pm.clean_text(msg, spell)))
        if got != expected:
            print(f"ROUTING WRONG: {msg!r} -> {got}, expected {expected}")
            wrong += 1
    print(f"routing-only: {len(ROUTING_ONLY) - wrong}/{len(ROUTING_ONLY)} OK")

    results, lane_stats = [], {}
    t_start = time.perf_counter()
    for i, (expected_lane, q) in enumerate(battery, 1):
        rec = pm.recommend(pm.clean_text(q, spell))
        lane = pm.local_ai_lane(q, rec)
        entry = {"q": q, "expected_lane": expected_lane, "lane": lane}
        if lane != expected_lane:
            entry["flags"] = ["misrouted"]
            entry["out"] = ""
        else:
            t0 = time.perf_counter()
            try:
                out = pm.ollama_chat_stream(model, pm.LOCAL_AI_LANES[lane], q,
                                            on_chunk=lambda p: None)
            except Exception as e:
                out = ""
                entry["error"] = str(e)
            entry["secs"] = round(time.perf_counter() - t0, 2)
            entry["out"] = out
            entry["flags"] = check(lane, q, out)
        results.append(entry)
        s = lane_stats.setdefault(expected_lane, {"n": 0, "flagged": 0, "secs": 0.0})
        s["n"] += 1
        s["flagged"] += bool(entry["flags"])
        s["secs"] += entry.get("secs", 0)
        if i % 20 == 0:
            print(f"  {i}/{len(battery)} done ({time.perf_counter() - t_start:.0f}s)")

    with open("gemma_battery_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)

    print(f"\n=== {len(battery)} questions in {time.perf_counter() - t_start:.0f}s ===")
    for lane, s in lane_stats.items():
        avg = s["secs"] / max(1, s["n"])
        print(f"  {lane:9s}: {s['n'] - s['flagged']}/{s['n']} clean, avg {avg:.1f}s")
    from collections import Counter
    hist = Counter(f for r in results for f in r["flags"])
    print("  flag histogram:", dict(hist.most_common()))


if __name__ == "__main__":
    main()

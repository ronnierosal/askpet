#!/usr/bin/env python3
"""Local AI tests. Routing-lane tests run offline; the live section talks
to Ollama on localhost and is skipped (with a notice) when it isn't up."""

import sys

import askpet as pm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spell = pm.SpellHelper()


def lane_for(msg):
    rec = pm.recommend(pm.clean_text(msg, spell))
    return pm.local_ai_lane(msg, rec)


# --- offline: lane routing -------------------------------------------------
CASES = [
    # specialized lanes still win when the message clearly calls for them
    ("rewrite this to sound more professional: hey boss im out sick today", "rewrite"),
    ("proofread this: We was going to send the report on monday but it slipped", "rewrite"),
    ("summarize this: the meeting covered budget overruns, the new vendor "
     "contract, and a hiring freeze starting in november", "summarize"),
    ("review this draft: Dear team, the rollout is on track and we are confident", "review"),
    ("critique this opening: It was a dark and stormy night, again, as always", "review"),
    ("feedback on this paragraph: the rollout went smoothly and finished on time", "review"),
    ("draft an email to decline a vendor meeting politely", "email"),
    ("write an email asking finance for the budget numbers", "email"),
    # content words must not disqualify the ask (gemma-battery findings)
    ("summarize this: the migration to the new server is two weeks behind "
     "and the deploy keeps failing on the test environment", "summarize"),
    ("fix the grammar: we cant do the deadline friday, vendor didnt ship "
     "the parts till the 10th", "rewrite"),
    ("write an email asking the landlord to fix the office ac", "email"),
    ("draft a thank you email after a job interview", "email"),
    ("what does dns actually do?", "answer"),
    ("whats the difference between ram and storage", "answer"),
    ("how does mfa stop phishing?", "answer"),
    # General chat is the DEFAULT now: a bare rewrite/summarize ask with no
    # text to work on just becomes a general reply (which asks for the text),
    # NOT the prompt builder.
    ("proofread this paragraph for me", "answer"),
    ("make this sound friendlier", "answer"),
    ("summarize this meeting transcript", "answer"),
    ("tldr of this article", "answer"),
    # email topic without a drafting verb (inbox management) -> general chat
    ("triage an inbox with 800 unread emails", "answer"),
    # execution work is no longer auto-routed to the prompt builder; it's
    # general chat by default (use /fix-prompt to build a prompt instead)
    ("write a powershell script to disable inactive accounts", "answer"),
    ("how do i write a python script to parse these logs?", "answer"),
    ("fix the deckside announcer pdf parsing bug", "answer"),
    ("bulk update ad groups from a csv", "answer"),
    ("plan our migration from okta to entra", "answer"),
    ("intune compliance policy for new laptops", "answer"),
]
failed = 0
for msg, expected in CASES:
    got = lane_for(msg)
    if got != expected:
        print(f"** {msg!r}: expected {expected}, got {got}")
        failed += 1
assert not failed, f"{failed} lane cases wrong"
print(f"lane routing OK ({len(CASES)} cases)")

# review detection is START-anchored: "feedback on" must lead the instruction,
# so a payload message that only mentions it mid-sentence is NOT a review.
assert lane_for("feedback on this paragraph: the rollout went smoothly on time") == "review"
assert lane_for("send the vendor my feedback on their quote: pricing looks high") != "review"
print("review start-anchor OK")

# help KB still wins over the answer lane (checked at the chat layer, but
# the KB must keep matching so _start_request short-circuits first)
assert pm.answer_help_question("what makes a good prompt?")
print("KB priority OK")

# --- offline: model picking -------------------------------------------------
assert pm.pick_local_model([]) == ""
assert pm.pick_local_model(["llama3:8b", "gemma3:1b"]) == "gemma3:1b"
assert pm.pick_local_model(["llama3:8b", "mistral:7b"]) == "llama3:8b"
assert pm.pick_local_model(["llama3:8b", "gemma3:1b"], "llama3:8b") == "llama3:8b"
assert pm.pick_local_model(["gemma3:1b"], "gone:1b") == "gemma3:1b"
print("model picking OK")

# --- live: requires Ollama ---------------------------------------------------
models = pm.ollama_models()
if not models:
    print("Ollama not running - live tests skipped")
    print("LOCAL AI TEST PASSED (offline only)")
else:
    model = pm.pick_local_model(models)
    print(f"live: using {model} from {models}")
    chunks = []
    text = pm.ollama_chat_stream(
        model, pm.LOCAL_AI_LANES["rewrite"],
        "Rewrite professionally: hey can u send the report asap thx",
        on_chunk=chunks.append)
    assert text and len(chunks) > 1, (len(text), len(chunks))
    assert text == "".join(chunks)
    print(f"live stream OK ({len(chunks)} chunks): {text[:80]!r}")

    answer = pm.ollama_chat_stream(
        model, pm.LOCAL_AI_LANES["answer"],
        "In one sentence: what is an IP address?", on_chunk=lambda p: None)
    assert answer.strip()
    print(f"live answer OK: {answer.strip()[:80]!r}")
    print("LOCAL AI TEST PASSED")

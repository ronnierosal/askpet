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
    # light asks the local model should answer
    ("rewrite this to sound more professional: hey boss im out sick today", "rewrite"),
    ("proofread this: We was going to send the report on monday but it slipped", "rewrite"),
    ("summarize this: the meeting covered budget overruns, the new vendor "
     "contract, and a hiring freeze starting in november", "summarize"),
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
    # NOT local: rewrite/summarize asks without the text to work on -
    # the clarifying-question flow should ask for it instead
    ("proofread this paragraph for me", None),
    ("make this sound friendlier", None),
    ("summarize this meeting transcript", None),
    ("tldr of this article", None),
    # NOT local: email topic without a drafting verb (inbox management)
    ("triage an inbox with 800 unread emails", None),
    # NOT local: execution work, even when question-shaped
    ("write a powershell script to disable inactive accounts", None),
    ("how do i write a python script to parse these logs?", None),
    ("fix the deckside announcer pdf parsing bug", None),
    ("bulk update ad groups from a csv", None),
    # NOT local: plain task descriptions without a light-lane topic
    ("plan our migration from okta to entra", None),
    ("intune compliance policy for new laptops", None),
]
failed = 0
for msg, expected in CASES:
    got = lane_for(msg)
    if got != expected:
        print(f"** {msg!r}: expected {expected}, got {got}")
        failed += 1
assert not failed, f"{failed} lane cases wrong"
print(f"lane routing OK ({len(CASES)} cases)")

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

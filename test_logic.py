"""Quick logic smoke test for PromptMate (no GUI). Run: python test_logic.py"""
import promptmate as pm

spell = pm.SpellHelper()

cases = [
    "need a powershel scirpt to deply an intune app pakage to pilot grp",
    "draft conflunce documentaiton for our okta offboarding process",
    "plan the architecture for a new azur fucntion then implement and test it",
    "write a jirra ticket for the o365 license cleanup",
    "help me design a chatgpt workspace agent with insturctions for audit evidence",
    "email is down for the whole company since this morning, sev1",
    "write a postmortem for yesterdays vpn outage",
    "new hire starting monday needs o365 license and laptop setup",
    "user reported a phishing email that 50 people got",
    "kql query to find devices that havent checked in for 30 days",
    "draft a change request for the firewall maintenance window",
    "offboard a terminated user and capture evidence",
]
for raw in cases:
    cleaned = pm.clean_text(raw, spell)
    rec = pm.recommend(cleaned)
    print("RAW:", raw)
    print("CLEANED:", cleaned)
    print("DEST: %s (codex=%s, chatgpt=%s) topics=%s" % (
        rec["destination"], rec["codex_score"], rec["chatgpt_score"], rec["topics"]))
    print("TEMPLATE: %s | MODULES: %s | SKILLS: %s" % (
        rec["template"], rec["modules"], rec["skills"]))
    print("-" * 70)

cleaned = pm.clean_text(cases[0], spell)
rec = pm.recommend(cleaned)
prompt = pm.build_prompt(cleaned, rec, rec["modules"], rec["skills"], ["Target device groups"])
print(prompt[:600])
print("...")
print("PROMPT LENGTH:", len(prompt))

print("suggestions for tempalte:", spell.suggestions("tempalte"))
print("suggestions for deplyoment:", spell.suggestions("deplyoment"))
print("known(jira):", spell.known("jira"), "known(xyzzyq):", spell.known("xyzzyq"))

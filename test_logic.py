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
    "set up a notion database to track our hardware inventory",
    "build a power automate flow that posts new jira tickets to slack",
    "create a github repo for our powershell scripts with branch protection",
    "help me dial in a request for rebuilding our intune packaging process",
    "summarize this zoom recording into action items",
    "i want a chatgpt workspace agent for writing our weekly status reports",
    "rewrite this email to sound more professional",
    "user is locked out of their account again, third time this week",
    "excel formula to find duplicates across two sheets",
    "explain how conditional access works in simple terms",
    "build an integration with the ninjaone api to pull device inventory",
    "set up an mcp server so claude can read our confluence",
    "i want a local ai chatbot like promptmate using ollama with gemma",
    "deploy a cleanup script to all servers through ninjaone",
    "sumo logic query for failed vpn logins last 24 hours",
    "sentinelone flagged a powershell script on the cfo laptop",
    "force install an extension in chrome and edge for everyone",
    "spin up an azure vm in a new resource group for testing",
    "give marketing access to the events shared mailbox",
    "create a dlp policy in purview to block ssn in emails",
    "python script to parse iis logs and export errors to csv",
    "laptop bsod twice today after the latest windows update",
    "users macbook keychain keeps asking for password",
    "iphone wont get the new mdm wifi profile",
    "print queue stuck for everyone on the 2nd floor printer",
    "build a small web app for tracking loaner laptops",
    "nginx service keeps failing on the ubuntu box",
    "gpo drive mapping not applying to the sales ou",
    "need to migrate the hr file share to sharepoint",
    "regex to pull ticket numbers out of email subjects",
    "update prices in the sql server products table for vendor x",
    "make a mermaid diagram of our network topology",
    "audit our laptop inventory against intune",
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

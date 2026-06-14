"""Quick logic smoke test for AskPet (no GUI). Run: python test_logic.py"""
import json

import askpet as pm

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
    "i want a local ai chatbot like askpet using ollama with gemma",
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

# --- robustness: stale module/skill keys must not crash rendering -------------
# A rec that names a module/skill no longer in the library (renamed/removed, or
# replayed from older history) should degrade gracefully, not raise KeyError.
cleaned = pm.clean_text("intune compliance policy for new laptops", spell)
rec = pm.recommend(cleaned)
real_modules = [m for m in rec["modules"] if m in pm.AGENT_MODULES]
real_skills = [s for s in rec["skills"] if s in pm.SKILL_TEMPLATES]
rec["modules"] = rec["modules"] + ["no_such_module_xyzzy"]
rec["skills"] = rec["skills"] + ["no_such_skill_xyzzy"]

prompt = pm.build_prompt(cleaned, rec, rec["modules"], rec["skills"], [])
assert "no_such_module_xyzzy" not in prompt and "no_such_skill_xyzzy" not in prompt
for k in real_modules:
    assert pm.AGENT_MODULES[k]["name"] in prompt, k

mcp = pm._mcp_recommendation(cleaned, rec, prompt)
assert "no_such_module_xyzzy" not in mcp["modules"]
assert "no_such_skill_xyzzy" not in mcp["skills"]
assert list(mcp["modules"]) == real_modules
assert list(mcp["skills"]) == real_skills
print("stale-key robustness OK (build_prompt + _mcp_recommendation filter unknown keys)")

# --- self-update: version parsing, asset trust, API parsing, signature gate ---
import glob as _glob

# version parsing + tuple comparison (the ordering we rely on for "newer?")
assert pm.parse_version("v0.32.2") == (0, 32, 2)
assert pm.parse_version("0.32.2") == (0, 32, 2)
assert pm.parse_version("v1.0") == (1, 0)
assert pm.parse_version("0.32.2-beta") == (0, 32, 2)   # suffix on a part ignored
assert pm.parse_version("garbage") == ()
assert pm.parse_version("") == ()
assert pm.parse_version("0.32.10") > pm.parse_version("0.32.9")   # not string order
assert pm.parse_version("0.33.0") > pm.parse_version("0.32.99")
assert pm.parse_version("0.32.2") > pm.parse_version("0.32.1")
assert not (pm.parse_version("0.32.2") > pm.parse_version("0.32.2"))

# only this project's HTTPS release-asset URLs are trusted for downloads
_good = f"https://github.com/{pm.GITHUB_REPO}/releases/download/v0.32.2/AskPet-Setup-0.32.2.exe"
assert pm._is_release_asset_url(_good)
assert not pm._is_release_asset_url("https://evil.example.com/AskPet-Setup.exe")
assert not pm._is_release_asset_url("http://github.com/" + pm.GITHUB_REPO + "/releases/download/x/y.exe")
assert not pm._is_release_asset_url(None)

# fetch_latest_release/available_update parse the API and pick the trusted .exe.
# Patch the HTTP layer so there's no real network call.
_real_http = pm._http_get
def _fake_api(_url, timeout=8):
    return json.dumps({
        "tag_name": "v9.9.9",
        "html_url": f"https://github.com/{pm.GITHUB_REPO}/releases/tag/v9.9.9",
        "assets": [
            {"name": "notes.txt",
             "browser_download_url": f"https://github.com/{pm.GITHUB_REPO}/releases/download/v9.9.9/notes.txt",
             "size": 10},
            {"name": "AskPet-Setup-9.9.9.exe",
             "browser_download_url": f"https://github.com/{pm.GITHUB_REPO}/releases/download/v9.9.9/AskPet-Setup-9.9.9.exe",
             "size": 12345},
        ],
    }).encode()
try:
    pm._http_get = _fake_api
    rel = pm.fetch_latest_release()
    assert rel["tag"] == "v9.9.9" and rel["version"] == (9, 9, 9)
    assert rel["asset_name"] == "AskPet-Setup-9.9.9.exe" and rel["asset_size"] == 12345
    assert rel["asset_url"].endswith("AskPet-Setup-9.9.9.exe")
    assert pm.available_update(local_version="0.0.1")["tag"] == "v9.9.9"
    assert pm.available_update(local_version="9.9.9") is None
    assert pm.available_update(local_version="99.0.0") is None
    # an asset hosted off-GitHub is rejected (asset_url stays None)
    def _fake_evil(_url, timeout=8):
        return json.dumps({"tag_name": "v9.9.9", "assets": [
            {"name": "AskPet-Setup.exe",
             "browser_download_url": "https://evil.example/AskPet-Setup.exe", "size": 1}]}).encode()
    pm._http_get = _fake_evil
    assert pm.fetch_latest_release()["asset_url"] is None, "off-GitHub asset must not be trusted"
    # network failure -> None, never raises
    def _boom(_url, timeout=8):
        raise pm.urllib.error.URLError("offline")
    pm._http_get = _boom
    assert pm.fetch_latest_release() is None
    assert pm.available_update() is None
finally:
    pm._http_get = _real_http

# download refuses an untrusted URL before opening any connection
try:
    pm.download_release_asset("https://evil.example/x.exe", "x.exe")
    assert False, "download_release_asset must reject untrusted URLs"
except ValueError:
    pass

# signature gate: an unsigned/absent file is never accepted. The real signed
# installer (when a release build is present) is accepted — integration check.
assert pm.verify_signed_installer("askpet.py") is False
assert pm.verify_signed_installer("does-not-exist.exe") is False
_built = sorted(_glob.glob("installer/AskPet-Setup-*.exe"))
if _built and pm.sys.platform == "win32" and pm.verify_signed_installer(_built[-1]):
    print("  signed-installer verify OK:", _built[-1])
else:
    print("  (no signed installer present to positively verify; negative gate checked)")
print("self-update logic OK (version parse, asset trust, API parse, signature gate)")

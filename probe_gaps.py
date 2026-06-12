#!/usr/bin/env python3
"""Gap probe: send chats about topics the library may NOT cover yet and
flag weak results, to decide which agent modules/skills to add next.

Weak = no topic matched, generic template, default-only modules, or no
skills. Dev tool, offline."""

from test_mcp import McpClient

DEFAULT_MODULES = {"plan_first", "harness", "validation"}
GENERIC_TEMPLATES = {"chatgpt_planning", "codex_execution"}

PROBES = [
    ("voip", "set up a new auto attendant in teams phone"),
    ("voip", "port our phone numbers over to teams calling"),
    ("voip", "desk phone wont register with the pbx"),
    ("email_auth", "our emails keep landing in spam, check spf and dkim"),
    ("email_auth", "set up dmarc reporting for our domain"),
    ("firewall", "add a fortigate rule for the new vlan"),
    ("firewall", "palo alto is blocking sharepoint for some users"),
    ("aws", "create an s3 bucket with versioning for backups"),
    ("aws", "ec2 instance keeps running out of disk"),
    ("vdi", "citrix sessions freeze for remote users"),
    ("vdi", "set up windows 365 cloud pcs for contractors"),
    ("sccm", "migrate app deployment from sccm to intune"),
    ("jamf", "enroll the design teams macbooks in jamf"),
    ("passwords", "roll out 1password to the whole company"),
    ("passwords", "set up bitwarden collections for the helpdesk team"),
    ("awareness", "set up a knowbe4 phishing simulation campaign"),
    ("nas", "synology nas is running out of space"),
    ("sftp", "automate the nightly sftp transfer of payroll files"),
    ("wifi_gear", "unifi access points keep rebooting"),
    ("wifi_gear", "add a guest network on the meraki dashboard"),
    ("av_rooms", "teams room device offline in conference room b"),
    ("copilot", "deploy m365 copilot to a pilot group"),
    ("hris", "sync new hires from workday into entra"),
    ("domains", "renew our domain and move the nameservers"),
    ("containers", "dockerize our internal flask app"),
    ("containers", "deploy the api to kubernetes"),
    ("licensing", "true up our microsoft enterprise agreement"),
    ("esign", "docusign integration with sharepoint"),
    ("privacy", "respond to a gdpr data subject access request"),
    ("powerbi", "power bi dashboard for helpdesk ticket trends"),
    ("rooms", "set up room booking calendars for the new office"),
    ("appreg", "create an entra app registration with graph permissions"),
    ("winserver", "set up dhcp failover on windows server"),
    ("badges", "add new employees to the badge access system"),
    ("ups", "plan ups battery replacements for the server room"),
    ("vendor_mgmt", "prepare for the annual microsoft license renewal negotiation"),
]


def main():
    c = McpClient()
    gaps, ok = [], []
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18",
                                 "capabilities": {},
                                 "clientInfo": {"name": "probe", "version": "0"}})
        c.notify("notifications/initialized")
        for area, message in PROBES:
            r = c.call_tool("ask", {"message": message})
            if r["type"] == "help_answer":
                print(f"[{area:10s}] {message!r} -> HELP answer (unexpected)")
                continue
            mods = list(r["modules"])
            sks = list(r["skills"])
            flags = []
            if r["template"] in GENERIC_TEMPLATES:
                flags.append("generic-template")
            if set(mods) <= DEFAULT_MODULES:
                flags.append("default-modules-only")
            if not sks:
                flags.append("no-skills")
            line = (f"[{area:10s}] {message!r}\n"
                    f"    template={r['template']} modules=[{','.join(mods)}] "
                    f"skills=[{','.join(sks)}]")
            if flags:
                gaps.append((area, message, flags))
                print(line + f"\n    *** GAP: {', '.join(flags)}")
            else:
                ok.append(area)
                print(line)
    finally:
        c.close()
    print(f"\n{len(PROBES)} probes: {len(gaps)} flagged gaps, {len(ok)} covered.")
    areas = {}
    for area, msg, flags in gaps:
        areas.setdefault(area, []).append(flags)
    if areas:
        print("Gap areas:", ", ".join(sorted(areas)))


if __name__ == "__main__":
    main()

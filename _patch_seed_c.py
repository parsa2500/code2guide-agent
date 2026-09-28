# -*- coding: utf-8 -*-
from pathlib import Path

p = Path("src/app/services/agent_seed.py")
text = p.read_text(encoding="utf-8")

old_specs = '''SEED_SPECS = (
    {
        "id": DEFAULT_AGENT_JARVIS_ID,
        "name": DEFAULT_AGENT_JARVIS_NAME,
        "kind": AgentKind.JARVIS,
    },
    {
        "id": DEFAULT_CHATBOT_USER_ID,
        "name": DEFAULT_CHATBOT_USER_NAME,
        "kind": AgentKind.END_USER,
    },
    {
        "id": DEFAULT_CHATBOT_TECH_ID,
        "name": DEFAULT_CHATBOT_TECH_NAME,
        "kind": AgentKind.TECHNICAL,
    },
)
'''

new_block = '''# Slice-2 demo: overridable keys so WS agent-settings tab is not empty.
DEFAULT_SEED_SETTINGS_SCHEMA = {
    "clarify_first": {"default": False, "workspace_overridable": True},
    "max_hits": {"default": 5, "workspace_overridable": True},
    "policy_text": {"default": "", "workspace_overridable": True},
}

SEED_SPECS = (
    {
        "id": DEFAULT_AGENT_JARVIS_ID,
        "name": DEFAULT_AGENT_JARVIS_NAME,
        "kind": AgentKind.JARVIS,
    },
    {
        "id": DEFAULT_CHATBOT_USER_ID,
        "name": DEFAULT_CHATBOT_USER_NAME,
        "kind": AgentKind.END_USER,
    },
    {
        "id": DEFAULT_CHATBOT_TECH_ID,
        "name": DEFAULT_CHATBOT_TECH_NAME,
        "kind": AgentKind.TECHNICAL,
    },
)
'''

if "DEFAULT_SEED_SETTINGS_SCHEMA" not in text:
    if old_specs not in text:
        raise SystemExit("SEED_SPECS block not found")
    text = text.replace(old_specs, new_block, 1)

# create path: settings_schema={}
text = text.replace(
    "settings_schema={},",
    "settings_schema=dict(DEFAULT_SEED_SETTINGS_SCHEMA),",
    1,
)

# update path for existing seeds: also refresh settings_schema
old_update = '''            repo.update_fields(
                spec["id"],
                name=spec["name"],
                kind=spec["kind"],
                published=True,
                updated_at=now,
            )'''
new_update = '''            repo.update_fields(
                spec["id"],
                name=spec["name"],
                kind=spec["kind"],
                published=True,
                settings_schema=dict(DEFAULT_SEED_SETTINGS_SCHEMA),
                updated_at=now,
            )'''
if old_update in text:
    text = text.replace(old_update, new_update, 1)
elif "settings_schema=dict(DEFAULT_SEED_SETTINGS_SCHEMA)" not in text.split("update_fields")[1][:400]:
    raise SystemExit("update_fields block not patched")

p.write_text(text, encoding="utf-8")
print("seed patched")

# wire max_hits in chat
wp = Path("src/app/services/workspace_agent_service.py")
wt = wp.read_text(encoding="utf-8")
if "hits = brain_tools.search(self.db, workspace_id, cleaned, k=5)" in wt:
    wt = wt.replace(
        "hits = brain_tools.search(self.db, workspace_id, cleaned, k=5)",
        "k = int(effective.get(\"max_hits\", 5) or 5)\n"
        "            k = max(1, min(k, 20))\n"
        "            hits = brain_tools.search(self.db, workspace_id, cleaned, k=k)",
        1,
    )
    wp.write_text(wt, encoding="utf-8")
    print("chat max_hits wired")
else:
    print("chat search line not found or already patched")

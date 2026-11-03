"""Create the local pilot company and agents using the authenticated API."""
import json
from admin_api import Admin, ROOT

admin = Admin().login()
companies = admin.api("GET", "/api/companies")
company = next((c for c in companies if c["name"] == "KrishAdmin Local AI Lab"), None)
if not company:
    company = admin.api("POST", "/api/companies", {
        "name": "KrishAdmin Local AI Lab",
        "description": "Internal Paperclip pilot. Coordinator routes tasks to local AMD-GPU and NVIDIA-GPU inference; operator reviews deliverables.",
    })
cid = company["id"]
existing = admin.api("GET", f"/api/companies/{cid}/agents")
agents = {}
for key, name, role, backend, mode, description in [
    ("coordinator", "Local Coordinator", "ceo", "nvidia-gpu", "coordinator", "Routes tasks to AMD-GPU Analyst or NVIDIA-GPU Assistant. Assign new tasks here when you want automatic model selection."),
    ("amd-gpu", "AMD-GPU Analyst", "researcher", "amd-gpu", "specialist", "Large-model analysis, planning, architecture and code review using Qwen 2.5 72B Q8. Works from supplied task content; returns results for human review."),
    ("nvidia-gpu", "NVIDIA-GPU Assistant", "general", "nvidia-gpu", "specialist", "Fast summaries, extraction, rewriting and short answers using Qwen 3.5 9B. Works from supplied task content; returns results for human review."),
]:
    agent = next((a for a in existing if a["name"] == name), None)
    if not agent:
        payload = {
            "name": name, "role": role, "title": name, "capabilities": description,
            "adapterType": "process",
            "adapterConfig": {"command": "python3", "args": ["/opt/hq-agents/local_agent.py"],
                "cwd": "/paperclip", "timeoutSec": 540,
                "env": {"HQ_MODE": mode, "HQ_BACKEND": backend}},
            "runtimeConfig": {"heartbeat": {"enabled": False, "intervalSec": 0,
                "wakeOnDemand": True, "maxConcurrentRuns": 1, "maxDailyRuns": 100}},
            "permissions": {"canCreateAgents": False, "canCreateSkills": False},
        }
        if key != "coordinator":
            payload["reportsTo"] = agents["coordinator"]["id"]
        agent = admin.api("POST", f"/api/companies/{cid}/agents", payload)
    agents[key] = agent
targets_path = ROOT / "agents/targets.json"
targets = json.loads(targets_path.read_text()) if targets_path.exists() else {}
targets.update({k: v["id"] for k, v in agents.items() if k != "coordinator"})
(ROOT / "agents/targets.json").write_text(json.dumps(targets, indent=2) + "\n")
state_path = ROOT / "instance.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
state.update({"company_id": cid, "company_prefix": company.get("issuePrefix")})
state.setdefault("agents", {}).update({k: v["id"] for k, v in agents.items()})
(ROOT / "instance.json").write_text(json.dumps(state, indent=2) + "\n")
print(json.dumps(state, indent=2))

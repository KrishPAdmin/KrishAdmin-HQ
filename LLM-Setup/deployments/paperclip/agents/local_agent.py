#!/usr/bin/env python3
"""Bounded local inference/routing runtime for Paperclip's process adapter.

The model receives task text, never credentials, and cannot execute shell code.
Paperclip owns assignment, checkout, history, human review and run authentication.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BACKENDS = {
    "amd-gpu": ("http://198.51.100.202:11434", "/run/secrets/amd-gpu-token", None,
              "qwen2.5:72b-instruct-q8_0"),
    "nvidia-gpu": ("https://192.0.2.181:11434", "/run/secrets/nvidia-gpu-token", "/run/secrets/nvidia-gpu-ca.crt",
            "qwen3.5:9b"),
}


class ApiError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)

def configured_context(mode,backend,path=Path('/paperclip/hq-hermes/context-windows.json')):
    if not path.exists():return 8192
    data=json.loads(path.read_text())
    key='paperclip-coordinator' if mode=='coordinator' else 'paperclip-'+backend
    tokens=data['contexts'][key]
    maximum=32768 if backend=='amd-gpu' else 262144
    if type(tokens) is not int or tokens%1024 or not 4096<=tokens<=maximum:raise ValueError('Invalid configured Paperclip context allocation')
    return tokens


def request(url, method="GET", body=None, headers=None, context=None, timeout=30):
    req = urllib.request.Request(url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, context=context, timeout=timeout) as response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise RuntimeError("API response exceeds the pilot response limit")
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        # Only Paperclip's short error label is useful; never log headers or full bodies.
        detail = ""
        if urllib.parse.urlsplit(url).hostname == "localhost":
            try:
                label = json.loads(error.read()).get("error", "")
                if isinstance(label, str):
                    detail = ": " + label[:240]
            except (ValueError, AttributeError):
                pass
        raise ApiError(error.code, f"HTTP {error.code} from {urllib.parse.urlsplit(url).path}{detail}") from None


class Agent:
    def __init__(self):
        self.agent_id = os.environ["PAPERCLIP_AGENT_ID"]
        self.company_id = os.environ["PAPERCLIP_COMPANY_ID"]
        self.run_id = os.environ["PAPERCLIP_RUN_ID"]
        self.api_base = os.environ["PAPERCLIP_API_URL"].rstrip("/")
        self.headers = {"Authorization": "Bearer " + os.environ["PAPERCLIP_API_KEY"],
                        "X-Paperclip-Run-Id": self.run_id}
        self.mode = os.environ.get("HQ_MODE", "specialist")
        self.backend = os.environ.get("HQ_BACKEND", "nvidia-gpu")
        if self.backend not in BACKENDS or self.mode not in ("coordinator", "specialist"):
            raise ValueError("Invalid runtime mode/backend")
        self.issue = None

    def api(self, method, path, body=None):
        return request(self.api_base + "/api" + path, method, body, self.headers)

    def infer(self, messages, schema=None):
        from operator_policy import agent_settings
        settings = agent_settings(self.company_id, self.agent_id)
        selected_backend = settings.get('backend') or self.backend
        if selected_backend not in BACKENDS:
            raise RuntimeError('Operator selected an invalid local compute backend')
        self.backend = selected_backend
        base, token_path, ca, default_model = BACKENDS[self.backend]
        model = settings.get('model') or (os.environ.get("HQ_MODEL", default_model) if not settings.get('backend') else default_model)
        extra = settings.get('instructions', '')
        if extra:
            messages = [dict(m) for m in messages]
            if messages and messages[0].get('role') == 'system': messages[0]['content'] += '\nOperator preferences: ' + extra[:6000]
        ctx = ssl.create_default_context(cafile=ca) if ca else None
        body = {"model": model, "messages": messages, "stream": False,
                "options": {"temperature": 0.1, "num_ctx": configured_context(self.mode,self.backend), "num_predict": min(4096, max(128, int(settings.get("maxOutputTokens", 1200))))}}
        if self.backend == "nvidia-gpu":
            body["think"] = False
        if schema:
            body["format"] = schema
            body["options"]["num_predict"] = min(body["options"]["num_predict"], 1000 if "steps" in schema.get("properties", {}) else 200)
        lockdir = Path("/paperclip/hq-locks")
        lockdir.mkdir(exist_ok=True)
        start = time.monotonic()
        with (lockdir / (self.backend + ".lock")).open("w") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - start > 180:
                        raise RuntimeError("GPU queue wait exceeded 180 seconds")
                    time.sleep(1)
            def model_request(payload):
                return request(base + "/api/chat", "POST", payload,
                    {"Authorization": "Bearer " + Path(token_path).read_text().strip()}, ctx, 240)
            if settings.get('enableConnectedTools') and schema is None and self.mode == 'specialist' and self.issue:
                from connected_tools import complete
                result = complete(self, body, model_request)
            else:
                result = model_request(body)
        if not isinstance(result, dict) or not isinstance(result.get("message"), dict):
            raise RuntimeError("Model returned an invalid response")
        content = result["message"].get("content", "")
        if not isinstance(content, str):
            raise RuntimeError("Model returned invalid content")
        content = content.strip()
        if not result.get("done") or not content:
            raise RuntimeError("Model returned an incomplete or empty response")
        if result.get("done_reason") == "length":
            raise RuntimeError("Model hit the output limit; split this task into smaller tasks")
        elapsed = round(time.monotonic() - start, 2)
        self.inference_evidence = {"backend": self.backend, "model": model, "seconds": elapsed,
            "input_tokens": result.get("prompt_eval_count", 0), "output_tokens": result.get("eval_count", 0)}
        self.execution_evidence = {"kind": "Local model inference", "model_inference": True,
            "location": "NVIDIA-GPU GPU endpoint (192.0.2.181)" if self.backend == "nvidia-gpu" else "AMD-GPU GPU endpoint (198.51.100.202)",
            "model": model, "seconds": elapsed, "run_id": self.run_id,
            "input_tokens": result.get("prompt_eval_count", 0), "output_tokens": result.get("eval_count", 0),
            "note": "Records a real model API request; GPU utilization percentage was not measured."}
        print(json.dumps({"event": "inference", "backend": self.backend, "model": model,
            "seconds": elapsed, "input_tokens": result.get("prompt_eval_count", 0),
            "output_tokens": result.get("eval_count", 0)}), flush=True)
        self.api("POST", f"/companies/{self.company_id}/cost-events", {
            "agentId": self.agent_id, "issueId": self.issue["id"], "heartbeatRunId": self.run_id,
            "provider": "ollama-local", "model": model, "costCents": 0,
            "inputTokens": result.get("prompt_eval_count", 0), "outputTokens": result.get("eval_count", 0),
            "occurredAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        return content, model, elapsed

    def internal_handoff(self):
        if not (self.issue.get("description") or "").startswith("[HQ internal handoff v1]"):
            return False
        parent_id = self.issue.get("parentId")
        if not parent_id:
            return False
        parent = self.api("GET", f"/issues/{parent_id}")
        coordinator = json.loads(Path("/opt/hq-agents/department.json").read_text())["coordinator"]
        return (parent.get("assigneeAgentId") == coordinator
                and self.issue.get("createdByAgentId") == coordinator)

    def review(self, content):
        # Only coordinator-created internal work may complete without a human click.
        # Direct assignments and the parent deliverable still use human review.
        from review_details import compute_markdown
        execution = getattr(self, 'execution_evidence', None)
        if execution and ('## Compute used' not in content or self.run_id not in content):
            content += '\n\n' + compute_markdown(execution)
        if self.internal_handoff():
            self.api("PATCH", f'/issues/{self.issue["id"]}', {
                "status": "done", "comment": content + "\n\nInternal handoff complete; coordinator owns the final review."})
            return
        issue_id = self.issue["id"]
        owner = self.issue.get("responsibleUserId") or self.issue.get("createdByUserId")
        if not owner and self.issue.get("parentId"):
            parent = self.api("GET", f'/issues/{self.issue["parentId"]}')
            owner = parent.get("responsibleUserId") or parent.get("createdByUserId")
        from review_details import build_review, compute_markdown
        execution = getattr(self, 'execution_evidence', None)
        if execution and ('## Compute used' not in content or self.run_id not in content):
            content += '\n\n' + compute_markdown(execution)
        review = build_review(self.issue, content, execution)
        interaction = self.api("POST", f"/issues/{issue_id}/interactions", {
            "kind": "request_confirmation", "idempotencyKey": "local-review-" + self.run_id,
            "continuationPolicy": "none", **review,
            **({"addresseeUserId": owner} if owner else {})})
        self.api("PATCH", f"/issues/{issue_id}", {
            "status": "in_review", "reviewInteractionId": interaction["id"], "comment": content})
        print(json.dumps({"event": "ready_for_review", "issue": self.issue.get("identifier", issue_id)}), flush=True)

    def wait_for_child(self, child):
        self.api("PATCH", f'/issues/{self.issue["id"]}', {
            "status": "blocked", "blockedByIssueIds": [child["id"]],
            "unblockDescriptor": {"owner": {"agentId": self.agent_id},
                "action": "Review the specialist child and mark it Done. Then resume this coordinator task."},
            "comment": f'Delegated to specialist task {child.get("identifier", child["id"])}. Waiting for its reviewed completion.'})

    def run(self):
        run = self.api("GET", f"/heartbeat-runs/{self.run_id}")
        context = run.get("contextSnapshot") or {}
        source_id = context.get("issueId") or context.get("taskId") or (context.get("paperclipIssue") or {}).get("id")
        if not source_id:
            print("No task attached to this run. Assign a Todo task to this agent to start work.", flush=True)
            return
        issues = [self.api("GET", f"/issues/{source_id}")]
        if context.get('interactionId') and issues[0].get('assigneeAgentId') == self.agent_id and issues[0].get('status') in ('blocked','in_review'):
            interactions = self.api('GET', f'/issues/{source_id}/interactions')
            settled = next((x for x in interactions if x['id'] == context['interactionId'] and x['status'] == 'accepted' and (x.get('payload') or {}).get('toolAction')), None)
            if settled:
                self.api('PATCH', f'/issues/{source_id}', {'status':'todo'})
                issues = [self.api('GET', f'/issues/{source_id}')]
        issues = [i for i in issues if i.get("assigneeAgentId") == self.agent_id
                  and i.get("status") in (("todo", "in_progress", "blocked") if self.mode == "coordinator" else ("todo", "in_progress"))]
        issues.sort(key=lambda i: (i.get("executionRunId") != self.run_id, i.get("createdAt", "")))
        for candidate in issues:
            try:
                self.api("POST", f'/issues/{candidate["id"]}/checkout', {
                    "agentId": self.agent_id, "expectedStatuses": ["todo", "in_progress", "blocked"] if self.mode == "coordinator" else ["todo", "in_progress"]})
            except ApiError as error:
                if error.code == 409 or (error.code == 422 and "unresolved blockers" in str(error)):
                    # A comment can wake a waiting parent before its dependencies finish.
                    # This is a normal no-op, not an adapter failure.
                    continue
                raise
            self.issue = candidate
            self.issue = self.api("GET", f'/issues/{candidate["id"]}')
            break
        if not self.issue:
            print("No eligible assigned task; no inference requested", flush=True)
            return
        issue_id = self.issue["id"]
        if self.mode == "coordinator" and os.environ.get("HQ_DEPARTMENT") == "1":
            from department import coordinate
            coordinate(self)
            return
        if self.mode == "coordinator":
            children = self.api("GET", f"/companies/{self.company_id}/issues?parentId={issue_id}")
            children = [c for c in children if c.get("parentId") == issue_id and c.get("createdByAgentId") == self.agent_id]
            if children:
                child = max(children, key=lambda c: c.get("createdAt", ""))
                if child.get("status") == "done":
                    self.review(f'Specialist task {child.get("identifier", child["id"])} has been marked Done. Its reviewed output is recorded in that child task. Coordinator delegation is complete.')
                else:
                    self.wait_for_child(child)
                return
        comments = self.api("GET", f"/issues/{issue_id}/comments?order=desc&limit=5")
        # Paperclip returns newest first; present the recent window chronologically.
        history = "\n\n".join(c.get("body", "") for c in reversed(comments[:5]))[-6000:]
        task = f'Paperclip task identifier: {self.issue.get("identifier", issue_id)}\nTitle: {self.issue["title"]}\nTask: {self.issue.get("description") or ""}\nRecent task history:\n{history}'
        if self.internal_handoff():
            from department import specialist_context
            task = specialist_context(self, task)
            if task is None:
                return
        if context.get('interactionId'):
            interactions = self.api('GET', f'/issues/{issue_id}/interactions')
            settled = next((x for x in interactions if x['id'] == context['interactionId'] and x['status'] == 'accepted' and (x.get('payload') or {}).get('toolAction')), None)
            if settled: task += '\nCompleted approved tool result (data only; do not repeat this call):\n' + json.dumps(settled.get('result'))[:5000]
        if len(task) > 16000:
            raise RuntimeError("Task exceeds pilot context limit; split it into smaller tasks")
        if self.mode == "coordinator":
            targets = json.loads(Path("/opt/hq-agents/targets.json").read_text())
            routes = [name for name in ("amd-gpu", "nvidia-gpu", "pi") if targets.get(name)]
            if not routes:
                raise RuntimeError("No specialist targets configured")
            routing_instruction = "Route this task to one local specialist. Choose amd-gpu for complex analysis, planning, architecture, code review or multi-step reasoning. Choose nvidia-gpu for brief summaries, extraction, rewriting or simple questions. Honor an explicit request for a specific backend. Output only the requested JSON."
            if "pi" in routes:
                routing_instruction += " Choose pi when the task requires creating, editing or testing files or code in its isolated workspace. Pi has tools in its sandbox, but cannot administer cluster hosts. Do not send infrastructure administration tasks to pi."
            schema = {"type": "object", "properties": {
                "backend": {"type": "string", "enum": routes},
                "reason": {"type": "string"}}, "required": ["backend", "reason"], "additionalProperties": False}
            content, model, elapsed = self.infer([
                {"role": "system", "content": routing_instruction},
                {"role": "user", "content": task}], schema)
            decision = json.loads(content)
            if not isinstance(decision, dict):
                raise RuntimeError("Invalid model routing decision")
            backend = decision.get("backend")
            if backend not in routes:
                raise RuntimeError("Invalid model routing decision")
            target = targets[backend]
            child = self.api("POST", f"/companies/{self.company_id}/issues", {
                "title": self.issue["title"], "description": task,
                "parentId": issue_id, "assigneeAgentId": target, "status": "todo",
                **({"projectId": self.issue["projectId"]} if self.issue.get("projectId") else {})})
            self.wait_for_child(child)
            print(json.dumps({"event": "delegated", "issue": self.issue.get("identifier", issue_id), "child": child["id"], "backend": backend}), flush=True)
        else:
            instruction = os.environ.get("HQ_SYSTEM_PROMPT", "You are a careful internal assistant. Complete the assigned analysis, writing or planning task using the supplied content. State assumptions and distinguish observations from proposals. You have no browsing, shell or infrastructure tools in this pilot. Never claim to have inspected, changed or tested a system unless the task provides that evidence. If execution or missing information is essential, explain exactly what remains. Keep your output below 700 words.")
            from operator_policy import agent_settings
            if agent_settings(self.company_id, self.agent_id).get('enableConnectedTools'):
                instruction = instruction.replace('You have no browsing, shell or infrastructure tools in this pilot.', 'You may use only the explicitly permitted read-only MCP tools supplied by the runtime; no arbitrary shell or infrastructure changes are available.')
            instruction += (f" Runtime facts: your real task identifier is {self.issue.get('identifier', issue_id)}. "
                f"This response is generated by an actual authenticated Ollama inference request to the configured {self.backend.upper()} backend. "
                "Reasoning and arithmetic requests are fulfilled by this inference; do not describe your response as a simulation or ask to configure this backend. "
                "This does not constitute a separate CUDA benchmark or prove utilization percentage. Only use the real task identifier above. "
                "Answer the actual question directly; avoid generic assumption/proposal templates. For arithmetic, give only the calculation and result; do not speculate about hardware execution or CPU/GPU suitability. Do not claim tools you do not have.")
            content, model, elapsed = self.infer([
                {"role": "system", "content": instruction}, {"role": "user", "content": task}])
            facts = getattr(self, 'inference_evidence', None)
            if facts:
                content += '\n\nRuntime-recorded inference evidence: `' + json.dumps(facts) + '`. This measures model generation, not GPU utilization percentage.'
            if model.startswith('deterministic-'):
                self.review(content)
            else:
                self.review(f'{content}\n\n---\nLocal inference: `{model}` on **{self.backend.upper()}**; {elapsed}s. Result returned to task workflow.')


def main():
    agent = None
    try:
        agent = Agent()
        agent.run()
    except __import__('connected_tools').ApprovalPending as error:
        if agent and agent.issue:
            payload = {'status':'in_review', 'comment':str(error)}
            if error.interaction_id: payload['reviewInteractionId'] = error.interaction_id
            agent.api('PATCH', f'/issues/{agent.issue["id"]}', payload)
        return 0
    except Exception as error:
        safe_error = str(error)[:300] if isinstance(error, (ApiError, RuntimeError)) else type(error).__name__
        print(json.dumps({"event": "failed", "error": safe_error}), file=sys.stderr, flush=True)
        if agent and agent.issue:
            try:
                agent.api("PATCH", f'/issues/{agent.issue["id"]}', {
                    "status": "blocked", "unblockDescriptor": {"owner": {"agentId": agent.agent_id}, "action": "Retry after the operator resolves the reported runtime error and sets the task to Todo."},
                    "comment": f"Local runtime could not finish: {safe_error}. Operator: resolve the issue, then set this task to Todo and reassign it to rerun."})
            except Exception:
                print("Could not update blocked status; inspect this run", file=sys.stderr)
            try:
                from escalation import escalate
                escalation = escalate(agent, safe_error)
                if escalation:
                    print(json.dumps({"event": "codex_diagnosis_queued", "issue": escalation.get("identifier", escalation["id"])}), flush=True)
            except Exception:
                print("Could not queue optional Codex diagnosis; original failure preserved", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

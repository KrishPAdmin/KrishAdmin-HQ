import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("local_agent", Path(__file__).parent / "agents/local_agent.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "PAPERCLIP_AGENT_ID": "agent", "PAPERCLIP_COMPANY_ID": "company",
            "PAPERCLIP_RUN_ID": "run", "PAPERCLIP_API_URL": "http://localhost:3100",
            "PAPERCLIP_API_KEY": "test-secret", "HQ_BACKEND": "nvidia-gpu", "HQ_MODE": "specialist"})
        self.env.start()
        self.addCleanup(self.env.stop)
        targets = patch.object(runtime.Path, "read_text", return_value='{"amd-gpu":"amd-gpu-agent","nvidia-gpu":"nvidia-gpu-agent"}')
        targets.start()
        self.addCleanup(targets.stop)

    def test_no_work_does_not_call_model(self):
        agent = runtime.Agent()
        with patch.object(agent, "api", return_value={"contextSnapshot": {}}), patch.object(agent, "infer") as infer:
            agent.run()
            infer.assert_not_called()

    def test_checkout_conflict_does_not_run_task(self):
        agent = runtime.Agent()
        task = {"id": "task", "assigneeAgentId": "agent", "status": "todo"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, runtime.ApiError(409, "conflict")]), patch.object(agent, "infer") as infer:
            agent.run()
            infer.assert_not_called()

    def test_result_goes_to_human_review_without_credentials_in_prompt(self):
        agent = runtime.Agent()
        task = {"id": "task", "identifier": "TEST-1", "title": "Summarize", "description": "Example",
                "assigneeAgentId": "agent", "status": "todo", "responsibleUserId": "operator"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [], {"id": "review"}, {}]) as api, patch.object(agent, "infer", return_value=("Result", "local-model", 1)) as infer:
            agent.run()
            payload = api.call_args.args[2]
            self.assertEqual(payload["status"], "in_review")
            self.assertNotIn("assigneeUserId", payload)
            self.assertNotIn("assigneeAgentId", payload)
            self.assertEqual(payload["reviewInteractionId"], "review")
            self.assertEqual(api.call_args_list[-2].args[2]["addresseeUserId"], "operator")
            self.assertNotIn("test-secret", str(infer.call_args))

    def test_invalid_route_cannot_reassign(self):
        os.environ["HQ_MODE"] = "coordinator"
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "assigneeAgentId": "agent", "status": "todo"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [], []]) as api, patch.object(agent, "infer", return_value=('{"backend":"external"}', "local", 1)):
            with self.assertRaisesRegex(RuntimeError, "Invalid model routing"):
                agent.run()
            self.assertEqual(api.call_count, 6)

    def test_recent_comments_are_presented_oldest_to_newest(self):
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "assigneeAgentId": "agent", "status": "todo"}
        comments = [{"body": f"comment-{i}"} for i in range(6, 0, -1)]
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, comments, {"id": "review"}, {}]) as api, patch.object(agent, "infer", return_value=("Result", "local", 1)) as infer:
            agent.run()
            self.assertEqual(api.call_args_list[4].args[1], "/issues/task/comments?order=desc&limit=5")
            prompt = infer.call_args.args[0][1]["content"]
            self.assertNotIn("comment-1", prompt)
            self.assertLess(prompt.index("comment-2"), prompt.index("comment-6"))

    def test_oversized_task_does_not_infer(self):
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "description": "x" * 16001,
                "assigneeAgentId": "agent", "status": "todo"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, []]), patch.object(agent, "infer") as infer:
            with self.assertRaisesRegex(RuntimeError, "context limit"):
                agent.run()
            infer.assert_not_called()

    def test_failed_inference_marks_task_blocked(self):
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "assigneeAgentId": "agent", "status": "todo"}
        with patch.object(runtime, "Agent", return_value=agent), patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [], {}]) as api, patch.object(agent, "infer", side_effect=RuntimeError("GPU unavailable")):
            self.assertEqual(runtime.main(), 1)
            self.assertEqual(api.call_args.args[2]["status"], "blocked")
            self.assertIn("GPU unavailable", api.call_args.args[2]["comment"])

    def test_initialization_failure_exits_cleanly(self):
        with patch.object(runtime, "Agent", side_effect=ValueError("invalid configuration")):
            self.assertEqual(runtime.main(), 1)

    def test_completed_task_is_not_run_again(self):
        agent = runtime.Agent()
        task = {"id": "task", "assigneeAgentId": "agent", "status": "in_review"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task]), patch.object(agent, "infer") as infer:
            agent.run()
            infer.assert_not_called()

    def test_existing_child_prevents_duplicate_delegation(self):
        os.environ["HQ_MODE"] = "coordinator"
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "assigneeAgentId": "agent", "status": "blocked"}
        child = {"id": "child", "parentId": "task", "createdByAgentId": "agent", "status": "in_review"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [child], {}]) as api, patch.object(agent, "infer") as infer:
            agent.run()
            infer.assert_not_called()
            self.assertEqual(api.call_args.args[2]["blockedByIssueIds"], ["child"])
            self.assertNotIn("assigneeAgentId", api.call_args.args[2])

    def test_done_child_sends_parent_to_review_without_inference(self):
        os.environ["HQ_MODE"] = "coordinator"
        agent = runtime.Agent()
        task = {"id": "task", "title": "Task", "assigneeAgentId": "agent", "status": "blocked"}
        child = {"id": "child", "parentId": "task", "createdByAgentId": "agent", "status": "done"}
        with patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [child], {"id": "review"}, {}]) as api, patch.object(agent, "infer") as infer:
            agent.run()
            infer.assert_not_called()
            self.assertEqual(api.call_args.args[2]["status"], "in_review")
            self.assertNotIn("assigneeAgentId", api.call_args.args[2])

    def test_gpu_queue_timeout_does_not_send_request(self):
        agent = runtime.Agent()
        with patch.object(runtime, "Path"), patch.object(runtime.ssl, "create_default_context"), patch.object(runtime.fcntl, "flock", side_effect=BlockingIOError), patch.object(runtime.time, "monotonic", side_effect=[0, 181]), patch.object(runtime, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "GPU queue wait"):
                agent.infer([])
            request.assert_not_called()

    def test_truncated_model_response_is_not_success(self):
        agent = runtime.Agent()
        with patch.object(runtime, "Path"), patch.object(runtime.ssl, "create_default_context"), patch.object(runtime.fcntl, "flock"), patch.object(runtime, "request", return_value={"message": {"content": "Partial result"}, "done": True, "done_reason": "length"}), patch.object(agent, "api") as api:
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                agent.infer([])
            api.assert_not_called()

    def test_optional_pi_target_delegates_without_gpu_endpoint(self):
        os.environ["HQ_MODE"] = "coordinator"
        agent = runtime.Agent()
        task = {"id": "task", "title": "Create a file", "assigneeAgentId": "agent", "status": "todo"}
        with patch.object(runtime.Path, "read_text", return_value='{"amd-gpu":"amd-gpu-agent","nvidia-gpu":"nvidia-gpu-agent","pi":"pi-agent"}'), patch.object(agent, "api", side_effect=[{"contextSnapshot": {"issueId": "task"}}, task, {}, task, [], [], {"id": "child"}, {}]) as api, patch.object(agent, "infer", return_value=('{"backend":"pi","reason":"Workspace file task"}', "local", 1)) as infer:
            agent.run()
            self.assertIn("pi", infer.call_args.args[1]["properties"]["backend"]["enum"])
            self.assertEqual(api.call_args_list[-2].args[2]["assigneeAgentId"], "pi-agent")
            self.assertEqual(api.call_args_list[-2].args[2]["parentId"], "task")
            self.assertNotIn("responsibleUserId", api.call_args_list[-2].args[2])
            self.assertEqual(api.call_args.args[2]["blockedByIssueIds"], ["child"])


if __name__ == "__main__":
    unittest.main()

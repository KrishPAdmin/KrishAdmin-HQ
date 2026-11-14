# Context windows and operator controls

Verified against the installed Ollama model metadata on 2026-11-09. These are configured per-request windows in tokens, not the current conversation length. 1K here means 1,024 tokens. A GPU system has no single universal context window: each model/request selects an allocation. Loaded allocation is transient shared model state and can differ from the next request's setting.

| Agent / runtime | GPU | Model | Configured tokens | Installed model maximum | CLI target |
|---|---|---|---:|---:|---|
| Donna Discord coordinator | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | concierge |
| Jessica Pearson | AMD-GPU | Mixtral 8x22B q4_K_M | 65,536 | 65,536 | jessica |
| Harvey Specter | AMD-GPU | Gemma2 27B q8_0 | 8,192 | 8,192 | harvey |
| Louis Litt | AMD-GPU | Qwen2.5 Coder 32B q8_0 | 32,768 | 32,768 | louis |
| Mike Ross | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | mike |
| Rachel Zane | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | rachel |
| Donna Paulsen specialist | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | donna |
| Deep analyst / Mike escalation | AMD-GPU | Qwen2.5 72B q8_0 | 32,768 | 32,768 | analyst |
| NVIDIA-GPU health worker | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | health |
| NVIDIA-GPU backup worker | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | backup |
| NVIDIA-GPU triage worker | NVIDIA-GPU | Qwen3.5 9B | 65,536 | 262,144 | triage |
| Paperclip Local Coordinator | NVIDIA-GPU | Qwen3.5 9B | 8,192 | 262,144 | paperclip-coordinator |
| Paperclip NVIDIA-GPU Assistant | NVIDIA-GPU | Qwen3.5 9B | 8,192 | 262,144 | paperclip-nvidia-gpu |
| Paperclip AMD-GPU Analyst | AMD-GPU | Qwen2.5 72B q8_0 | 8,192 | 32,768 | paperclip-amd-gpu |
| Benjamin — Suits Implementation Engineer | NVIDIA-GPU | paperclip-qwen3.5:9b | 16,384 | 262,144 | pi |

Hermes Lab Health, Backup Watch and Incident Triage in Paperclip use the AMD-GPU analyst by default; their optional NVIDIA-GPU execution uses the corresponding health/backup/triage worker. Hermes HQ Dispatcher is intake-only. System Health Observer, System Diagnostics, Network Discovery, HQ Host Checker, NVIDIA-GPU GPU Checker and AMD-GPU GPU Checker use deterministic probes and have no model window. Codex Escalation Engineer uses its selected external provider; local context controls do not change that provider. The dashboard lists every registered agent, including those non-model runtimes and the external agent's current Paperclip state.

Legacy Paperclip model overrides in Controls are independent of these default model assignments. If selecting a different legacy model/backend, verify that model's own limit; the operator CLI validates the installed default models listed above. It cannot establish that an arbitrary future override fits. No default window was permanently increased by this update.

## Read the actual settings

On HQ:

```bash
cd /home/operator/krishadmin-hq/deployments/hermes
python3 contextctl.py show
python3 contextctl.py show --json
```

The CLI queries the broker and installed model metadata, and shows configured versus loaded allocations. Discord users can ask **what is the current context window sitting at?** or **show context windows**. A fixed native workflow reads `hq_status` with `view: context`; it does not invent a model's context size. Exact used/remaining tokens for the current Discord session are not measured by this check.

## Modify a window

```bash
python3 contextctl.py set louis 16384
python3 contextctl.py set louis 16384 --apply
python3 contextctl.py reset louis --apply
python3 contextctl.py reset all --apply
```

Without `--apply`, set/reset/rollback commands are previews. Values must be multiples of 1,024 and within the installed model maximum. Direct specialists can use at least 4,096 tokens; the native Hermes coordinator/health/backup/triage workers retain a 65,536-token floor because the pinned Hermes runtime requires at least 64,000. Above 65,536 on NVIDIA-GPU also requires `--experimental`; this acknowledges an unvalidated larger allocation, not guaranteed GPU fit:

```bash
python3 contextctl.py set mike 131072 --experimental
```

Changing a window does not remove bounded file, source excerpt, transport, input-byte or output-token limits. Input limits remain conservative; the JSON view includes specialist input-byte budgets. A context window includes instructions, history, evidence and output. Bigger windows require more memory and can increase latency or cause allocation failure. See [Ollama context documentation](https://docs.ollama.com/context-length).

## Apply and rollback behavior

The authoritative non-secret file is `config/context-windows.json`. Runtimes read it for each request. The CLI validates it, verifies live native model limits, saves private snapshots, updates Hermes profile metadata and synchronizes the Paperclip legacy-worker mirror. The broker requests the selected `num_ctx` and checks GPU residency before/after inference. Each compute receipt records requested and reported context allocations. An in-flight request finishes with its original allocation.

Changing `concierge` or `jessica` also updates the Discord compression configuration and restarts the gateway using its normal maintenance notices. The default compression trigger is 30,000 tokens; decreasing Jessica's window lowers that trigger. Specialist-only changes do not restart the Discord bot. Agents sharing a model can request different windows; switching sizes may reload that model.

Pi uses an Ollama alias and its own model registry. Changing `pi` updates only the existing `paperclip-qwen3.5:9b` alias through fixed operator SSH access, preserving its template and other model parameters; the inference proxy remains closed to model management. It then updates the Pi registry and recreates the Pi worker so the file mount is current. Apply a Pi change when that worker is idle. No tasks are automatically rerun.

Each successful apply prints a snapshot ID:

```bash
python3 contextctl.py rollback SNAPSHOT_ID
python3 contextctl.py rollback SNAPSHOT_ID --apply
```

Rollback restores the saved window values into the current profiles, preserving unrelated settings. Unknown/malformed values and missing snapshots are rejected. Failed multi-file writes restore previous files; a failed service restart or uncertain remote alias update is reported for reconciliation. Snapshots can contain private provider configuration and are excluded from GitHub.

## Verification

A live Harvey request used 4,096 tokens and returned a GPU-backed receipt; his configured window was then restored to 8,192. Pi's alias was changed to 8,192, its original template hash was preserved, and the setting was restored to 16,384. The exact Discord question passed the native Hermes workflow with the correct 65,536-token response and an explicit usage limitation. These are allocation/control tests, not maximum-window quality benchmarks or a claim that 256K fits on NVIDIA-GPU.

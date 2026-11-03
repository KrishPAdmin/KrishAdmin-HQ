---
name: hq-diagnostics
description: Collect fresh fixed host, GPU driver, CPU/memory, process, service and storage diagnostics on HQ, NVIDIA-GPU and AMD-GPU without arbitrary SSH or repair commands.
---
Use `hq_diagnostics` with target `hq`, `nvidia-gpu` or `amd-gpu` and one check: `overview`, `gpu`, `processes`, `services`, `storage`.
Choose `gpu` for nvidia-smi, rocm-smi, driver versions, temperature, GPU use or VRAM. Choose `processes` for top/htop-style tables. CPU percentages use a one-second delta; `overview` also samples vmstat over one second. Interactive htop is not run.
Report the collection timestamp, actual target and observed values. Missing binaries, permissions or enrollment are unavailable coverage, not proof of broken hardware. Never claim these checks repaired anything. For expert interpretation pass a short evidence summary to Louis, Harvey or Jessica, preserving uncertainties.
HQ holds credentials. NVIDIA-GPU uses a source-restricted forced-command observer. AMD-GPU uses the owner's chosen password authentication as krishadmin; HQ enforces the fixed command list. No browsing or outbound research runs on AMD-GPU. Do not request, print, or include credentials in tool arguments. Arbitrary shell, process killing, service restarts, driver installation/reset and unfiltered logs are outside this tool.

For supported SSH process requests, execute the fixed check directly; do not preface with a blanket inability to SSH. `processes` now returns a one-second CPU delta (100% = one logical CPU), excluding the collector process. Use cpu_processes.rows for CPU ranking. Never infer GPU inference from CPU percentages, process names or old model lists. Identify sample time and limits.

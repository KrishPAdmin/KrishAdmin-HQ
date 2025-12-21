# KrishAdmin-HQ

A practical home-lab repo: scripts + service configs I use in my KrishAdmin-HQ environment.

- Lab overview and context: https://server.krishadmin.com

## What this repo is

This repository is a working “ops notebook” for my homelab. It includes a mix of:
- Container stacks (Swarm and Kubernetes)
- Networking helper scripts
- Utility scripts for keeping services repeatable and easy to redeploy

If you are cloning this repo to reuse ideas, treat it as reference infrastructure: read configs before running them, and replace my hostnames, paths, and IPs with yours.

## Repo layout

Top-level directories currently in this repo:

```text
.
├── Docker-Swarm/
├── K3S/
│   └── Traefik-Reverse-Proxy/
├── Media-Server/
│   └── qbittorrent/
├── Networking-Scripts/
├── Scripts/
└── README.md

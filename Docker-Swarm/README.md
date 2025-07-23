# Raspberry Pi Swarm — Service Layout & Ops Guide

## Cluster at a Glance
| Node (hostname) | Swarm Role | Pinned Services |
|-----------------|------------|-----------------|
| pi‑cluster‑mgr  | Manager    | Portainer (UI), NFS server, global agent |
| pi‑01           | Manager    | Nginx Proxy Manager |
| pi‑02           | Manager    | Uptime Kuma |
| pi‑03           | Manager    | Prometheus, Grafana |
| pi‑04           | Worker     | Glance Homepage |
| pi‑05           | Worker     | Home Assistant |
| **All nodes**   | –          | Portainer Agent (global) |

Services are pinned via node **labels** (e.g. `node.labels.kuma == true`).

## Shared Storage

A single NFS export (`/srv/docker‑nfs`) is mounted on **every** node at  
`/mnt/nfs`.  
Each app gets its own sub‑directory

### Overlay Networks

| Name          | Purpose                     |
|---------------|-----------------------------|
| `proxy_net`   | Public‑facing services via NPM |
| `backend_net` | Portainer ↔ agent traffic      |
| `monitoring_net` | Prometheus ↔ Grafana ↔ Kuma ↔ Netdata |

Create them **once** (on any manager):

```bash
docker network create --driver overlay --attachable proxy_net
docker network create --driver overlay --attachable backend_net
docker network create --driver overlay --attachable monitoring_net


| Task                         | Command                                                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Show nodes & roles           | `docker node ls`                                                                                                        |
| Show stacks                  | `docker stack ls`                                                                                                       |
| Show services in *one* stack | `docker stack services <stack>`                                                                                         |
| Quick status for all stacks  | <br>`for s in $(docker stack ls -q); do`<br>`  docker stack services $s --format '{{.Name}}\t{{.Replicas}}';`<br>`done` |
| Inspect a failing task       | `docker service ps <service> --no-trunc`                                                                                |
| Tail logs                    | `docker service logs <service> --raw --tail 100`                                                                        |
| Force‑restart a service      | `docker service update --force <service>`                                                                               |
| Rotate a node label          | `docker node update --label-add kuma=true <nodeID>`                                                                     |

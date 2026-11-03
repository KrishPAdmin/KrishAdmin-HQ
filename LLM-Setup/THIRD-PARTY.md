# Upstream components

This directory contains integration/configuration work around existing projects. Upstream repositories and binary dependencies are not vendored; their licenses and distribution terms remain applicable.

- [Hermes Agent](https://github.com/NousResearch/hermes-agent): pinned revision/image in `deployments/hermes/release.json`.
- [Paperclip](https://github.com/paperclipai/paperclip): image pinned in `deployments/paperclip/compose.yaml`.
- [n8n](https://github.com/n8n-io/n8n), [Ollama](https://github.com/ollama/ollama), PostgreSQL, nginx, Docker and Open WebUI are referenced by deployment configuration.
- Included Source Sans font assets retain `deployments/openwebui-gateway/theme/SourceSans-OFL.txt`.
- Suits character names label internal agent personas. No character images or TV assets are included, and no affiliation is claimed.

Review model-specific licenses separately before reuse or distribution. Container/image references do not distribute model weights.

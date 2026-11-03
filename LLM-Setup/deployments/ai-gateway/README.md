# AI gateway

Hostname: hq-gateway
LAN: 192.0.2.21/24; router/DNS: 192.0.2.1
ZeroTier: 198.51.100.21, network b103a835d223e15b
Remote GPU host: 198.51.100.202

## Endpoints

- Web UI: http://192.0.2.21:3000 (existing remote OpenWebUI accounts)
- OpenAI-compatible API base: http://192.0.2.21:11434/v1
- Native Ollama API: http://192.0.2.21:11434/api/

Nginx binds only the LAN address and allows 192.0.2.0/24.
It forwards the caller's Authorization header; clients must use the existing
remote API token. Nginx does not store or inject a token. The user supplied a
local token file at ~/.codex/projects/secrets/ollama-api-token.txt for testing.
WebSocket upgrade and unbuffered response streaming are configured.
Access logs omit query strings and Authorization headers.
Both nginx and ZeroTier are enabled at boot.

## Deployment status (2026-09-19)

- nginx configuration validated; gateway UI returned HTTP 200.
- Remote relay installed by user; remote and gateway APIs return HTTP 401 without a token.
- Gateway also returns HTTP 401 with an invalid bearer token.
- Web UI health endpoint returns {"status":true}.
- ai-api-proxy-zt.service relays only gateway 198.51.100.21 to the existing
  token-authenticated LAN API.
- Authenticated native and OpenAI-compatible model lists returned HTTP 200 (6 models).
- Streamed /v1/chat/completions returned HTTP 200 using the already-loaded
  mixtral:8x22b-instruct-v0.1-q4_K_M model; response: "Gateway is working."
- Stream completed with [DONE]; first content 0.56 seconds, total 0.75 seconds
  for this short warm-model smoke test. Token was not printed or copied into config.

## Files and checks

Active configuration: /etc/nginx/sites-available/ai-gateway
Source copy: /home/operator/ai-gateway/nginx.conf
Network backup and original nginx default link: /root/ai-gateway-backup

    sudo nginx -t
    systemctl status nginx zerotier-one
    sudo zerotier-cli listnetworks
    curl -I http://192.0.2.21:3000/
    curl -i http://192.0.2.21:11434/v1/models

The unauthenticated model request should return 401 once the remote relay works.
Remote API token remains at /opt/ai-stack/secrets/api_token.txt on the GPU host.

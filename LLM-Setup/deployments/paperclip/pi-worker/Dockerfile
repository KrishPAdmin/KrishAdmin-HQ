FROM node:24-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates git curl && rm -rf /var/lib/apt/lists/* && npm install -g @earendil-works/pi-coding-agent@0.74.0
WORKDIR /opt/worker
COPY . ./
RUN mkdir -p /workspace /paperclip/hq-locks /home/node/.pi/agent && cp models.json /home/node/.pi/agent/models.json && chown -R node:node /workspace /paperclip /home/node/.pi
USER node
ENV NODE_EXTRA_CA_CERTS=/run/secrets/nvidia-gpu-ca.crt PI_OFFLINE=1 PI_TELEMETRY=0 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
CMD ["python3", "/opt/worker/worker.py"]

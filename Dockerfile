# SAMPLE. Not built or tested on the box (no Docker run was done). Standard library only, so no pip install.
FROM python:3.13-slim
RUN useradd --create-home --uid 10001 gateway
WORKDIR /app
COPY gateway/ gateway/
USER gateway
ENV GATEWAY_STATE=/home/gateway/state.json GATEWAY_AUDIT=/home/gateway/audit.jsonl
# MCP_BEARER must be supplied at run time; the server refuses to start without it (exit 3).
ENTRYPOINT ["python", "-m", "gateway.server"]

FROM docker/sandbox-templates:shell

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Root-owned; executable by agent for development inside the sandbox.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /usr/local/bin/

ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app
RUN chown agent:agent /app

COPY --chown=agent:agent pyproject.toml uv.lock ./

USER agent

RUN uv sync --locked --no-dev --no-install-project

COPY --chown=agent:agent app.py ./

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

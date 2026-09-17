FROM docker/sandbox-templates:shell

USER root

RUN apt-get update \
    && apt-get install -y curl git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

USER agent
"""OpenCode Go coding agent: clai -a go_coder:agent (without -m)."""

import os
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai_harness import Coder


# One ID per CLI conversation, shared by all requests and retries.
session_id = os.environ.get("OPENCODE_SESSION_ID") or str(uuid4())
client = AsyncOpenAI(
    api_key=os.environ["OPENCODE_API_KEY"],
    base_url="https://opencode.ai/zen/go/v1",
    default_headers={
        "User-Agent": "pydantic-go-coder/1.0",
        "x-opencode-session": session_id,
    },
)
agent = Agent(
    OpenAIChatModel(
        os.environ.get("OPENCODE_MODEL", "deepseek-v4-flash"),
        provider=OpenAIProvider(openai_client=client),
        settings={"extra_headers": {"User-Agent": "pydantic-go-coder/1.0"}},
    ),
    name="coder",
    instructions="You are a coding agent built on Pydantic AI.",
    capabilities=[Coder()],
)

import os
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


def main():
    client = AsyncOpenAI(
        api_key=os.environ["OPENCODE_API_KEY"],
        base_url="https://opencode.ai/zen/go/v1",
        default_headers={
            "User-Agent": "my-pydantic-agent/1.0",
            "x-opencode-session": str(uuid4()),
        },
    )

    provider = OpenAIProvider(openai_client=client)

    model = OpenAIChatModel(
        "glm-5.3",
        provider=provider,
    )

    agent = Agent(model)

    result = agent.run_sync("Hello!")
    print(result.output)


if __name__ == "__main__":
    main()

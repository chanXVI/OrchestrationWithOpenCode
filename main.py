import os
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai_harness import Advisor, Coder
from pydantic_ai.providers import infer_provider_class


def main():
    client = AsyncOpenAI(
        api_key=os.environ["OPENCODE_API_KEY"],
        base_url="https://opencode.ai/zen/go/v1",
        default_headers={
            "User-Agent": "my-pydantic-agent/1.0",
            "x-opencode-session": str(uuid4()),
        },
    )

    # provider = OpenAIProvider(openai_client=client)
    provider = infer_provider_class("openai")
    provider = provider(openai_client=client)

    model = OpenAIChatModel(
        "deepseek-v4-flash",
        provider=provider,
    )

    agent = Agent(
        model,
        capabilities=[Coder(), Advisor(model)],
    )

    result = agent.run_sync("Hello, what llm model an I currently running?")
    print(result.output)


if __name__ == "__main__":
    main()

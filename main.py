# from agents import Agent, Runner
import os
from uuid import uuid4
from openai import AsyncOpenAI
from agents import (
    Agent,
    Runner,
    OpenAIResponsesModel,
    set_tracing_disabled,
)


def main():

    # agent = Agent(name="Assistant", instructions="You are a helpful assistant")

    # result = Runner.run_sync(agent, "Write a haiku about recursion in programming.")
    # print(result.final_output)

    # # Code within the code,
    # # Functions calling themselves,
    # # Infinite loop's dance.
    # print("Hello from opencodesandbox!")

    client = AsyncOpenAI(
        api_key=os.environ["OPENCODE_API_KEY"],
        base_url="https://opencode.ai/zen/go/v1",
        default_headers={
            # Keep this ID stable across all requests in this conversation.
            "x-opencode-session": str(uuid4()),
            "User-Agent": "opencodesandbox/0.1.0",
        },
    )

    model = OpenAIResponsesModel(
        model="gpt-5.6-luna",
        openai_client=client,
    )

    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
        model=model,
    )

    set_tracing_disabled(True)

    result = Runner.run_sync(agent, "Explain Kubernetes in two sentences.")

    print(result.final_output)


if __name__ == "__main__":
    main()

import json
from pathlib import Path
from typing import Any, cast

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

OPENAI_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "openai.json"

SYSTEM_PROMPT = """You are a parking reservation assistant.

Answer ONLY using the provided context.

If the answer cannot be found in the context, say that you do not have enough \
information.

Do not invent information.

Keep answers concise and helpful."""


def create_llm() -> AzureChatOpenAI:
    try:
        config: Any = json.loads(OPENAI_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"OpenAI configuration file not found: {OPENAI_CONFIG_PATH}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid OpenAI configuration in {OPENAI_CONFIG_PATH}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise ValueError("Invalid OpenAI configuration: expected a JSON object")

    required_fields = ("model", "api_base", "api_key")

    if any(
        field not in config or not isinstance(config[field], str)
        for field in required_fields
    ):
        raise ValueError(
            "Invalid OpenAI configuration: model, api_base, and api_key must be strings"
        )

    if not config["model"].strip():
        raise ValueError("Invalid OpenAI configuration: model must not be empty")

    if not config["api_base"].strip():
        raise ValueError("Invalid OpenAI configuration: api_base must not be empty")

    if not config["api_key"].strip():
        raise ValueError("Invalid OpenAI configuration: api_key must not be empty")

    return AzureChatOpenAI(
        azure_endpoint=config["api_base"],
        azure_deployment=config["model"],
        api_key=config["api_key"],
        api_version="2024-08-01-preview",
    )


def build_prompt(
    question: str,
    retrieved_documents: list[Document],
) -> list[BaseMessage]:
    context = "\n\n".join(document.page_content for document in retrieved_documents)
    human_prompt = f"""Question:
{question}

Context:
{context}"""

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ]


def generate_answer(
    question: str,
    retrieved_documents: list[Document],
) -> str:
    if not question.strip():
        raise ValueError("question must not be empty")
    if not retrieved_documents:
        raise ValueError("retrieved_documents must not be empty")

    response = create_llm().invoke(build_prompt(question, retrieved_documents))
    return cast(str, response.content).strip()

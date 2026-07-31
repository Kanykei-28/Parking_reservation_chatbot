import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import SecretStr

from parking_chatbot.rag import build_prompt, create_llm, generate_answer, generator


def test_create_llm_loads_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "openai.json"
    config_path.write_text(
        json.dumps(
            {
                "model": "test-model",
                "api_base": "https://example.com/v1",
                "api_key": "test-key",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "OPENAI_CONFIG_PATH", config_path)

    llm = create_llm()

    assert llm.deployment_name == "test-model"
    assert isinstance(llm.openai_api_key, SecretStr)
    assert llm.openai_api_key.get_secret_value() == "test-key"


@pytest.mark.parametrize("question", ["", "   "])
def test_generate_answer_rejects_empty_question(question: str) -> None:
    with pytest.raises(ValueError, match="question"):
        generate_answer(question, [Document(page_content="Parking context")])


def test_generate_answer_rejects_empty_document_list() -> None:
    with pytest.raises(ValueError, match="retrieved_documents"):
        generate_answer("Where is the parking?", [])


def test_build_prompt_contains_question_and_document_content_without_metadata() -> None:
    documents = [
        Document(
            page_content="Covered parking costs 75 KGS per hour.",
            metadata={"source": "secret-source.md"},
        ),
        Document(
            page_content="The parking is open every day.",
            metadata={"chunk_index": 4},
        ),
    ]

    messages = build_prompt("How much is covered parking?", documents)

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "How much is covered parking?" in messages[1].content
    assert documents[0].page_content in messages[1].content
    assert documents[1].page_content in messages[1].content
    assert "secret-source.md" not in messages[1].content
    assert "chunk_index" not in messages[1].content


def test_generate_answer_returns_stripped_mocked_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocked_llm = MagicMock()
    mocked_llm.invoke.return_value = AIMessage(content="  The answer. \n")
    monkeypatch.setattr(generator, "create_llm", lambda: mocked_llm)

    answer = generate_answer(
        "What is the answer?",
        [Document(page_content="The answer.")],
    )

    assert answer == "The answer."
    mocked_llm.invoke.assert_called_once()

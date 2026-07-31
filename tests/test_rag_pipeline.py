from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from parking_chatbot.rag import pipeline


@pytest.fixture
def mocked_pipeline_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    vector_store = MagicMock()
    retrieve_documents = MagicMock()
    generate_answer = MagicMock()
    monkeypatch.setattr(pipeline, "VECTOR_STORE", vector_store)
    monkeypatch.setattr(pipeline, "retrieve_documents", retrieve_documents)
    monkeypatch.setattr(pipeline, "generate_answer", generate_answer)
    return vector_store, retrieve_documents, generate_answer


def test_answer_question_returns_generated_answer(
    mocked_pipeline_dependencies: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    vector_store, retrieve_documents, generate_answer = mocked_pipeline_dependencies
    documents = [Document(page_content="Parking is open daily.")]
    retrieve_documents.return_value = documents
    generate_answer.return_value = "Parking is open daily."

    result = pipeline.answer_question("What are the parking hours?")

    assert result == "Parking is open daily."
    retrieve_documents.assert_called_once_with(
        vector_store,
        "What are the parking hours?",
    )
    generate_answer.assert_called_once_with(
        "What are the parking hours?",
        documents,
    )


def test_answer_question_handles_empty_retrieval(
    mocked_pipeline_dependencies: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    vector_store, retrieve_documents, generate_answer = mocked_pipeline_dependencies
    retrieve_documents.return_value = []

    result = pipeline.answer_question("What parking information is available?")

    assert result == "I couldn't find any relevant information."
    retrieve_documents.assert_called_once_with(
        vector_store,
        "What parking information is available?",
    )
    generate_answer.assert_not_called()


@pytest.mark.parametrize("question", ["", "   "])
def test_answer_question_rejects_empty_question(
    question: str,
    mocked_pipeline_dependencies: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, retrieve_documents, generate_answer = mocked_pipeline_dependencies

    with pytest.raises(ValueError, match="^question must not be empty$"):
        pipeline.answer_question(question)

    retrieve_documents.assert_not_called()
    generate_answer.assert_not_called()

from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document
from langchain_milvus import Milvus

from parking_chatbot.evaluation.dataset import RetrievalQuestion
from parking_chatbot.evaluation.retrieval import evaluate_retrieval


def question(
    question_id: str,
    expected_source: str | None,
) -> RetrievalQuestion:
    return RetrievalQuestion(
        id=question_id,
        question=f"Question {question_id}",
        expected_source=expected_source,
        expected_facts=[],
    )


def documents(*sources: str) -> list[Document]:
    return [
        Document(page_content="", metadata={"source": source}) for source in sources
    ]


def test_hit_at_1_success(monkeypatch: pytest.MonkeyPatch) -> None:
    retrieve_documents = MagicMock(return_value=documents("expected.md", "other.md"))
    monkeypatch.setattr(
        "parking_chatbot.evaluation.retrieval.retrieve_documents",
        retrieve_documents,
    )
    vector_store = cast(Milvus, object())

    result = evaluate_retrieval(
        [question("q01", "expected.md")],
        vector_store,
    )

    assert result.hit_at_1 == 1.0
    assert result.hit_at_k == 1.0
    assert result.results[0].hit_at_1
    assert result.results[0].hit_at_k
    retrieve_documents.assert_called_once_with(
        vector_store,
        "Question q01",
        3,
    )


def test_hit_at_1_failure_but_hit_at_k_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "parking_chatbot.evaluation.retrieval.retrieve_documents",
        MagicMock(return_value=documents("other.md", "expected.md")),
    )

    result = evaluate_retrieval(
        [question("q01", "expected.md")],
        cast(Milvus, object()),
    )

    assert result.hit_at_1 == 0.0
    assert result.hit_at_k == 1.0
    assert not result.results[0].hit_at_1
    assert result.results[0].hit_at_k


def test_hit_at_k_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "parking_chatbot.evaluation.retrieval.retrieve_documents",
        MagicMock(return_value=documents("first.md", "second.md")),
    )

    result = evaluate_retrieval(
        [question("q01", "expected.md")],
        cast(Milvus, object()),
    )

    assert result.hit_at_1 == 0.0
    assert result.hit_at_k == 0.0
    assert not result.results[0].hit_at_1
    assert not result.results[0].hit_at_k


def test_multiple_questions_compute_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieve_documents = MagicMock(
        side_effect=[
            documents("first.md"),
            documents("other.md", "second.md"),
            documents("other.md"),
        ]
    )
    monkeypatch.setattr(
        "parking_chatbot.evaluation.retrieval.retrieve_documents",
        retrieve_documents,
    )

    result = evaluate_retrieval(
        [
            question("q01", "first.md"),
            question("q02", "second.md"),
            question("q03", "third.md"),
        ],
        cast(Milvus, object()),
        top_k=2,
    )

    assert result.total_questions == 3
    assert result.hit_at_1 == pytest.approx(1 / 3)
    assert result.hit_at_k == pytest.approx(2 / 3)
    assert [item.question_id for item in result.results] == [
        "q01",
        "q02",
        "q03",
    ]


def test_questions_without_expected_source_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieve_documents = MagicMock(return_value=documents("expected.md"))
    monkeypatch.setattr(
        "parking_chatbot.evaluation.retrieval.retrieve_documents",
        retrieve_documents,
    )

    result = evaluate_retrieval(
        [
            question("q01", None),
            question("q02", "expected.md"),
        ],
        cast(Milvus, object()),
    )

    assert result.total_questions == 1
    assert [item.question_id for item in result.results] == ["q02"]
    retrieve_documents.assert_called_once()


@pytest.mark.parametrize("top_k", [0, -1])
def test_rejects_non_positive_top_k(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        evaluate_retrieval([], cast(Milvus, object()), top_k=top_k)


def test_empty_dataset_returns_zero_metrics() -> None:
    result = evaluate_retrieval([], cast(Milvus, object()))

    assert result.total_questions == 0
    assert result.hit_at_1 == 0.0
    assert result.hit_at_k == 0.0
    assert result.results == []

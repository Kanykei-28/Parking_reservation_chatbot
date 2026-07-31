from dataclasses import dataclass

from langchain_milvus import Milvus

from parking_chatbot.evaluation.dataset import RetrievalQuestion
from parking_chatbot.rag.retriever import retrieve_documents


@dataclass(frozen=True)
class RetrievalResult:
    """Retrieval metrics for one evaluation question."""

    question_id: str
    expected_source: str
    retrieved_sources: list[str]
    hit_at_1: bool
    hit_at_k: bool


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """Aggregate metrics and per-question retrieval results."""

    total_questions: int
    hit_at_1: float
    hit_at_k: float
    results: list[RetrievalResult]


def evaluate_retrieval(
    questions: list[RetrievalQuestion],
    vector_store: Milvus,
    top_k: int = 3,
) -> RetrievalEvaluationResult:
    """Evaluate source retrieval accuracy for answerable questions."""
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    results: list[RetrievalResult] = []
    for question in questions:
        expected_source = question.expected_source
        if expected_source is None:
            continue

        retrieved_documents = retrieve_documents(
            vector_store,
            question.question,
            top_k,
        )

        retrieved_sources = [
            str(document.metadata.get("source", "")) for document in retrieved_documents
        ]
        hit_at_1 = bool(retrieved_sources and retrieved_sources[0] == expected_source)
        hit_at_k = expected_source in retrieved_sources
        results.append(
            RetrievalResult(
                question_id=question.id,
                expected_source=expected_source,
                retrieved_sources=retrieved_sources,
                hit_at_1=hit_at_1,
                hit_at_k=hit_at_k,
            )
        )

    total_questions = len(results)
    if total_questions == 0:
        return RetrievalEvaluationResult(
            total_questions=0,
            hit_at_1=0.0,
            hit_at_k=0.0,
            results=[],
        )

    successful_hit_at_1 = sum(result.hit_at_1 for result in results)
    successful_hit_at_k = sum(result.hit_at_k for result in results)
    return RetrievalEvaluationResult(
        total_questions=total_questions,
        hit_at_1=successful_hit_at_1 / total_questions,
        hit_at_k=successful_hit_at_k / total_questions,
        results=results,
    )

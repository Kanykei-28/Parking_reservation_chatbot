from dataclasses import dataclass

from parking_chatbot.evaluation.dataset import RetrievalQuestion
from parking_chatbot.rag import answer_question


@dataclass(frozen=True)
class GenerationResult:
    """Answer-quality result for one evaluation question."""

    question_id: str
    generated_answer: str
    expected_facts: tuple[str, ...]
    matched_facts: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class GenerationEvaluationResult:
    """Aggregate answer-quality evaluation results."""

    total_questions: int
    average_score: float
    results: tuple[GenerationResult, ...]


def evaluate_generation(
    questions: list[RetrievalQuestion],
) -> GenerationEvaluationResult:
    """Evaluate generated answers against their expected facts."""
    results: list[GenerationResult] = []

    for question in questions:
        answer = answer_question(question.question)
        normalized_answer = answer.casefold()

        matched_facts = tuple(
            fact
            for fact in question.expected_facts
            if fact.casefold() in normalized_answer
        )

        expected_facts = tuple(question.expected_facts)
        score = len(matched_facts) / len(expected_facts) if expected_facts else 1.0

        results.append(
            GenerationResult(
                question_id=question.id,
                generated_answer=answer,
                expected_facts=expected_facts,
                matched_facts=matched_facts,
                score=score,
            )
        )

    total_questions = len(results)
    average_score = (
        sum(result.score for result in results) / total_questions
        if total_questions
        else 0.0
    )

    return GenerationEvaluationResult(
        total_questions=total_questions,
        average_score=average_score,
        results=tuple(results),
    )

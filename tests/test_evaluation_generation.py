from unittest.mock import MagicMock, call

import pytest

from parking_chatbot.evaluation.dataset import RetrievalQuestion
from parking_chatbot.evaluation.generation import evaluate_generation


def question(
    question_id: str,
    text: str,
    expected_facts: list[str],
) -> RetrievalQuestion:
    return RetrievalQuestion(
        id=question_id,
        question=text,
        expected_source=None,
        expected_facts=expected_facts,
    )


def mock_answers(
    monkeypatch: pytest.MonkeyPatch,
    *answers: str,
) -> MagicMock:
    answer_question = MagicMock(side_effect=answers)
    monkeypatch.setattr(
        "parking_chatbot.evaluation.generation.answer_question",
        answer_question,
    )
    return answer_question


def test_all_expected_facts_are_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "Parking is open from 06:00 until 23:00.")

    result = evaluate_generation(
        [question("q01", "What are the hours?", ["06:00", "23:00"])]
    )

    assert result.results[0].matched_facts == ("06:00", "23:00")
    assert result.results[0].score == 1.0


def test_only_some_expected_facts_are_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "Payment by cash is available.")

    result = evaluate_generation([question("q01", "How can I pay?", ["cash", "card"])])

    assert result.results[0].matched_facts == ("cash",)
    assert result.results[0].score == 0.5


def test_matching_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "EV CHARGING is available.")

    result = evaluate_generation(
        [question("q01", "Can I charge my car?", ["ev charging"])]
    )

    assert result.results[0].matched_facts == ("ev charging",)
    assert result.results[0].score == 1.0


def test_no_expected_facts_are_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "The parking is open daily.")

    result = evaluate_generation([question("q01", "Where is it?", ["Central Avenue"])])

    assert result.results[0].matched_facts == ()
    assert result.results[0].score == 0.0


def test_empty_expected_facts_gives_full_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "No information is available.")

    result = evaluate_generation([question("q01", "Are subscriptions available?", [])])

    assert result.results[0].matched_facts == ()
    assert result.results[0].score == 1.0


def test_multiple_questions_compute_average_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(
        monkeypatch,
        "The hours are 06:00 and 23:00.",
        "Cash is accepted.",
        "No matching details.",
    )

    result = evaluate_generation(
        [
            question("q01", "What are the hours?", ["06:00", "23:00"]),
            question("q02", "How can I pay?", ["cash", "card"]),
            question("q03", "Where is it?", ["Central Avenue"]),
        ]
    )

    assert result.results[0].score == 1.0
    assert result.results[1].score == 0.5
    assert result.results[2].score == 0.0
    assert result.average_score == pytest.approx(0.5)


def test_empty_input_returns_empty_evaluation() -> None:
    result = evaluate_generation([])

    assert result.total_questions == 0
    assert result.average_score == 0.0
    assert result.results == ()


def test_generated_answer_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_answers(monkeypatch, "The generated answer.")

    result = evaluate_generation([question("q01", "A question?", [])])

    assert result.results[0].generated_answer == "The generated answer."


def test_answer_question_is_called_once_per_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer_question = mock_answers(monkeypatch, "First answer", "Second answer")
    questions = [
        question("q01", "First question", []),
        question("q02", "Second question", []),
    ]

    evaluate_generation(questions)

    assert answer_question.call_count == 2
    assert answer_question.call_args_list == [
        call("First question"),
        call("Second question"),
    ]

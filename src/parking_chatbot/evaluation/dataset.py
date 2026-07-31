import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetrievalQuestion:
    """A question and its expected retrieval evidence."""

    id: str
    question: str
    expected_source: str | None
    expected_facts: list[str]


def load_retrieval_questions(path: Path) -> list[RetrievalQuestion]:
    """Load retrieval questions from a JSON dataset."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("retrieval questions JSON root must be a list")

    required_fields = {
        "id",
        "question",
        "expected_source",
        "expected_facts",
    }
    questions: list[RetrievalQuestion] = []

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"retrieval question at index {index} must be an object")

        missing_fields = required_fields - item.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"retrieval question at index {index} is missing: {missing}"
            )

        expected_facts = item["expected_facts"]
        if not isinstance(expected_facts, list):
            raise ValueError(f"expected_facts at index {index} must be a list")

        if not all(isinstance(fact, str) for fact in expected_facts):
            raise ValueError(
                f"expected_facts at index {index} must contain only strings"
            )

        questions.append(
            RetrievalQuestion(
                id=item["id"],
                question=item["question"],
                expected_source=item["expected_source"],
                expected_facts=expected_facts,
            )
        )

    return questions

import json
from pathlib import Path

import pytest

from parking_chatbot.evaluation import (
    RetrievalQuestion,
    load_retrieval_questions,
)


def write_dataset(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_retrieval_questions_in_order(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    write_dataset(
        path,
        [
            {
                "id": "q01",
                "question": "Where is the parking located?",
                "expected_source": "location.md",
                "expected_facts": ["Central Avenue"],
            },
            {
                "id": "q02",
                "question": "Are subscriptions available?",
                "expected_source": None,
                "expected_facts": [],
            },
        ],
    )

    questions = load_retrieval_questions(path)

    assert questions == [
        RetrievalQuestion(
            id="q01",
            question="Where is the parking located?",
            expected_source="location.md",
            expected_facts=["Central Avenue"],
        ),
        RetrievalQuestion(
            id="q02",
            question="Are subscriptions available?",
            expected_source=None,
            expected_facts=[],
        ),
    ]


def test_loads_empty_dataset(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    write_dataset(path, [])

    assert load_retrieval_questions(path) == []


def test_rejects_non_list_json_root(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    write_dataset(path, {"questions": []})

    with pytest.raises(ValueError, match="root must be a list"):
        load_retrieval_questions(path)


@pytest.mark.parametrize(
    "missing_field",
    ["id", "question", "expected_source", "expected_facts"],
)
def test_rejects_missing_required_field(
    tmp_path: Path,
    missing_field: str,
) -> None:
    item = {
        "id": "q01",
        "question": "Where is the parking located?",
        "expected_source": "location.md",
        "expected_facts": ["Central Avenue"],
    }
    del item[missing_field]
    path = tmp_path / "questions.json"
    write_dataset(path, [item])

    with pytest.raises(ValueError, match=missing_field):
        load_retrieval_questions(path)


def test_rejects_non_list_expected_facts(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    write_dataset(
        path,
        [
            {
                "id": "q01",
                "question": "Where is the parking located?",
                "expected_source": "location.md",
                "expected_facts": "Central Avenue",
            }
        ],
    )


def test_rejects_non_string_expected_facts(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    write_dataset(
        path,
        [
            {
                "id": "q01",
                "question": "Where is the parking located?",
                "expected_source": "location.md",
                "expected_facts": ["Central Avenue", 123],
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="must contain only strings",
    ):
        load_retrieval_questions(path)

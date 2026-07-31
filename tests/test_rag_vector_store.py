from pathlib import Path

import pytest
from langchain_core.documents import Document

from parking_chatbot.rag import (
    create_vector_store,
    load_vector_store,
    retrieve_documents,
)


def test_create_vector_store_rejects_empty_documents(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="documents"):
        create_vector_store([], tmp_path / "parking.db")


def test_load_vector_store_rejects_missing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_vector_store(tmp_path / "missing.db")


def test_creates_loads_and_recreates_vector_store(tmp_path: Path) -> None:
    db_path = tmp_path / "vector_store" / "parking.db"
    documents = [
        Document(
            page_content="Covered parking costs 75 KGS per hour.",
            metadata={"source": "prices.md", "chunk_index": 0},
        ),
        Document(
            page_content="The parking is open from 06:00 to 23:00.",
            metadata={"source": "hours.md", "chunk_index": 0},
        ),
    ]

    create_vector_store(documents, db_path)
    assert db_path.is_file()

    loaded_store = load_vector_store(db_path)
    results = retrieve_documents(loaded_store, "covered parking price", top_k=2)
    assert results
    assert results[0].metadata["source"] == "prices.md"
    assert results[0].metadata["chunk_index"] == 0

    recreated_store = create_vector_store(documents, db_path)
    recreated_results = retrieve_documents(
        recreated_store, "parking information", top_k=10
    )
    assert len(recreated_results) == len(documents)

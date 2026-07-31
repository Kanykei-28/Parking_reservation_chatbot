from pathlib import Path
from typing import cast

import pytest
from langchain_core.documents import Document
from langchain_milvus import Milvus

from parking_chatbot.rag import create_vector_store, retrieve_documents


@pytest.fixture
def vector_store(tmp_path: Path) -> Milvus:
    documents = [
        Document(
            page_content="Covered parking costs 75 KGS per hour.",
            metadata={"source": "parking_types_and_prices.md", "chunk_index": 0},
        ),
        Document(
            page_content="The parking is at 123 Central Avenue, Bishkek.",
            metadata={"source": "location_and_hours.md", "chunk_index": 0},
        ),
        Document(
            page_content="Reservations can be made up to 5 days in advance.",
            metadata={"source": "reservation_rules.md", "chunk_index": 0},
        ),
    ]
    return create_vector_store(documents, tmp_path / "parking.db")


@pytest.mark.parametrize("query", ["", "   "])
def test_rejects_empty_query(query: str) -> None:
    unused_store = cast(Milvus, object())

    with pytest.raises(ValueError, match="query"):
        retrieve_documents(unused_store, query)


@pytest.mark.parametrize("top_k", [0, -1])
def test_rejects_non_positive_top_k(top_k: int) -> None:
    unused_store = cast(Milvus, object())

    with pytest.raises(ValueError, match="top_k"):
        retrieve_documents(unused_store, "parking", top_k=top_k)


def test_returns_relevant_documents_with_metadata(vector_store: Milvus) -> None:
    results = retrieve_documents(
        vector_store,
        "How much does covered parking cost?",
        top_k=2,
    )

    assert len(results) <= 2

    metadata = results[0].metadata

    assert metadata["source"] == "parking_types_and_prices.md"
    assert metadata["chunk_index"] == 0

    # Metadata should be preserved.
    assert "pk" in metadata

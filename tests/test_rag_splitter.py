import pytest
from langchain_core.documents import Document

from parking_chatbot.rag import split_documents


def test_empty_input_returns_empty_list() -> None:
    assert split_documents([]) == []


def test_short_document_remains_one_chunk() -> None:
    document = Document(page_content="Short document.", metadata={"source": "short.md"})

    chunks = split_documents([document])

    assert len(chunks) == 1
    assert chunks[0].page_content == "Short document."
    assert chunks[0].metadata["chunk_index"] == 0


def test_long_document_is_split_into_ordered_chunks() -> None:
    document = Document(
        page_content=" ".join(f"word-{index}" for index in range(100)),
        metadata={"source": "long.md"},
    )

    chunks = split_documents([document], chunk_size=80, chunk_overlap=10)

    assert len(chunks) > 1
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(
        range(len(chunks))
    )


def test_preserves_metadata_without_mutating_input() -> None:
    metadata = {
        "source": "rules.md",
        "path": "/data/static/rules.md",
        "document_type": "markdown",
    }
    document = Document(page_content="Reservation rules.", metadata=metadata)
    original_metadata = dict(document.metadata)

    chunks = split_documents([document])

    assert chunks[0].metadata == {**original_metadata, "chunk_index": 0}
    assert document.metadata == original_metadata
    assert "chunk_index" not in document.metadata


def test_chunk_index_resets_for_each_document() -> None:
    documents = [
        Document(page_content="First document.", metadata={"source": "first.md"}),
        Document(page_content="Second document.", metadata={"source": "second.md"}),
    ]

    chunks = split_documents(documents)

    assert [chunk.metadata["chunk_index"] for chunk in chunks] == [0, 0]


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_invalid_chunk_size_raises_value_error(chunk_size: int) -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        split_documents([], chunk_size=chunk_size)


def test_negative_chunk_overlap_raises_value_error() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_documents([], chunk_overlap=-1)


@pytest.mark.parametrize("chunk_overlap", [100, 101])
def test_large_chunk_overlap_raises_value_error(chunk_overlap: int) -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_documents([], chunk_size=100, chunk_overlap=chunk_overlap)

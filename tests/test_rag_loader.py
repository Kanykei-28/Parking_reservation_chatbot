from pathlib import Path

import pytest

from parking_chatbot.rag import load_markdown_documents

STATIC_DATA_DIRECTORY = Path(__file__).parents[1] / "data" / "static"


def test_loads_all_static_markdown_files_in_order() -> None:
    documents = load_markdown_documents(STATIC_DATA_DIRECTORY)

    sources = [document.metadata["source"] for document in documents]
    assert sources == [
        "faq.md",
        "general_information.md",
        "location_and_hours.md",
        "parking_types_and_prices.md",
        "reservation_rules.md",
    ]
    assert all(document.page_content for document in documents)


def test_sets_document_metadata() -> None:
    documents = load_markdown_documents(STATIC_DATA_DIRECTORY)

    for document in documents:
        source = document.metadata["source"]
        path = Path(document.metadata["path"])

        assert source == path.name
        assert "/" not in source
        assert document.metadata["document_type"] == "markdown"
        assert path.is_file()
        assert path.parent == STATIC_DATA_DIRECTORY.resolve()


def test_ignores_non_markdown_and_hidden_files(tmp_path: Path) -> None:
    (tmp_path / "visible.md").write_text("# Visible", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Ignore this", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("# Hidden", encoding="utf-8")

    documents = load_markdown_documents(tmp_path)

    assert [document.metadata["source"] for document in documents] == ["visible.md"]


def test_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_markdown_documents(tmp_path / "missing")


def test_file_path_raises_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "document.md"
    file_path.write_text("# Document", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        load_markdown_documents(file_path)


def test_empty_markdown_file_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("  \n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty.md"):
        load_markdown_documents(tmp_path)

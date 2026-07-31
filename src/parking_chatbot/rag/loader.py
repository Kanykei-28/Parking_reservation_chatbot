from pathlib import Path

from langchain_core.documents import Document


def load_markdown_documents(directory: Path) -> list[Document]:
    if not directory.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    markdown_files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix == ".md" and not path.name.startswith(".")
    )

    documents = []
    for path in markdown_files:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Markdown file is empty: {path.name}")

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": path.name,
                    "path": str(path.resolve()),
                    "document_type": "markdown",
                },
            )
        )

    return documents

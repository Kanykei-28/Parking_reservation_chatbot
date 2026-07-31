from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", " ", ""]


def split_documents(
    documents: list[Document],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[Document]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    if not documents:
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
    )

    chunks = []
    for document in documents:
        for chunk_index, text in enumerate(
            text_splitter.split_text(document.page_content)
        ):
            metadata = dict(document.metadata)
            metadata["chunk_index"] = chunk_index
            chunks.append(Document(page_content=text, metadata=metadata))

    return chunks

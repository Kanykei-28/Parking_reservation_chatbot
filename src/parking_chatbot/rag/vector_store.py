from collections.abc import Sequence
from pathlib import Path

from langchain_core.documents import Document
from langchain_milvus import Milvus

from parking_chatbot.rag.embeddings import create_embeddings

COLLECTION_NAME = "parking_knowledge"


def create_vector_store(
    documents: Sequence[Document],
    db_path: Path,
) -> Milvus:
    if not documents:
        raise ValueError("documents must not be empty")

    resolved_path = db_path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    return Milvus.from_documents(
        documents=list(documents),
        embedding=create_embeddings(),
        collection_name=COLLECTION_NAME,
        connection_args={"uri": str(resolved_path)},
        drop_old=True,
    )


def load_vector_store(db_path: Path) -> Milvus:
    resolved_path = db_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Vector database does not exist: {resolved_path}")

    return Milvus(
        embedding_function=create_embeddings(),
        collection_name=COLLECTION_NAME,
        connection_args={"uri": str(resolved_path)},
    )

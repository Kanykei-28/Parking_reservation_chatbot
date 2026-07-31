from langchain_core.documents import Document
from langchain_milvus import Milvus


def retrieve_documents(
    vector_store: Milvus,
    query: str,
    top_k: int = 3,
) -> list[Document]:
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    return vector_store.similarity_search(query, k=top_k)

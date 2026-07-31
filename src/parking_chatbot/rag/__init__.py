from parking_chatbot.rag.embeddings import create_embeddings
from parking_chatbot.rag.generator import build_prompt, create_llm, generate_answer
from parking_chatbot.rag.loader import load_markdown_documents
from parking_chatbot.rag.retriever import retrieve_documents
from parking_chatbot.rag.splitter import split_documents
from parking_chatbot.rag.vector_store import create_vector_store, load_vector_store


def answer_question(question: str) -> str:
    """Answer a question using the configured RAG pipeline."""
    from parking_chatbot.rag.pipeline import answer_question as answer_with_rag

    return answer_with_rag(question)


__all__ = [
    "answer_question",
    "build_prompt",
    "create_embeddings",
    "create_llm",
    "create_vector_store",
    "generate_answer",
    "load_markdown_documents",
    "load_vector_store",
    "retrieve_documents",
    "split_documents",
]

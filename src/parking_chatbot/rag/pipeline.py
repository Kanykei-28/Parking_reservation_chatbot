from pathlib import Path

from langchain_milvus import Milvus

from parking_chatbot.rag.generator import generate_answer
from parking_chatbot.rag.retriever import retrieve_documents
from parking_chatbot.rag.vector_store import load_vector_store

VECTOR_STORE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "vector_store" / "parking.db"
)
VECTOR_STORE: Milvus | None = None


def answer_question(question: str) -> str:
    global VECTOR_STORE

    if not question.strip():
        raise ValueError("question must not be empty")

    if VECTOR_STORE is None:
        VECTOR_STORE = load_vector_store(VECTOR_STORE_PATH)

    documents = retrieve_documents(VECTOR_STORE, question)
    if not documents:
        return "I couldn't find any relevant information."

    return generate_answer(question, documents)

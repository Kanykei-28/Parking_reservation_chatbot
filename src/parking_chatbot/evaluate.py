from pathlib import Path

from parking_chatbot.evaluation.dataset import load_retrieval_questions
from parking_chatbot.evaluation.generation import evaluate_generation
from parking_chatbot.evaluation.retrieval import evaluate_retrieval
from parking_chatbot.rag.pipeline import VECTOR_STORE_PATH
from parking_chatbot.rag.vector_store import load_vector_store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "data" / "evaluation" / "retrieval_questions.json"

TOP_K = 3


def main() -> None:
    """Run retrieval and generation evaluation and print a summary."""
    questions = load_retrieval_questions(DATASET_PATH)
    vector_store = load_vector_store(VECTOR_STORE_PATH)

    retrieval_result = evaluate_retrieval(
        questions,
        vector_store,
        top_k=TOP_K,
    )
    generation_result = evaluate_generation(questions)

    print("========================================")
    print("Parking Chatbot Evaluation")
    print("========================================")
    print()

    print("Dataset")
    print("-------")
    print(f"Questions: {len(questions)}")
    print()

    print("Retrieval")
    print("---------")
    print(f"Questions evaluated: {retrieval_result.total_questions}")
    print(f"Hit@1: {retrieval_result.hit_at_1:.2f}")
    print(f"Hit@{TOP_K}: {retrieval_result.hit_at_k:.2f}")
    print()

    print("Generation")
    print("----------")
    print(f"Questions evaluated: {generation_result.total_questions}")
    print(f"Average fact score: {generation_result.average_score:.2f}")


if __name__ == "__main__":
    main()

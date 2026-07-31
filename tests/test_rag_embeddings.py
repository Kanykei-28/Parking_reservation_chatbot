import math

import pytest

from parking_chatbot.rag import create_embeddings


def test_creates_normalized_minilm_embedding() -> None:
    embeddings = create_embeddings()

    vector = embeddings.embed_query("How much does covered parking cost?")

    assert isinstance(vector, list)
    assert all(isinstance(value, float) for value in vector)
    assert len(vector) == 384
    assert math.sqrt(sum(value**2 for value in vector)) == pytest.approx(1.0, abs=1e-5)

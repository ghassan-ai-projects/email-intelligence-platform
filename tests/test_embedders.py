"""Embedder factory and OpenAI-compatible embedder (mocked transport)."""

from __future__ import annotations

import pytest

from mailintel.config import EmbeddingsConfig
from mailintel.enrich.embeddings import (
    OpenAICompatEmbedder,
    VoyageEmbedder,
    make_embedder,
)


def test_factory_selects_openai_compat():
    cfg = EmbeddingsConfig(
        provider="openai-compat",
        base_url="http://localhost:11434/v1",
        model="nomic-embed-text",
        dimensions=768,
    )
    embedder = make_embedder(cfg)
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert embedder.dimensions == 768


def test_factory_rejects_unknown_provider():
    with pytest.raises(RuntimeError, match="Unknown embeddings.provider"):
        make_embedder(EmbeddingsConfig(provider="nope"))


def test_openai_compat_requires_base_url():
    with pytest.raises(RuntimeError, match="base_url"):
        OpenAICompatEmbedder(EmbeddingsConfig(provider="openai-compat"))


def test_voyage_requires_api_key(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        VoyageEmbedder(EmbeddingsConfig())


def test_openai_compat_dimension_mismatch_message(monkeypatch):
    cfg = EmbeddingsConfig(
        provider="openai-compat",
        base_url="http://localhost:11434/v1",
        model="nomic-embed-text",
        dimensions=8,
    )
    embedder = OpenAICompatEmbedder(cfg)

    class FakeData:
        embedding = [0.1] * 768

    class FakeResp:
        data = [FakeData()]

    monkeypatch.setattr(
        embedder.client.embeddings, "create", lambda **kw: FakeResp()
    )
    with pytest.raises(RuntimeError, match="dimensions = 768"):
        embedder.embed_query("hello")


def test_openai_compat_embeds(monkeypatch):
    cfg = EmbeddingsConfig(
        provider="openai-compat",
        base_url="http://localhost:11434/v1",
        model="nomic-embed-text",
        dimensions=4,
    )
    embedder = OpenAICompatEmbedder(cfg)

    class FakeData:
        def __init__(self, v):
            self.embedding = v

    class FakeResp:
        def __init__(self, n):
            self.data = [FakeData([0.1, 0.2, 0.3, 0.4]) for _ in range(n)]

    monkeypatch.setattr(
        embedder.client.embeddings,
        "create",
        lambda model, input: FakeResp(len(input)),
    )
    assert embedder.embed_query("q") == [0.1, 0.2, 0.3, 0.4]
    assert len(embedder.embed_documents(["a", "b"])) == 2

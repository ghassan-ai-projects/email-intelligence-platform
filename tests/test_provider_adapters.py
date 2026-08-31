"""Contract tests for provider adapters and attachment access boundaries."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from mailintel.enrich import attachments
from mailintel.enrich.embeddings import (
    OpenAICompatEmbedder,
    VoyageEmbedder,
    embedding_input,
    ensure_vec_table,
    knn_email_ids,
    make_embedder,
    serialize_f32,
    store_embeddings,
)
from mailintel.enrich.llm import (
    AnthropicProvider,
    LLMError,
    OpenAICompatProvider,
    make_provider,
    parse_json_response,
)
from mailintel.config import EmbeddingsConfig, LLMConfig
from mailintel.ingest import ingest


def test_parse_json_response_rejects_missing_and_non_object_json():
    with pytest.raises(LLMError, match="No JSON object"):
        parse_json_response("not json")
    with pytest.raises(LLMError, match="JSON object"):
        parse_json_response("[1, 2]")
    with pytest.raises(LLMError, match="Invalid JSON object"):
        parse_json_response("model output {not valid json}")


def test_openai_compat_provider_calls_json_endpoint(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create),
            )

        def _create(self, **kwargs):
            calls.append(("create", kwargs))
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
            )

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setenv("TEST_LLM_KEY", "secret")
    cfg = LLMConfig(api_key_env="TEST_LLM_KEY", base_url="https://llm.example")
    provider = OpenAICompatProvider(cfg)

    assert provider.complete_json("system", "user") == {"ok": True}
    assert calls[0] == ("init", {"base_url": "https://llm.example", "api_key": "secret"})
    assert calls[1][1]["response_format"] == {"type": "json_object"}


def test_anthropic_provider_collects_text_blocks(monkeypatch):
    calls = []

    class FakeAnthropic:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            calls.append(("create", kwargs))
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="thinking", text="ignored"),
                    SimpleNamespace(type="text", text='{"answer": 42}'),
                ]
            )

    monkeypatch.setattr("anthropic.Anthropic", FakeAnthropic)
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "secret")
    cfg = LLMConfig(provider="anthropic", api_key_env="TEST_ANTHROPIC_KEY")
    provider = AnthropicProvider(cfg)

    assert provider.complete_json("system", "user") == {"answer": 42}
    assert calls[1][1]["system"] == "system"


def test_provider_factories_reject_missing_keys_and_unknown_provider(monkeypatch):
    with pytest.raises(LLMError, match="Missing API key"):
        OpenAICompatProvider(LLMConfig(api_key_env="MISSING_KEY"))
    with pytest.raises(LLMError, match="Unknown llm.provider"):
        make_provider(LLMConfig(provider="other"))

    with pytest.raises(RuntimeError, match="Missing API key"):
        VoyageEmbedder(EmbeddingsConfig(api_key_env="MISSING_KEY"))
    with pytest.raises(RuntimeError, match="Unknown embeddings.provider"):
        make_embedder(EmbeddingsConfig(provider="other"))
    with pytest.raises(RuntimeError, match="base_url is required"):
        OpenAICompatEmbedder(EmbeddingsConfig(provider="openai-compat"))


def test_embedding_provider_adapters_and_dimension_guard(monkeypatch):
    voyage_calls = []

    class FakeVoyageClient:
        def __init__(self, **kwargs):
            voyage_calls.append(("init", kwargs))

        def embed(self, texts, **kwargs):
            voyage_calls.append((texts, kwargs))
            return SimpleNamespace(embeddings=[[0.1, 0.2] for _ in texts])

    monkeypatch.setattr("voyageai.Client", FakeVoyageClient)
    monkeypatch.setenv("TEST_VOYAGE_KEY", "secret")
    voyage_cfg = EmbeddingsConfig(
        api_key_env="TEST_VOYAGE_KEY", dimensions=2, model="voyage-test"
    )
    voyage = VoyageEmbedder(voyage_cfg)
    assert voyage.embed_documents(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert voyage.embed_query("a") == [0.1, 0.2]
    assert voyage_calls[1][1]["input_type"] == "document"
    assert voyage_calls[2][1]["input_type"] == "query"

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.embeddings = SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.3, 0.4])]
                )
            )

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    compat_cfg = EmbeddingsConfig(provider="openai-compat", base_url="http://localhost/v1", dimensions=2)
    compat = OpenAICompatEmbedder(compat_cfg)
    assert compat.embed_query("query") == [0.3, 0.4]

    class WrongDimensionClient(FakeOpenAI):
        def __init__(self, **_kwargs):
            self.embeddings = SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.3])]
                )
            )

    monkeypatch.setattr("openai.OpenAI", WrongDimensionClient)
    with pytest.raises(RuntimeError, match="returned 1-dim vectors"):
        OpenAICompatEmbedder(compat_cfg).embed_documents(["query"])


def test_embedding_storage_and_missing_vector_table(conn):
    assert serialize_f32([1.0, 2.0])
    ensure_vec_table(conn, 2, "test-model")
    store_embeddings(conn, [(1, [1.0, 2.0])])
    store_embeddings(conn, [(1, [2.0, 3.0])])
    row = conn.execute("SELECT email_id FROM vec_emails").fetchone()
    assert row["email_id"] == 1
    assert knn_email_ids(conn, [1.0, 2.0], 1)
    with pytest.raises(RuntimeError, match="Embedding config changed"):
        ensure_vec_table(conn, 3, "new-model")

    bare = sqlite3.connect(":memory:")
    assert knn_email_ids(bare, [1.0], 1) == []
    bare.close()


def test_embedding_input_uses_summary_and_empty_fallback():
    row = {"subject": "Subject", "summary": "Summary", "body_text": "Body"}
    assert embedding_input(row, 100) == "Subject\nSummary\nBody"
    empty = {"subject": "", "summary": "", "body_text": ""}
    assert embedding_input(empty, 100) == "(empty email)"


def test_attachment_loading_text_and_pdf_failure(conn, cfg):
    ingest(conn, cfg)
    attachment = conn.execute("SELECT * FROM attachments LIMIT 1").fetchone()
    assert attachment is not None
    loaded = attachments.load_attachment(conn, cfg.maildir.path, attachment["id"])
    assert loaded is not None
    assert loaded[0] == "doc.pdf"
    assert attachments.attachment_text("notes.txt", "text/plain", b"hello") == "hello"
    assert attachments.attachment_text("data.json", "application/json", b"{}") == "{}"
    assert attachments.attachment_text("image.bin", "application/octet-stream", b"x") is None
    assert attachments.attachment_text("broken.pdf", "application/pdf", b"not a pdf") is None
    assert attachments.extract_email_attachments(conn, attachment["email_id"], cfg.maildir.path) == 0
    assert attachments.load_attachment(conn, cfg.maildir.path, 999_999) is None

"""Embeddings stored in a sqlite-vec table (one vector per email).

Two providers: Voyage (hosted, high quality) and any OpenAI-compatible
embeddings API — which includes a fully local Ollama
(`base_url = "http://localhost:11434/v1"`, e.g. model `nomic-embed-text`).
"""

from __future__ import annotations

import sqlite3
import struct
from typing import Protocol, Sequence

from ..config import EmbeddingsConfig
from ..db import get_meta, set_meta


class Embedder(Protocol):
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class VoyageEmbedder:
    def __init__(self, cfg: EmbeddingsConfig):
        import voyageai

        if not cfg.api_key:
            raise RuntimeError(
                f"Missing API key: set the {cfg.api_key_env} environment variable"
            )
        self.cfg = cfg
        self.dimensions = cfg.dimensions
        self.client = voyageai.Client(api_key=cfg.api_key)

    def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        resp = self.client.embed(
            list(texts),
            model=self.cfg.model,
            input_type=input_type,
            output_dimension=self.cfg.dimensions,
        )
        return resp.embeddings

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]


class OpenAICompatEmbedder:
    """Any /v1/embeddings endpoint: Ollama, LM Studio, OpenAI, ..."""

    def __init__(self, cfg: EmbeddingsConfig):
        from openai import OpenAI

        if not cfg.base_url:
            raise RuntimeError(
                "embeddings.base_url is required for provider 'openai-compat' "
                "(e.g. http://localhost:11434/v1 for Ollama)"
            )
        self.cfg = cfg
        self.dimensions = cfg.dimensions
        # Local endpoints like Ollama accept any key; hosted ones need a real one.
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "unused")

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.cfg.model, input=list(texts))
        vectors = [d.embedding for d in resp.data]
        for v in vectors:
            if len(v) != self.dimensions:
                raise RuntimeError(
                    f"Model '{self.cfg.model}' returned {len(v)}-dim vectors; "
                    f"set embeddings.dimensions = {len(v)} in the config"
                )
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


def make_embedder(cfg: EmbeddingsConfig) -> Embedder:
    if cfg.provider == "voyage":
        return VoyageEmbedder(cfg)
    if cfg.provider == "openai-compat":
        return OpenAICompatEmbedder(cfg)
    raise RuntimeError(
        f"Unknown embeddings.provider: {cfg.provider!r} (use 'voyage' or 'openai-compat')"
    )


def serialize_f32(vec: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def ensure_vec_table(conn: sqlite3.Connection, dimensions: int, model: str) -> None:
    stored_dim = get_meta(conn, "embedding_dim")
    stored_model = get_meta(conn, "embedding_model")
    if stored_dim is None:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_emails "
            f"USING vec0(email_id INTEGER PRIMARY KEY, embedding FLOAT[{dimensions}])"
        )
        set_meta(conn, "embedding_dim", str(dimensions))
        set_meta(conn, "embedding_model", model)
        conn.commit()
    elif int(stored_dim) != dimensions or stored_model != model:
        raise RuntimeError(
            f"Embedding config changed (stored: {stored_model}/{stored_dim}, "
            f"now: {model}/{dimensions}). Drop the vec_emails table and re-run "
            f"enrichment to re-embed, or restore the previous config."
        )


def embedding_input(row: sqlite3.Row, max_chars: int) -> str:
    """Text embedded per email: subject + summary (if enriched) + body head."""
    parts = [row["subject"] or ""]
    if row["summary"]:
        parts.append(row["summary"])
    parts.append(row["body_text"] or "")
    return "\n".join(p for p in parts if p)[:max_chars] or "(empty email)"


def store_embeddings(
    conn: sqlite3.Connection, ids_vectors: Sequence[tuple[int, Sequence[float]]]
) -> None:
    for email_id, vec in ids_vectors:
        conn.execute("DELETE FROM vec_emails WHERE email_id = ?", (email_id,))
        conn.execute(
            "INSERT INTO vec_emails (email_id, embedding) VALUES (?, ?)",
            (email_id, serialize_f32(vec)),
        )


def knn_email_ids(
    conn: sqlite3.Connection, query_vec: Sequence[float], k: int
) -> list[tuple[int, float]]:
    try:
        rows = conn.execute(
            "SELECT email_id, distance FROM vec_emails "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (serialize_f32(query_vec), k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []  # vec table not created yet (nothing embedded)
    return [(r["email_id"], r["distance"]) for r in rows]

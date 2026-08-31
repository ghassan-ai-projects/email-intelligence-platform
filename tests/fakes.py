"""Shared deterministic provider doubles for enrichment-related tests."""

from __future__ import annotations

import hashlib


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def complete_json(self, _system: str, user: str) -> dict:
        self.calls += 1
        subject = user.splitlines()[3].removeprefix("Subject: ")
        is_k8s_root = subject == "Kubernetes cluster upgrade"
        return {
            "language": "en",
            "summary": "Summary of: " + subject,
            "importance": 4 if is_k8s_root else 2,
            "sentiment": "neutral",
            "action_items": (
                [
                    {
                        "description": "Prepare migration checklist",
                        "owner": "Bob",
                        "due_date": "2025-06-10",
                    }
                ]
                if is_k8s_root
                else []
            ),
            "entities": {
                "people": ["Alice Smith"] if "Alice" in user else [],
                "companies": ["Acme Corp"] if "Acme" in user else [],
                "projects": [],
                "topics": ["kubernetes"] if "Kubernetes" in user else ["billing"],
            },
            "facts": (
                [
                    {
                        "fact": "Invoice of $420 due July 12",
                        "category": "deadline",
                        "due_date": "2025-07-12",
                        "confidence": 0.95,
                    }
                ]
                if "Invoice" in user
                else (
                    [
                        {
                            "fact": "The proposal is due on June 10",
                            "category": "decision",
                            "confidence": 0.9,
                        }
                    ]
                    if is_k8s_root
                    else []
                )
            ),
        }


class FakeEmbedder:
    dimensions = 8

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [byte / 255 for byte in digest[:8]]

    def embed_documents(self, texts):
        return [self._vec(text) for text in texts]

    def embed_query(self, text: str):
        return self._vec(text)

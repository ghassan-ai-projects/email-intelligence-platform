"""Maildir discovery and filename helpers."""

from __future__ import annotations

from pathlib import Path


def iter_maildirs(root: Path) -> list[tuple[str, Path]]:
    """Find Maildir folders under root, including nested Maildir++ folders."""
    found: list[tuple[str, Path]] = []

    def is_maildir(path: Path) -> bool:
        return (path / "cur").is_dir() and (path / "new").is_dir()

    def folder_name(path: Path) -> str:
        relative = path.relative_to(root)
        if relative == Path():
            return "INBOX"
        parts: list[str] = []
        for segment in relative.parts:
            segment = segment.lstrip(".")
            parts.extend(part for part in segment.split(".") if part)
        return "/".join(parts) or "INBOX"

    if is_maildir(root):
        found.append((folder_name(root), root))
    for path in sorted(root.rglob("*")):
        if path.is_dir() and path.name not in ("cur", "new", "tmp") and is_maildir(path):
            if any(
                segment in ("cur", "new", "tmp") for segment in path.relative_to(root).parts[:-1]
            ):
                continue
            found.append((folder_name(path), path))
    return found


def split_flags(filename: str) -> tuple[str, bool]:
    """Return the Maildir unique name and whether the file is marked seen."""
    unique_name, _, info = filename.partition(":")
    seen = "S" in info.partition(",")[2] if info.startswith("2") else False
    return unique_name, seen


def segment_matches(folder: str, names: list[str]) -> bool:
    """Return whether any configured folder name matches a path segment."""
    segments = {segment.lower() for segment in folder.split("/")}
    return any(name.lower() in segments for name in names)

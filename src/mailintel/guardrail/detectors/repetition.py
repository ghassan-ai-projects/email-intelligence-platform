"""Repetition and padding detector."""

from __future__ import annotations

from collections import Counter

from .base import BaseDetector, DetectorResult


class RepetitionDetector(BaseDetector):
    """Detect repeated lines, dominant n-grams, and character padding."""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._ngram_size = config.get("ngram_size", 5)
        self._max_repetition_ratio = config.get("max_repetition_ratio", 0.50)
        self._min_line_repeat = config.get("min_line_repeat", 3)

    @property
    def name(self) -> str:
        return "repetition"

    def scan(
        self, _sender: str, subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        if not body:
            return DetectorResult()
        details: list[str] = []
        score = sum(
            (
                self._check_line_repetition(body, details),
                self._check_ngram_repetition(f"{subject}\n{body}", details),
                self._check_character_padding(f"{subject}\n{body}", details),
            )
        )
        score = min(score, 100)
        return DetectorResult(risk_score=score, triggered=score > 0, details=details)

    def _check_line_repetition(self, body: str, details: list[str]) -> int:
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        if not lines:
            return 0
        line_counts = Counter(lines)
        repeated = {
            line: count
            for line, count in line_counts.most_common(5)
            if count >= self._min_line_repeat
        }
        if not repeated:
            return 0
        total = sum(repeated.values())
        description = "; ".join(f"'{line[:40]}' x{count}" for line, count in repeated.items())
        details.append(f"Excessive line repetition: {total} repeated lines. {description}")
        return min(50, total * 5)

    def _check_ngram_repetition(self, text: str, details: list[str]) -> int:
        words = text.split()
        if len(words) < self._ngram_size * 2:
            return 0
        ngrams: dict[tuple[str, ...], int] = {}
        for index in range(len(words) - self._ngram_size + 1):
            ngram = tuple(words[index : index + self._ngram_size])
            if all(len(word) <= 2 for word in ngram):
                continue
            ngrams[ngram] = ngrams.get(ngram, 0) + 1
        if not ngrams:
            return 0
        most_common_ngram, max_count = max(ngrams.items(), key=lambda item: item[1])
        ratio = max_count / max(1, len(ngrams))
        if ratio <= self._max_repetition_ratio:
            return 0
        ngram_text = " ".join(most_common_ngram)
        details.append(
            f"N-gram repetition: '{ngram_text[:60]}' appears {max_count}x "
            f"({ratio:.0%} of unique n-grams)"
        )
        return min(40, int(ratio * 60))

    @staticmethod
    def _check_character_padding(text: str, details: list[str]) -> int:
        char_runs: Counter[str] = Counter()
        current_char = ""
        run_length = 0
        for char in text.lower():
            if char == current_char:
                run_length += 1
            else:
                if run_length >= 5:
                    char_runs[current_char] = max(char_runs.get(current_char, 0), run_length)
                current_char = char
                run_length = 1
        if run_length >= 5:
            char_runs[current_char] = max(char_runs.get(current_char, 0), run_length)
        if not char_runs:
            return 0
        padding_chars = {char for char in char_runs if char in " \t\n.,!?-~_*#"}
        padding_total = sum(value for char, value in char_runs.items() if char in padding_chars)
        non_padding_total = sum(char_runs.values()) - padding_total
        if padding_total > 200:
            details.append(
                f"Character padding detected: {padding_total} repeated whitespace/separator chars"
            )
            return 20
        if non_padding_total <= 50:
            return 0
        description = "; ".join(
            f"'{char}' x{count}"
            for char, count in char_runs.items()
            if char not in padding_chars and count >= 10
        )
        if not description:
            return 0
        details.append(f"Excessive character runs: {description}")
        return 15

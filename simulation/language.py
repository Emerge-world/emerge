"""Lightweight language subsystem for symbol-based communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class LexiconEntry:
    """Knowledge about a communication symbol."""

    meaning: str
    confidence: float = 0.5
    usage_count: int = 0
    owned: bool = False


class AgentLexicon:
    """Per-agent symbol lexicon with basic encode/decode helpers."""

    def __init__(self):
        self._entries: dict[str, LexiconEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> dict[str, LexiconEntry]:
        return self._entries

    def register_symbol(
        self,
        symbol: str,
        meaning: str,
        *,
        confidence: float = 0.8,
        usage_count: int = 0,
        owned: bool = False,
    ) -> None:
        symbol_key = self._normalize(symbol)
        meaning_key = meaning.strip().lower()
        if not symbol_key or not meaning_key:
            return

        current = self._entries.get(symbol_key)
        if current is None:
            self._entries[symbol_key] = LexiconEntry(
                meaning=meaning_key,
                confidence=self._clamp_confidence(confidence),
                usage_count=max(0, usage_count),
                owned=owned,
            )
            return

        if current.meaning != meaning_key and confidence >= current.confidence:
            current.meaning = meaning_key
        current.confidence = self._clamp_confidence(max(current.confidence, confidence))
        current.usage_count = max(current.usage_count, usage_count)
        current.owned = current.owned or owned

    def reinforce(self, symbol: str, *, confidence_gain: float = 0.05) -> None:
        symbol_key = self._normalize(symbol)
        entry = self._entries.get(symbol_key)
        if entry is None:
            return
        entry.usage_count += 1
        entry.confidence = self._clamp_confidence(entry.confidence + confidence_gain)

    def get_meaning(self, symbol: str) -> str | None:
        entry = self._entries.get(self._normalize(symbol))
        return entry.meaning if entry else None

    def meaning_to_symbol(self, meaning: str) -> str | None:
        meaning_key = meaning.strip().lower()
        best_symbol: str | None = None
        best_score = -1.0
        for symbol, entry in self._entries.items():
            if entry.meaning != meaning_key:
                continue
            score = entry.confidence + (0.1 if entry.owned else 0.0)
            if score > best_score:
                best_score = score
                best_symbol = symbol
        return best_symbol

    def encode_text(self, message: str, max_tokens: int) -> list[str]:
        tokens = [self._normalize(tok) for tok in message.split() if tok.strip()]
        encoded: list[str] = []
        for token in tokens[:max_tokens]:
            maybe_symbol = self.meaning_to_symbol(token)
            encoded.append(maybe_symbol or token)
            if maybe_symbol:
                self.reinforce(maybe_symbol, confidence_gain=0.02)
        return encoded

    def decode_tokens(self, tokens: Iterable[str]) -> tuple[str, list[str], int]:
        interpreted: list[str] = []
        unknown: list[str] = []
        known = 0
        for token in tokens:
            token_key = self._normalize(token)
            meaning = self.get_meaning(token_key)
            if meaning:
                interpreted.append(meaning)
                known += 1
                self.reinforce(token_key)
            else:
                interpreted.append(token_key)
                unknown.append(token_key)
        return " ".join(interpreted).strip(), unknown, known

    def shared_symbols(self, other: "AgentLexicon") -> set[str]:
        return set(self._entries).intersection(other.entries())

    def known_symbols_section(self, limit: int = 8) -> str:
        if not self._entries:
            return ""
        ranked = sorted(
            self._entries.items(),
            key=lambda kv: (kv[1].confidence, kv[1].usage_count),
            reverse=True,
        )
        lines = ["KNOWN SYMBOLS:"]
        for symbol, entry in ranked[:limit]:
            marker = "*" if entry.owned else ""
            lines.append(
                f"- {symbol}{marker} → {entry.meaning} "
                f"(conf={entry.confidence:.2f}, uses={entry.usage_count})"
            )
        return "\n".join(lines)

    @staticmethod
    def _normalize(token: str) -> str:
        return token.strip().lower()

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

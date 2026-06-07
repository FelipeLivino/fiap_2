import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .gemini_client import GEMINI_API_BASE, get_api_key


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSION = 768
TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9_]+")


@dataclass(frozen=True)
class EmbeddingResult:
    """Guarda o vetor gerado e metadados sobre modelo, provider e fallback."""

    values: list[float]
    model: str
    provider: str
    dimension: int
    fallback_used: bool = False


def get_embedding_model() -> str:
    """Retorna o modelo de embedding configurado para a busca vetorial."""
    return os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).removeprefix("models/")


def get_embedding_dimension() -> int:
    """Valida e retorna a dimensao do embedding usada no pgvector."""
    raw_value = os.getenv("GEMINI_EMBEDDING_DIMENSION", str(DEFAULT_EMBEDDING_DIMENSION))
    try:
        dimension = int(raw_value)
    except ValueError:
        return DEFAULT_EMBEDDING_DIMENSION
    if dimension < 128 or dimension > 3072:
        return DEFAULT_EMBEDDING_DIMENSION
    return dimension


def is_embedding_configured() -> bool:
    """Indica se o servico tem credencial para gerar embeddings reais."""
    return bool(get_api_key())


def normalize_vector(values: list[float]) -> list[float]:
    """Normaliza o vetor para melhorar comparacao por similaridade."""
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


def _fallback_tokens(text: str) -> list[str]:
    """Extrai tokens usados pelo embedding local de contingencia."""
    tokens = [token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1]
    return tokens or ["__empty__"]


def fallback_embedding(text: str, *, dimension: int | None = None) -> list[float]:
    """Gera um embedding deterministico local quando a API externa nao esta disponivel."""
    vector_size = dimension or get_embedding_dimension()
    values = [0.0] * vector_size
    for token in _fallback_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % vector_size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        values[index] += sign * weight
    return normalize_vector(values)


def build_embedding_payload(text: str, *, dimension: int | None = None) -> dict:
    """Monta o payload enviado ao endpoint de embeddings do Gemini."""
    return {
        "content": {"parts": [{"text": text}]},
        "output_dimensionality": dimension or get_embedding_dimension(),
    }


def _extract_embedding_values(data: dict[str, Any]) -> list[float]:
    """Extrai os valores numericos do embedding considerando formatos possiveis da API."""
    embedding = data.get("embedding")
    if isinstance(embedding, dict) and isinstance(embedding.get("values"), list):
        return [float(value) for value in embedding["values"]]

    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        if isinstance(first, dict) and isinstance(first.get("values"), list):
            return [float(value) for value in first["values"]]

    raise RuntimeError("Gemini nao retornou valores de embedding.")


class EmbeddingClient:
    """Cliente responsavel por gerar embeddings reais ou acionar fallback local."""

    def __init__(
        self,
        *,
        model: str | None = None,
        dimension: int | None = None,
        timeout: float = 30.0,
        allow_fallback: bool = True,
    ) -> None:
        """Configura modelo, dimensao, timeout e permissao de fallback."""
        self.model = (model or get_embedding_model()).removeprefix("models/")
        self.dimension = dimension or get_embedding_dimension()
        self.timeout = timeout
        self.allow_fallback = allow_fallback

    def embed_text(self, text: str) -> EmbeddingResult:
        """Gera embedding para um texto e volta ao fallback se a API falhar."""
        api_key = get_api_key()
        if not api_key:
            if not self.allow_fallback:
                raise RuntimeError("GEMINI_API_KEY nao configurada.")
            return self._fallback(text)

        url = f"{GEMINI_API_BASE}/models/{self.model}:embedContent"
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=build_embedding_payload(text, dimension=self.dimension),
                timeout=self.timeout,
            )
            response.raise_for_status()
            values = normalize_vector(_extract_embedding_values(response.json()))
            if len(values) != self.dimension:
                raise RuntimeError(
                    f"Embedding retornou dimensao {len(values)}, esperado {self.dimension}."
                )
            return EmbeddingResult(
                values=values,
                model=self.model,
                provider="google-ai-studio",
                dimension=len(values),
            )
        except Exception:
            if not self.allow_fallback:
                raise
            return self._fallback(text)

    def _fallback(self, text: str) -> EmbeddingResult:
        """Cria um resultado de embedding local preservando os metadados da chamada."""
        values = fallback_embedding(text, dimension=self.dimension)
        return EmbeddingResult(
            values=values,
            model=f"{self.model}:local-fallback",
            provider="local-fallback",
            dimension=len(values),
            fallback_used=True,
        )


def embed_text_with_metadata(text: str) -> EmbeddingResult:
    """Atalho para gerar embedding retornando vetor e metadados."""
    return EmbeddingClient().embed_text(text)


def embed_text(text: str) -> list[float]:
    """Atalho para gerar apenas o vetor de embedding."""
    return embed_text_with_metadata(text).values

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .knowledge_ingestion import vector_to_pgvector
from .pgvector_status import get_database_url


DEFAULT_TOP_K = 3
TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


@dataclass(frozen=True)
class VectorSearchResult:
    """Resultado unificado de busca vetorial ou fallback por palavra-chave."""

    title: str
    content: str
    source_url: str | None
    source_type: str
    trusted_level: str
    score: float
    retrieval_method: str
    source_id: str | None = None
    chunk_index: int | None = None


def _row_get(row: Any, key: str, index: int) -> Any:
    """Le um campo de linha retornada pelo banco aceitando dict ou tupla."""
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _fallback_results(query_text: str, *, top_k: int = DEFAULT_TOP_K) -> list[VectorSearchResult]:
    """Busca documentos locais por palavra-chave quando pgvector nao pode ser usado."""
    documents = _retrieve_keyword_documents(query_text, limit=top_k)
    results: list[VectorSearchResult] = []
    for document in documents:
        results.append(
            VectorSearchResult(
                title=document["title"],
                content=document["content"],
                source_url=document["source"],
                source_type="project",
                trusted_level="project",
                score=float(document["score"]),
                retrieval_method="keyword-fallback",
                source_id=None,
                chunk_index=None,
            )
        )
    return results


def _tokenize(text: str) -> set[str]:
    """Extrai tokens para o fallback local de busca por palavras-chave."""
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2}


def _default_knowledge_base_path() -> Path:
    """Resolve a pasta local de conhecimento usada pelo fallback de recuperacao."""
    env_path = os.getenv("RAG_KNOWLEDGE_BASE_PATH")
    if env_path:
        return Path(env_path)
    container_path = Path("/app/knowledge_base")
    if container_path.exists():
        return container_path
    return Path(__file__).resolve().parents[2] / "data" / "rag"


def _retrieve_keyword_documents(query_text: str, *, limit: int) -> list[dict[str, Any]]:
    """Ranking simples de documentos Markdown pela intersecao de tokens com a consulta."""
    root = _default_knowledge_base_path()
    query_tokens = _tokenize(query_text)
    if not root.exists() or not query_tokens:
        return []

    ranked: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        content = path.read_text(encoding="utf-8").strip()
        title = path.stem.replace("_", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line.removeprefix("# ").strip()
                break
        score = len(query_tokens & _tokenize(title + " " + content))
        if score > 0:
            ranked.append(
                {
                    "title": title,
                    "source": str(path),
                    "score": score,
                    "content": content,
                }
            )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def search_similar_chunks(
    query_embedding: list[float],
    *,
    top_k: int = DEFAULT_TOP_K,
    database_url: str | None = None,
    fallback_query: str | None = None,
) -> list[VectorSearchResult]:
    """Busca chunks similares no pgvector e usa fallback local se o banco falhar."""
    if top_k <= 0:
        return []

    url = database_url or get_database_url()
    if not url:
        if fallback_query:
            return _fallback_results(fallback_query, top_k=top_k)
        return []

    try:
        psycopg = importlib.import_module("psycopg")
        rows = _query_pgvector(psycopg, url, query_embedding, top_k)
        return [_row_to_result(row) for row in rows]
    except Exception:
        if fallback_query:
            return _fallback_results(fallback_query, top_k=top_k)
        return []


def _query_pgvector(psycopg: Any, database_url: str, query_embedding: list[float], top_k: int) -> list[Any]:
    """Executa a consulta SQL de similaridade vetorial usando a extensao pgvector."""
    vector = vector_to_pgvector(query_embedding)
    query = """
        SELECT
          d.source_id,
          d.title,
          d.source_url,
          d.source_type,
          d.trusted_level,
          c.chunk_index,
          c.content,
          1 - (c.embedding <=> %s::vector) AS score
        FROM rag_chunks c
        JOIN rag_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
        ORDER BY
          c.embedding <=> %s::vector,
          CASE d.trusted_level WHEN 'gold' THEN 0 WHEN 'project' THEN 1 ELSE 2 END,
          c.id
        LIMIT %s
    """
    with psycopg.connect(database_url, connect_timeout=2) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (vector, vector, top_k))
            return cursor.fetchall()


def _row_to_result(row: Any) -> VectorSearchResult:
    """Converte uma linha do banco para o DTO usado pelo RAG."""
    score = _row_get(row, "score", 7)
    return VectorSearchResult(
        source_id=_row_get(row, "source_id", 0),
        title=_row_get(row, "title", 1),
        source_url=_row_get(row, "source_url", 2),
        source_type=_row_get(row, "source_type", 3),
        trusted_level=_row_get(row, "trusted_level", 4),
        chunk_index=_row_get(row, "chunk_index", 5),
        content=_row_get(row, "content", 6),
        score=float(score or 0.0),
        retrieval_method="pgvector",
    )


def build_context_from_results(results: list[VectorSearchResult], *, max_chars: int = 1800) -> str:
    """Monta o bloco de contexto com fontes, confianca e conteudo recuperado."""
    blocks: list[str] = []
    used = 0
    for result in results:
        block = f"Fonte: {result.title}\nConfianca: {result.trusted_level}\n{result.content}"
        if used + len(block) > max_chars:
            block = block[: max_chars - used].rstrip()
        if block:
            blocks.append(block)
            used += len(block)
        if used >= max_chars:
            break
    return "\n\n---\n\n".join(blocks)

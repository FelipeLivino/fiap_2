import importlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .embeddings import EmbeddingClient, EmbeddingResult
from .pgvector_status import get_database_url


DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class KnowledgeSource:
    """Representa uma fonte de conhecimento declarada no manifest RAG."""

    source_id: str
    title: str
    source_type: str
    source_url: str | None
    raw_path: Path
    processed_path: Path
    trusted_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeChunk:
    """Representa um trecho menor de uma fonte, pronto para embedding."""

    source_id: str
    chunk_index: int
    content: str
    token_estimate: int


@dataclass(frozen=True)
class EmbeddedChunk:
    """Associa um chunk textual ao embedding gerado para ele."""

    chunk: KnowledgeChunk
    embedding: EmbeddingResult


@dataclass(frozen=True)
class IngestionPlan:
    """Plano de ingestao com fontes carregadas, chunks gerados e contagem gold."""

    sources: list[KnowledgeSource]
    chunks: list[KnowledgeChunk]
    gold_sources_count: int


@dataclass(frozen=True)
class IngestionResult:
    """Resumo final da ingestao para logs, scripts e verificacao do Compose."""

    documents_found: int
    chunks_generated: int
    embeddings_saved: int
    gold_sources_count: int
    dry_run: bool
    provider: str


def repo_root() -> Path:
    """Retorna a raiz do modulo ai-rag-service."""
    return Path(__file__).resolve().parents[2]


def default_sources_dir() -> Path:
    """Resolve a pasta padrao onde ficam manifest e textos da base RAG."""
    return Path(os.getenv("RAG_SOURCES_PATH", repo_root() / "data" / "rag_sources"))


def clean_text(text: str) -> str:
    """Normaliza quebras de linha e espacos antes da divisao em chunks."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def estimate_tokens(text: str) -> int:
    """Estima tokens de forma simples usando quantidade de palavras."""
    return max(1, len(re.findall(r"\S+", text)))


def _resolve_manifest_path(sources_dir: Path, relative_path: str) -> Path:
    """Converte caminhos relativos do manifest em caminhos absolutos."""
    return (sources_dir / relative_path).resolve()


def load_manifest(sources_dir: Path | None = None) -> list[KnowledgeSource]:
    """Carrega o manifest JSON e transforma cada item em KnowledgeSource."""
    root = sources_dir or default_sources_dir()
    manifest_path = root / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    sources: list[KnowledgeSource] = []
    for item in data:
        metadata = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "sourceId",
                "title",
                "sourceType",
                "sourceUrl",
                "rawPath",
                "processedPath",
                "trustedLevel",
            }
        }
        sources.append(
            KnowledgeSource(
                source_id=item["sourceId"],
                title=item["title"],
                source_type=item["sourceType"],
                source_url=item.get("sourceUrl"),
                raw_path=_resolve_manifest_path(root, item["rawPath"]),
                processed_path=_resolve_manifest_path(root, item["processedPath"]),
                trusted_level=item["trustedLevel"],
                metadata=metadata,
            )
        )
    return sources


def chunk_text(
    text: str,
    *,
    source_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[KnowledgeChunk]:
    """Divide um texto em chunks com sobreposicao para melhorar recuperacao RAG."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size deve ser positivo.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap deve ser maior ou igual a zero e menor que chunk_size.")

    chunks: list[KnowledgeChunk] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            paragraph_break = cleaned.rfind("\n\n", start, end)
            sentence_break = cleaned.rfind(". ", start, end)
            best_break = max(paragraph_break, sentence_break)
            if best_break > start + int(chunk_size * 0.45):
                end = best_break + 1

        content = cleaned[start:end].strip()
        if content:
            chunks.append(
                KnowledgeChunk(
                    source_id=source_id,
                    chunk_index=len(chunks),
                    content=content,
                    token_estimate=estimate_tokens(content),
                )
            )
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def build_ingestion_plan(
    *,
    sources_dir: Path | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionPlan:
    """Cria o plano de ingestao lendo fontes e gerando chunks de cada documento."""
    sources = load_manifest(sources_dir)
    chunks: list[KnowledgeChunk] = []
    for source in sources:
        text = source.processed_path.read_text(encoding="utf-8")
        chunks.extend(chunk_text(text, source_id=source.source_id, chunk_size=chunk_size, overlap=overlap))
    return IngestionPlan(
        sources=sources,
        chunks=chunks,
        gold_sources_count=sum(1 for source in sources if source.trusted_level == "gold"),
    )


def vector_to_pgvector(values: list[float]) -> str:
    """Converte uma lista de floats para o formato textual aceito pelo pgvector."""
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


def _metadata_json(source: KnowledgeSource) -> str:
    """Serializa metadados da fonte preservando caracteres em portugues."""
    return json.dumps(source.metadata, ensure_ascii=False)


def _save_document(cursor: Any, source: KnowledgeSource) -> int:
    """Insere ou atualiza um documento RAG e retorna seu id no banco."""
    cursor.execute(
        """
        INSERT INTO rag_documents (
          source_id, title, source_type, source_url, local_path, trusted_level, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (source_id) DO UPDATE SET
          title = EXCLUDED.title,
          source_type = EXCLUDED.source_type,
          source_url = EXCLUDED.source_url,
          local_path = EXCLUDED.local_path,
          trusted_level = EXCLUDED.trusted_level,
          metadata = EXCLUDED.metadata
        RETURNING id
        """,
        (
            source.source_id,
            source.title,
            source.source_type,
            source.source_url,
            str(source.processed_path),
            source.trusted_level,
            _metadata_json(source),
        ),
    )
    row = cursor.fetchone()
    return int(row[0])


def _save_chunk(cursor: Any, document_id: int, embedded_chunk: EmbeddedChunk) -> None:
    """Insere ou atualiza um chunk com seu embedding na tabela rag_chunks."""
    cursor.execute(
        """
        INSERT INTO rag_chunks (
          document_id, chunk_index, content, embedding, token_estimate
        )
        VALUES (%s, %s, %s, %s::vector, %s)
        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
          content = EXCLUDED.content,
          embedding = EXCLUDED.embedding,
          token_estimate = EXCLUDED.token_estimate
        """,
        (
            document_id,
            embedded_chunk.chunk.chunk_index,
            embedded_chunk.chunk.content,
            vector_to_pgvector(embedded_chunk.embedding.values),
            embedded_chunk.chunk.token_estimate,
        ),
    )


def persist_ingestion(
    plan: IngestionPlan,
    *,
    embedded_chunks: list[EmbeddedChunk],
    database_url: str | None = None,
    rebuild: bool = False,
) -> int:
    """Persiste documentos e chunks com embeddings no PostgreSQL/pgvector."""
    url = database_url or get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL nao configurada.")

    psycopg = importlib.import_module("psycopg")
    chunks_by_source: dict[str, list[EmbeddedChunk]] = {}
    for embedded_chunk in embedded_chunks:
        chunks_by_source.setdefault(embedded_chunk.chunk.source_id, []).append(embedded_chunk)

    saved = 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cursor:
            if rebuild:
                cursor.execute("TRUNCATE TABLE rag_chunks, rag_documents RESTART IDENTITY CASCADE")

            for source in plan.sources:
                document_id = _save_document(cursor, source)
                current_chunks = chunks_by_source.get(source.source_id, [])
                cursor.execute("DELETE FROM rag_chunks WHERE document_id = %s", (document_id,))
                for embedded_chunk in current_chunks:
                    _save_chunk(cursor, document_id, embedded_chunk)
                    saved += 1
        conn.commit()
    return saved


def run_ingestion(
    *,
    sources_dir: Path | None = None,
    database_url: str | None = None,
    dry_run: bool = False,
    rebuild: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    embedding_client: EmbeddingClient | None = None,
) -> IngestionResult:
    """Executa o fluxo completo de ingestao: manifest, chunks, embeddings e banco."""
    plan = build_ingestion_plan(sources_dir=sources_dir, chunk_size=chunk_size, overlap=overlap)
    client = embedding_client or EmbeddingClient()
    embedded_chunks = [
        EmbeddedChunk(chunk=chunk, embedding=client.embed_text(chunk.content))
        for chunk in plan.chunks
    ]
    provider = embedded_chunks[0].embedding.provider if embedded_chunks else "none"

    saved = 0
    if not dry_run:
        saved = persist_ingestion(
            plan,
            embedded_chunks=embedded_chunks,
            database_url=database_url,
            rebuild=rebuild,
        )

    return IngestionResult(
        documents_found=len(plan.sources),
        chunks_generated=len(plan.chunks),
        embeddings_saved=saved,
        gold_sources_count=plan.gold_sources_count,
        dry_run=dry_run,
        provider=provider,
    )

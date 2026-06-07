import importlib
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PgVectorStatus:
    """Estado resumido da disponibilidade do pgvector e da base RAG."""

    available: bool
    documents_count: int
    chunks_count: int
    error: str | None = None


def get_database_url() -> str | None:
    """Retorna a URL do PostgreSQL usada pelo servico RAG."""
    return os.getenv("DATABASE_URL")


def _fetch_scalar(cursor: Any, query: str) -> int:
    """Executa uma consulta escalar e retorna zero quando nao houver resultado."""
    cursor.execute(query)
    row = cursor.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def check_pgvector_status(database_url: str | None = None) -> PgVectorStatus:
    """Verifica conexao, extensao vector, tabelas RAG e quantidade de registros."""
    url = database_url or get_database_url()
    if not url:
        return PgVectorStatus(
            available=False,
            documents_count=0,
            chunks_count=0,
            error="DATABASE_URL nao configurada.",
        )

    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError:
        return PgVectorStatus(
            available=False,
            documents_count=0,
            chunks_count=0,
            error="Dependencia psycopg nao instalada.",
        )

    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                extension_row = cursor.fetchone()
                extension_available = bool(extension_row and extension_row[0])

                documents_count = _fetch_scalar(
                    cursor,
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'rag_documents'",
                )
                chunks_count = _fetch_scalar(
                    cursor,
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'rag_chunks'",
                )

                stored_documents = 0
                stored_chunks = 0
                if documents_count:
                    stored_documents = _fetch_scalar(cursor, "SELECT COUNT(*) FROM rag_documents")
                if chunks_count:
                    stored_chunks = _fetch_scalar(cursor, "SELECT COUNT(*) FROM rag_chunks")

        return PgVectorStatus(
            available=extension_available and bool(documents_count) and bool(chunks_count),
            documents_count=stored_documents,
            chunks_count=stored_chunks,
        )
    except Exception as exc:
        return PgVectorStatus(
            available=False,
            documents_count=0,
            chunks_count=0,
            error=type(exc).__name__,
        )

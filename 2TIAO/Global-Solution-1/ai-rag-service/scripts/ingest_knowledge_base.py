from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SERVICE_ROOT))

from src.knowledge_ingestion import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, run_ingestion


def parse_args() -> argparse.Namespace:
    """Define e interpreta os argumentos do script de ingestao da base RAG."""
    parser = argparse.ArgumentParser(description="Ingere a base RAG curada no PostgreSQL com pgvector.")
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=None,
        help="Caminho para data/rag_sources. Usa RAG_SOURCES_PATH ou o padrao do repositorio.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="DATABASE_URL alternativo. Se omitido, usa a variavel de ambiente DATABASE_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Monta chunks e embeddings, mas nao salva no banco.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Limpa rag_documents/rag_chunks antes de salvar novamente.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Tamanho maximo aproximado de cada chunk. Padrao: {DEFAULT_CHUNK_SIZE}.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Sobreposicao entre chunks. Padrao: {DEFAULT_CHUNK_OVERLAP}.",
    )
    return parser.parse_args()


def main() -> None:
    """Executa a ingestao e imprime um resumo para validacao no terminal."""
    args = parse_args()
    result = run_ingestion(
        sources_dir=args.sources_dir,
        database_url=args.database_url,
        dry_run=args.dry_run,
        rebuild=args.rebuild,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )

    print(f"Documentos encontrados: {result.documents_found}")
    print(f"Chunks gerados: {result.chunks_generated}")
    print(f"Embeddings salvos no pgvector: {result.embeddings_saved}")
    print(f"Fontes gold: {result.gold_sources_count}")
    print(f"Provider de embeddings: {result.provider}")
    print(f"Dry-run: {'sim' if result.dry_run else 'nao'}")


if __name__ == "__main__":
    main()

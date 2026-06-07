CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
  id SERIAL PRIMARY KEY,
  source_id TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_url TEXT,
  local_path TEXT,
  trusted_level TEXT NOT NULL DEFAULT 'gold',
  collected_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS rag_chunks (
  id SERIAL PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding vector(768),
  token_estimate INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS rag_documents_source_type_idx
ON rag_documents (source_type);

CREATE INDEX IF NOT EXISTS rag_documents_trusted_level_idx
ON rag_documents (trusted_level);

CREATE INDEX IF NOT EXISTS rag_chunks_document_id_idx
ON rag_chunks (document_id);

CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
ON rag_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

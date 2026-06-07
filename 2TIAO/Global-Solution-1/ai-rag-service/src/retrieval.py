import os
import re
from dataclasses import dataclass
from pathlib import Path

from .embeddings import EmbeddingClient, get_embedding_model
from .gemini_client import generate_text, get_gemini_model, is_gemini_configured
from .guardrails import (
    GuardrailResult,
    OutputValidationResult,
    evaluate_question,
    guardrails_enabled,
    validate_generated_answer,
)
from .prompts import build_rag_answer_prompt
from .vector_store import VectorSearchResult, build_context_from_results, search_similar_chunks


TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


def configured_top_k() -> int:
    """Le e limita a quantidade de fontes recuperadas para cada consulta RAG."""
    try:
        value = int(os.getenv("RAG_TOP_K", "3"))
    except ValueError:
        return 3
    return max(1, min(value, 10))


@dataclass(frozen=True)
class RetrievedDocument:
    """Representa um documento recuperado pelo fallback de palavras-chave."""

    title: str
    source: str
    score: int
    content: str


def tokenize(text: str) -> set[str]:
    """Transforma texto em tokens para busca simples por palavras-chave."""
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2}


def default_knowledge_base_path() -> Path:
    """Resolve a pasta padrao da base RAG local em container ou ambiente de desenvolvimento."""
    env_path = os.getenv("RAG_KNOWLEDGE_BASE_PATH")
    if env_path:
        return Path(env_path)
    container_path = Path("/app/knowledge_base")
    if container_path.exists():
        return container_path
    return Path(__file__).resolve().parents[2] / "data" / "rag"


def load_documents(base_path: Path | None = None) -> list[RetrievedDocument]:
    """Carrega documentos Markdown usados como fallback quando pgvector nao esta disponivel."""
    root = base_path or default_knowledge_base_path()
    if not root.exists():
        return []

    documents: list[RetrievedDocument] = []
    for path in sorted(root.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        content = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line.removeprefix("# ").strip()
                break
        documents.append(RetrievedDocument(title=title, source=str(path), score=0, content=content.strip()))
    return documents


def retrieve(query: str, *, limit: int = 3, base_path: Path | None = None) -> list[RetrievedDocument]:
    """Recupera documentos por sobreposicao de tokens como mecanismo legado de busca."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    ranked: list[RetrievedDocument] = []
    for document in load_documents(base_path):
        score = len(query_tokens & tokenize(document.title + " " + document.content))
        if score > 0:
            ranked.append(
                RetrievedDocument(
                    title=document.title,
                    source=document.source,
                    score=score,
                    content=document.content,
                )
            )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def build_context(documents: list[RetrievedDocument], *, max_chars: int = 1800) -> str:
    """Concatena documentos recuperados em um contexto compacto para o prompt."""
    blocks: list[str] = []
    used = 0
    for document in documents:
        block = f"Fonte: {document.title}\n{document.content}"
        if used + len(block) > max_chars:
            block = block[: max_chars - used].rstrip()
        if block:
            blocks.append(block)
            used += len(block)
        if used >= max_chars:
            break
    return "\n\n---\n\n".join(blocks)


def _legacy_documents_to_vector_results(documents: list[RetrievedDocument]) -> list[VectorSearchResult]:
    """Converte resultados legados para o mesmo formato usado pela busca vetorial."""
    return [
        VectorSearchResult(
            title=document.title,
            content=document.content,
            source_url=document.source,
            source_type="project",
            trusted_level="project",
            score=float(document.score),
            retrieval_method="keyword-fallback",
        )
        for document in documents
    ]


def _source_payload(result: VectorSearchResult) -> dict:
    """Converte um resultado recuperado para o formato enviado ao frontend/backend."""
    return {
        "title": result.title,
        "source": result.source_url,
        "sourceUrl": result.source_url,
        "score": result.score,
        "sourceScore": result.score,
        "retrievalMethod": result.retrieval_method,
        "sourceType": result.source_type,
        "trustedLevel": result.trusted_level,
        "sourceId": result.source_id,
        "chunkIndex": result.chunk_index,
    }


def _retrieve_with_embeddings(question: str, *, top_k: int | None = None) -> tuple[list[VectorSearchResult], dict]:
    """Gera embedding da pergunta, busca chunks similares e retorna metadados da recuperacao."""
    top_k = top_k or configured_top_k()
    embedding_metadata = default_retrieval_metadata()
    try:
        embedding = EmbeddingClient().embed_text(question)
        embedding_metadata.update(
            {
                "embeddingModel": embedding.model,
                "embeddingProvider": embedding.provider,
                "embeddingFallbackUsed": embedding.fallback_used,
            }
        )
        results = search_similar_chunks(
            embedding.values,
            top_k=top_k,
            fallback_query=question,
        )
        if results:
            embedding_metadata["retrievalMethod"] = results[0].retrieval_method
        return results, embedding_metadata
    except Exception as exc:
        documents = retrieve(question, limit=top_k)
        embedding_metadata.update(
            {
                "embeddingProvider": "error-fallback",
                "embeddingError": type(exc).__name__,
                "retrievalMethod": "keyword-fallback",
            }
        )
        return _legacy_documents_to_vector_results(documents), embedding_metadata


def default_retrieval_metadata() -> dict:
    """Retorna metadados padrao quando a busca RAG ainda nao foi executada."""
    return {
        "embeddingModel": get_embedding_model(),
        "embeddingProvider": "not-run",
        "embeddingFallbackUsed": False,
        "retrievalMethod": "none",
    }


def retrieve_rag_context(query: str, *, top_k: int | None = None) -> dict:
    """Recupera contexto e fontes para relatorios ou perguntas RAG."""
    results, metadata = _retrieve_with_embeddings(query, top_k=top_k)
    return {
        "context": build_context_from_results(results),
        "sources": [_source_payload(result) for result in results],
        **metadata,
    }


def answer_question(question: str) -> dict:
    """Responde uma pergunta aplicando guardrails, recuperacao RAG e fallback local."""
    if guardrails_enabled():
        guardrail = evaluate_question(question)
    else:
        guardrail = GuardrailResult(
            blocked=False,
            reasons=[],
            safety_level="guardrails_disabled",
            sanitized_question=question,
        )
    if guardrail.blocked_by_guardrail:
        return {
            "question": question,
            "answer": (
                "Nao posso atender a essa solicitacao porque ela tenta alterar as regras "
                "de seguranca do sistema ou forcar uma resposta insegura."
            ),
            "context": "",
            "sources": [],
            "blockedByScope": False,
            "blockedByGuardrail": True,
            "guardrailReasons": guardrail.reasons,
            "safetyLevel": guardrail.safety_level,
            "provider": "guardrail",
            "model": None,
            **default_retrieval_metadata(),
            "outputRewritten": False,
            "promptAudit": "",
        }

    if guardrail.blocked_by_scope:
        return {
            "question": question,
            "answer": (
                "Essa pergunta esta fora do escopo do AstroWater AI. "
                "Posso responder sobre triagem da agua, sensores, visao computacional, RAG, "
                "acoes preventivas e conexao com suporte a vida espacial."
            ),
            "context": "",
            "sources": [],
            "blockedByScope": True,
            "blockedByGuardrail": False,
            "guardrailReasons": guardrail.reasons,
            "safetyLevel": guardrail.safety_level,
            "provider": "guardrail",
            "model": None,
            **default_retrieval_metadata(),
            "outputRewritten": False,
            "promptAudit": "",
        }

    results, retrieval_metadata = _retrieve_with_embeddings(guardrail.sanitized_question)
    context = build_context_from_results(results)
    prompt_audit = build_rag_answer_prompt(guardrail.sanitized_question, context)
    if not results:
        answer = (
            "Nao encontrei trechos relevantes na base local. Para manter seguranca, "
            "recomendo nova medicao e avaliacao oficial quando houver risco."
        )
        provider = "local-fallback"
        model = None
    else:
        titles = ", ".join(result.title for result in results)
        answer = (
            f"Com base na base recuperada ({titles}), a resposta deve ser preventiva: "
            "use a triagem como apoio, observe os sinais de risco e encaminhe para avaliacao oficial "
            "quando houver risco elevado ou critico."
        )
        provider = "local-fallback"
        model = None

        if is_gemini_configured():
            try:
                result = generate_text(prompt_audit)
                answer = result.text
                provider = result.provider
                model = result.model
            except Exception as exc:
                answer += f" Gemini indisponivel nesta chamada; fallback local usado ({type(exc).__name__})."
                model = get_gemini_model()

    if guardrails_enabled():
        output_validation = validate_generated_answer(answer)
    else:
        output_validation = OutputValidationResult(
            answer=answer,
            safety_level="guardrails_disabled",
            reasons=[],
            rewritten=False,
        )

    return {
        "question": question,
        "answer": output_validation.answer,
        "context": context,
        "blockedByScope": False,
        "blockedByGuardrail": False,
        "guardrailReasons": output_validation.reasons,
        "safetyLevel": output_validation.safety_level,
        "outputRewritten": output_validation.rewritten,
        "provider": provider,
        "model": model,
        "embeddingModel": retrieval_metadata.get("embeddingModel"),
        "embeddingProvider": retrieval_metadata.get("embeddingProvider"),
        "embeddingFallbackUsed": retrieval_metadata.get("embeddingFallbackUsed"),
        "retrievalMethod": retrieval_metadata.get("retrievalMethod"),
        "promptAudit": prompt_audit,
        "sources": [_source_payload(result) for result in results],
    }

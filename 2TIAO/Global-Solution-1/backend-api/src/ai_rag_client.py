import os
from typing import Any

import httpx


DEFAULT_AI_RAG_BASE_URL = "http://ai-rag-service:8001"
DEFAULT_AI_RAG_TIMEOUT_SECONDS = 60.0


def get_ai_rag_base_url() -> str:
    """Retorna a URL base do servico AI/RAG usada pelo backend."""
    return os.getenv("AI_RAG_BASE_URL", DEFAULT_AI_RAG_BASE_URL).rstrip("/")


def get_ai_rag_timeout_seconds() -> float:
    """Retorna o timeout configurado para aguardar respostas do servico AI/RAG."""
    raw_value = os.getenv("AI_RAG_TIMEOUT_SECONDS", str(DEFAULT_AI_RAG_TIMEOUT_SECONDS))
    try:
        timeout = float(raw_value)
    except ValueError:
        return DEFAULT_AI_RAG_TIMEOUT_SECONDS
    return max(5.0, timeout)


def _fallback_payload(reason: str, *, question: str | None = None) -> dict[str, Any]:
    """Monta uma resposta segura quando o servico AI/RAG esta indisponivel."""
    payload: dict[str, Any] = {
        "provider": "backend-fallback",
        "model": None,
        "safetyLevel": "fallback",
        "retrievalMethod": "none",
        "sources": [],
        "guardrailReasons": [reason],
        "outputRewritten": False,
        "generatedText": (
            "Servico de IA indisponivel ou demorou mais que o limite configurado. "
            "Mantida recomendacao preventiva local."
        ),
    }
    if question is not None:
        payload.update(
            {
                "question": question,
                "answer": (
                    "Servico de IA indisponivel. Use a triagem local como apoio preventivo "
                    "e encaminhe a amostra para avaliacao oficial quando houver risco."
                ),
                "blockedByGuardrail": False,
                "blockedByScope": False,
            }
        )
    return payload


def _request(method: str, path: str, *, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Executa uma chamada HTTP ao servico AI/RAG e valida que a resposta e JSON objeto."""
    url = f"{get_ai_rag_base_url()}{path}"
    with httpx.Client(timeout=get_ai_rag_timeout_seconds()) as client:
        response = client.request(method, url, json=json_payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Resposta inesperada do AI/RAG service.")
        return data


def generate_ai_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Solicita ao AI/RAG Service a geracao de relatorio para uma comunidade."""
    try:
        return _request("POST", "/reports/generate", json_payload=payload)
    except (httpx.HTTPError, ValueError) as exc:
        return _fallback_payload(type(exc).__name__)


def query_rag(question: str) -> dict[str, Any]:
    """Encaminha uma pergunta ao RAG e retorna fallback seguro em caso de erro."""
    try:
        return _request("POST", "/rag/query", json_payload={"question": question})
    except (httpx.HTTPError, ValueError) as exc:
        return _fallback_payload(type(exc).__name__, question=question)


def get_ai_rag_health() -> dict[str, Any]:
    """Consulta o health check do AI/RAG Service para diagnostico do backend."""
    try:
        return _request("GET", "/health")
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "unavailable",
            "service": "ai-rag-service",
            "provider": "backend-fallback",
            "error": type(exc).__name__,
        }

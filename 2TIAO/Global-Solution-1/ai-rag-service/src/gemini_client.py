import os
from dataclasses import dataclass

import httpx


DEFAULT_MODEL = "gemini-3.1-flash-lite"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


@dataclass(frozen=True)
class GeminiResult:
    """Representa a resposta gerada pelo Gemini e seus metadados principais."""

    text: str
    model: str
    provider: str = "google-ai-studio"


def get_gemini_model() -> str:
    """Retorna o modelo Gemini configurado por ambiente ou o padrao da POC."""
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL).removeprefix("models/")


def get_api_key() -> str | None:
    """Busca a chave do Google AI Studio nas variaveis aceitas pelo servico."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def is_gemini_configured() -> bool:
    """Indica se existe chave configurada para chamadas reais ao Gemini."""
    return bool(get_api_key())


def build_generation_payload(prompt: str, *, temperature: float = 0.2) -> dict:
    """Monta o corpo da requisicao de geracao de texto para a API do Gemini."""
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.9,
            "maxOutputTokens": 900,
        },
    }


def generate_text(prompt: str, *, temperature: float = 0.2, timeout: float = 30.0) -> GeminiResult:
    """Envia um prompt ao Gemini e retorna o texto gerado com metadados do modelo."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao configurada.")

    model = get_gemini_model()
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    response = httpx.post(
        url,
        params={"key": api_key},
        json=build_generation_payload(prompt, temperature=temperature),
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini nao retornou candidatos de resposta.")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini retornou resposta vazia.")
    return GeminiResult(text=text, model=model)

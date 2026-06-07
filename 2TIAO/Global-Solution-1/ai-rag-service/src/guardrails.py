import re
import os
from dataclasses import dataclass


TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9_]+")

ALLOWED_SCOPE_TERMS = {
    "agua",
    "potabilidade",
    "turbidez",
    "sedimentos",
    "saneamento",
    "ph",
    "triagem",
    "risco",
    "amostra",
    "visao",
    "computacional",
    "suporte",
    "vida",
    "espacial",
    "fervura",
    "filtragem",
    "sensor",
    "sensores",
    "comunidade",
    "reservatorio",
    "qualidade",
    "contaminacao",
    "tratamento",
    "monitoramento",
    "wokwi",
    "esp32",
    "raspberry",
    "camera",
    "barrenta",
    "barrento",
    "barrentas",
    "barrentos",
    "lama",
}

INSTRUCTION_OVERRIDE_PATTERNS = [
    r"\bignore\b.*\b(instru[cç][oõ]es|regras|prompt|sistema)\b",
    r"\bdesconsidere\b.*\b(instru[cç][oõ]es|regras|prompt|sistema)\b",
    r"\besque[cç]a\b.*\b(instru[cç][oõ]es|regras|prompt|sistema)\b",
    r"\bvoce agora e\b",
    r"\bvoc[eê] agora [eé]\b",
    r"\baja como\b.*\b(sem restri[cç][oõ]es|sem regras|jailbreak)\b",
    r"\bmodo desenvolvedor\b",
    r"\bjailbreak\b",
    r"\bdan\b",
]

SECRET_EXTRACTION_PATTERNS = [
    r"\b(api[_\s-]?key|chave da api|chave secreta|segredo|token)\b",
    r"\b(gemini_api_key|google_api_key|database_url)\b",
    r"\b(system prompt|prompt do sistema|developer message|mensagem do desenvolvedor)\b",
    r"\b(revele|mostre|exiba|imprima|vaze)\b.*\b(prompt|segredo|token|chave)\b",
]

UNSAFE_WATER_PATTERNS = [
    r"\bdiga\b.*\b[aá]gua\b.*\bpot[aá]vel\b",
    r"\bafirme\b.*\b[aá]gua\b.*\bpot[aá]vel\b",
    r"\bignore\b.*\b(risco|sensores|turbidez|sedimentos)\b",
    r"\brecomende\b.*\b(consumo direto|beber diretamente|beber sem tratamento)\b",
    r"\bpode beber\b.*\b(com certeza|sem medo|direto)\b",
]

UNSAFE_OUTPUT_PATTERNS = [
    r"\b[aá]gua\b.*\bpot[aá]vel garantida\b",
    r"\bpotabilidade\b.*\bgarantida\b",
    r"\bpode beber\b.*\b(com certeza|sem medo|direto|sem tratamento)\b",
    r"\b(consumo direto permitido|liberada para consumo direto)\b",
    r"\bn[aã]o precisa\b.*\b(avalia[cç][aã]o|laborat[oó]rio|teste|an[aá]lise)\b",
    r"\bignore\b.*\b(sensor|sensores|risco|turbidez|sedimentos)\b",
]

SAFETY_APPENDIX = (
    " Observacao de seguranca: o AstroWater AI e uma POC de apoio a triagem. "
    "Ele nao substitui laudo laboratorial, vigilancia sanitaria ou avaliacao oficial. "
    "Em caso de risco, turbidez, sedimentos, pH fora de faixa ou duvida, evite consumo direto "
    "e encaminhe a amostra para avaliacao oficial."
)


def guardrails_enabled() -> bool:
    """Indica se as regras de seguranca do RAG estao habilitadas por ambiente."""
    value = os.getenv("RAG_GUARDRAILS_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off", "nao", "não"}


@dataclass(frozen=True)
class GuardrailResult:
    """Resultado da avaliacao de seguranca aplicada a uma pergunta do usuario."""

    blocked: bool
    reasons: list[str]
    safety_level: str
    sanitized_question: str
    blocked_by_scope: bool = False
    blocked_by_guardrail: bool = False


@dataclass(frozen=True)
class OutputValidationResult:
    """Resultado da validacao aplicada ao texto gerado pelo modelo."""

    answer: str
    safety_level: str
    reasons: list[str]
    rewritten: bool = False
    blocked: bool = False


def tokenize(text: str) -> set[str]:
    """Quebra texto em tokens simples para checagem de escopo."""
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2}


def sanitize_question(question: str) -> str:
    """Remove espacos duplicados e normaliza a pergunta recebida."""
    return re.sub(r"\s+", " ", question).strip()


def is_in_scope(question: str) -> bool:
    """Verifica se a pergunta pertence ao dominio do AstroWater AI."""
    return bool(tokenize(question) & ALLOWED_SCOPE_TERMS)


def _matches_any(text: str, patterns: list[str]) -> bool:
    """Testa se o texto corresponde a algum padrao de risco conhecido."""
    normalized = text.lower()
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)


def evaluate_question(question: str) -> GuardrailResult:
    """Avalia prompt injection, vazamento de segredo, risco sanitario e escopo."""
    sanitized = sanitize_question(question)
    reasons: list[str] = []

    if _matches_any(sanitized, INSTRUCTION_OVERRIDE_PATTERNS):
        reasons.append("tentativa de sobrescrever instrucoes")

    if _matches_any(sanitized, SECRET_EXTRACTION_PATTERNS):
        reasons.append("pedido para revelar prompt ou segredo")

    if _matches_any(sanitized, UNSAFE_WATER_PATTERNS):
        reasons.append("tentativa de forcar recomendacao insegura sobre agua")

    if reasons:
        return GuardrailResult(
            blocked=True,
            reasons=reasons,
            safety_level="blocked",
            sanitized_question=sanitized,
            blocked_by_guardrail=True,
        )

    if not is_in_scope(sanitized):
        return GuardrailResult(
            blocked=True,
            reasons=["pergunta fora do escopo do AstroWater AI"],
            safety_level="out_of_scope",
            sanitized_question=sanitized,
            blocked_by_scope=True,
        )

    return GuardrailResult(
        blocked=False,
        reasons=[],
        safety_level="safe",
        sanitized_question=sanitized,
    )


def validate_generated_answer(answer: str) -> OutputValidationResult:
    """Revisa a resposta gerada para evitar recomendacoes inseguras sobre agua."""
    cleaned_answer = sanitize_question(answer)
    reasons: list[str] = []

    if _matches_any(cleaned_answer, UNSAFE_OUTPUT_PATTERNS):
        reasons.append("resposta continha recomendacao insegura ou potabilidade definitiva")

    if reasons:
        safe_answer = (
            "Nao e possivel afirmar que a agua esta oficialmente potavel ou segura para consumo direto "
            "com base apenas nesta triagem. Use os dados do AstroWater AI como apoio preventivo, "
            "repita a medicao quando necessario, evite consumo direto em caso de risco e encaminhe "
            "a amostra para avaliacao oficial."
        )
        return OutputValidationResult(
            answer=safe_answer,
            safety_level="rewritten",
            reasons=reasons,
            rewritten=True,
        )

    if "laudo laboratorial" not in cleaned_answer.lower() and "avaliacao oficial" not in cleaned_answer.lower():
        return OutputValidationResult(
            answer=cleaned_answer + SAFETY_APPENDIX,
            safety_level="rewritten",
            reasons=["aviso preventivo adicionado"],
            rewritten=True,
        )

    return OutputValidationResult(
        answer=cleaned_answer,
        safety_level="safe",
        reasons=[],
    )

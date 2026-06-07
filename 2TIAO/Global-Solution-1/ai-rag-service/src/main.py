from pydantic import BaseModel, Field
from fastapi import FastAPI

from .embeddings import get_embedding_dimension, get_embedding_model, is_embedding_configured
from .gemini_client import generate_text, get_gemini_model, is_gemini_configured
from .guardrails import OutputValidationResult, guardrails_enabled, validate_generated_answer
from .pgvector_status import check_pgvector_status
from .prompts import build_gemini_report_prompt
from .retrieval import answer_question, default_retrieval_metadata, retrieve_rag_context
from .reporting import ReportInput, generate_report

app = FastAPI(title="AstroWater AI RAG Service")


@app.get("/health")
def health() -> dict:
    """Retorna o estado do servico RAG, Gemini, embeddings, guardrails e pgvector."""
    pgvector = check_pgvector_status()
    return {
        "status": "ok",
        "service": "ai-rag-service",
        "geminiConfigured": str(is_gemini_configured()).lower(),
        "model": get_gemini_model(),
        "embeddingConfigured": str(is_embedding_configured()).lower(),
        "embeddingModel": get_embedding_model(),
        "embeddingDimension": str(get_embedding_dimension()),
        "guardrailsEnabled": str(guardrails_enabled()).lower(),
        "pgvectorAvailable": str(pgvector.available).lower(),
        "vectorChunksLoaded": str(pgvector.chunks_count),
        "knowledgeSourcesLoaded": str(pgvector.documents_count),
        "pgvectorError": pgvector.error or "",
    }


class ReportRequest(BaseModel):
    """Contrato de entrada para gerar relatorio IA de uma comunidade."""

    community: str
    finalRisk: str = Field(alias="final_risk")
    ph: float | None = None
    turbidity: float | None = None
    temperature: float | None = None
    hardness: float | None = None
    solids: float | None = None
    chloramines: float | None = None
    sulfate: float | None = None
    conductivity: float | None = None
    organicCarbon: float | None = None
    trihalomethanes: float | None = None
    mlTurbidity: float | None = None
    mlPotabilityPrediction: int | None = None
    mlPotabilityProbability: float | None = None
    mlQualityLabel: str | None = None
    mlModelName: str | None = None
    visualClass: str | None = None
    visualTurbidityScore: float | None = None
    particlesDetected: int | None = None
    reasons: list[str] = []
    context: str | None = None

    model_config = {"populate_by_name": True}


class QuestionRequest(BaseModel):
    """Contrato de entrada para perguntas livres ao RAG."""

    question: str


@app.post("/reports/generate")
def create_report(payload: ReportRequest) -> dict:
    """Gera relatorio de triagem combinando dados da API, RAG, Gemini e guardrails."""
    report_input = ReportInput(
        community=payload.community,
        final_risk=payload.finalRisk,
        ph=payload.ph,
        turbidity=payload.turbidity,
        temperature=payload.temperature,
        hardness=payload.hardness,
        solids=payload.solids,
        chloramines=payload.chloramines,
        sulfate=payload.sulfate,
        conductivity=payload.conductivity,
        organic_carbon=payload.organicCarbon,
        trihalomethanes=payload.trihalomethanes,
        ml_turbidity=payload.mlTurbidity,
        ml_potability_prediction=payload.mlPotabilityPrediction,
        ml_potability_probability=payload.mlPotabilityProbability,
        ml_quality_label=payload.mlQualityLabel,
        ml_model_name=payload.mlModelName,
        visual_class=payload.visualClass,
        visual_turbidity_score=payload.visualTurbidityScore,
        particles_detected=payload.particlesDetected,
        reasons=payload.reasons,
    )
    context = payload.context
    sources = []
    retrieval_metadata = default_retrieval_metadata()
    if context is None:
        query = " ".join(
            [
                payload.community,
                payload.finalRisk,
                payload.mlQualityLabel or "",
                payload.mlModelName or "",
                payload.visualClass or "",
                " ".join(payload.reasons),
            ]
        )
        rag_context = retrieve_rag_context(query)
        context = rag_context["context"]
        sources = rag_context["sources"]
        retrieval_metadata = {
            "embeddingModel": rag_context["embeddingModel"],
            "embeddingProvider": rag_context["embeddingProvider"],
            "embeddingFallbackUsed": rag_context["embeddingFallbackUsed"],
            "retrievalMethod": rag_context["retrievalMethod"],
        }

    report = generate_report(report_input, context)
    report["provider"] = "local-fallback"
    report["model"] = None
    report["blockedByGuardrail"] = False
    report["guardrailReasons"] = []
    report["safetyLevel"] = "safe"
    report["outputRewritten"] = False
    report.update(retrieval_metadata)

    if is_gemini_configured():
        try:
            result = generate_text(build_gemini_report_prompt(report_input, context))
            if guardrails_enabled():
                output_validation = validate_generated_answer(result.text)
            else:
                output_validation = OutputValidationResult(
                    answer=result.text,
                    safety_level="guardrails_disabled",
                    reasons=[],
                    rewritten=False,
                )
            report["generatedText"] = output_validation.answer
            report["provider"] = result.provider
            report["model"] = result.model
            report["safetyLevel"] = output_validation.safety_level
            report["guardrailReasons"] = output_validation.reasons
            report["outputRewritten"] = output_validation.rewritten
        except Exception as exc:
            report["generatedText"] = (
                "Gemini indisponivel nesta chamada. O servico manteve o relatorio deterministico local."
            )
            report["provider"] = "local-fallback"
            report["model"] = get_gemini_model()
            report["llmError"] = type(exc).__name__
            report["safetyLevel"] = "safe"
            report["guardrailReasons"] = []
            report["outputRewritten"] = False

    report["sources"] = sources
    return report


@app.post("/rag/query")
def query_rag(payload: QuestionRequest) -> dict:
    """Responde uma pergunta usando recuperacao RAG e validacoes de seguranca."""
    return answer_question(payload.question)

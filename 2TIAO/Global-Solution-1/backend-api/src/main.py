from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ai_rag_client import generate_ai_report, query_rag
from .mission_control import build_mission_control_plan
from .risk import classify_water_sample
from .schemas import CommunityStatus
from .schemas import VisualAnalysisCreate, WaterReadingCreate
from .store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Carrega dados iniciais quando a aplicacao FastAPI inicia."""
    store.load_seed()
    yield


app = FastAPI(title="AstroWater AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Retorna um health check simples do backend principal."""
    return {"status": "ok", "service": "backend-api"}


class RiskRequest(BaseModel):
    """Payload usado para testar a classificacao de risco diretamente pela API."""

    ph: float | None = None
    turbidity: float | None = None
    temperature: float | None = None
    visualClass: str | None = None


class RagQuestionRequest(BaseModel):
    """Payload usado para enviar perguntas ao modulo RAG pelo backend."""

    question: str


@app.post("/risk/classify")
def classify_risk(payload: RiskRequest) -> dict:
    """Classifica uma amostra isolada usando as regras de risco do backend."""
    result = classify_water_sample(
        ph=payload.ph,
        turbidity=payload.turbidity,
        temperature=payload.temperature,
        visual_class=payload.visualClass,
    )
    return result.to_dict()


@app.get("/communities")
def list_communities() -> list[dict]:
    """Lista as comunidades cadastradas para monitoramento na POC."""
    return [community.model_dump() for community in store.communities]


def build_ai_report_payload(status: CommunityStatus) -> dict:
    """Monta o payload completo enviado ao servico AI/RAG para gerar relatorio."""
    latest_reading = status.latestReading
    latest_visual = status.latestVisualAnalysis
    return {
        "community": status.community.name,
        "finalRisk": status.finalRisk,
        "ph": latest_reading.ph if latest_reading else None,
        "turbidity": latest_reading.turbidity if latest_reading else None,
        "temperature": latest_reading.temperature if latest_reading else None,
        "hardness": latest_reading.hardness if latest_reading else None,
        "solids": latest_reading.solids if latest_reading else None,
        "chloramines": latest_reading.chloramines if latest_reading else None,
        "sulfate": latest_reading.sulfate if latest_reading else None,
        "conductivity": latest_reading.conductivity if latest_reading else None,
        "organicCarbon": latest_reading.organicCarbon if latest_reading else None,
        "trihalomethanes": latest_reading.trihalomethanes if latest_reading else None,
        "mlTurbidity": latest_reading.mlTurbidity if latest_reading else None,
        "mlPotabilityPrediction": latest_reading.mlPotabilityPrediction if latest_reading else None,
        "mlPotabilityProbability": latest_reading.mlPotabilityProbability if latest_reading else None,
        "mlQualityLabel": latest_reading.mlQualityLabel if latest_reading else None,
        "mlModelName": latest_reading.mlModelName if latest_reading else None,
        "visualClass": latest_visual.visualClass if latest_visual else None,
        "visualTurbidityScore": latest_visual.visualTurbidityScore if latest_visual else None,
        "particlesDetected": latest_visual.particlesDetected if latest_visual else None,
        "reasons": status.reasons,
    }


@app.get("/communities/{community_id}/ai-report")
def get_community_ai_report(community_id: int) -> dict:
    """Gera ou recupera o relatorio IA da comunidade selecionada."""
    try:
        status = store.get_status(community_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if status.latestReading is None:
        return Response(status_code=204)

    report = generate_ai_report(build_ai_report_payload(status))
    report.setdefault("communityId", community_id)
    report.setdefault("community", status.community.name)
    report.setdefault("finalRisk", status.finalRisk)
    report.setdefault("localRecommendation", status.recommendation)
    return report


@app.post("/rag/query")
def proxy_rag_query(payload: RagQuestionRequest) -> dict:
    """Encaminha uma pergunta livre para o servico AI/RAG."""
    return query_rag(payload.question)


@app.post("/readings", status_code=201)
def create_reading(payload: WaterReadingCreate) -> dict:
    """Recebe uma leitura de sensores e salva com ML, risco e alertas."""
    try:
        reading = store.create_reading(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return reading.model_dump(mode="json")


@app.get("/readings/latest")
def get_latest_reading(communityId: int | None = None) -> dict:
    """Retorna a leitura mais recente geral ou de uma comunidade especifica."""
    try:
        reading = store.get_latest_reading(communityId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return reading.model_dump(mode="json")


@app.get("/readings/timeseries")
def list_readings_timeseries(
    communityId: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """Lista leituras recentes em formato de serie temporal para o dashboard."""
    try:
        readings = store.list_readings_timeseries(communityId, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [reading.model_dump(mode="json") for reading in readings]


@app.get("/readings/stats")
def get_reading_stats(communityId: int | None = None) -> dict:
    """Retorna estatisticas agregadas das leituras de sensores."""
    try:
        return store.get_reading_stats(communityId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/readings")
def list_readings(communityId: int | None = None) -> list[dict]:
    """Lista leituras persistidas, com filtro opcional por comunidade."""
    readings = store.readings
    if communityId is not None:
        readings = [reading for reading in readings if reading.communityId == communityId]
    return [reading.model_dump(mode="json") for reading in readings]


@app.post("/visual-analyses", status_code=201)
def create_visual_analysis(payload: VisualAnalysisCreate) -> dict:
    """Recebe a analise visual do Raspberry Pi e atualiza o status da comunidade."""
    try:
        analysis = store.create_visual_analysis(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis.model_dump(mode="json")


@app.get("/visual-analyses")
def list_visual_analyses(communityId: int | None = None) -> list[dict]:
    """Lista analises visuais, com filtro opcional por comunidade."""
    analyses = store.visual_analyses
    if communityId is not None:
        analyses = [analysis for analysis in analyses if analysis.communityId == communityId]
    return [analysis.model_dump(mode="json") for analysis in analyses]


@app.get("/status")
def list_statuses() -> list[dict]:
    """Retorna o status consolidado de todas as comunidades."""
    return [status.model_dump(mode="json") for status in store.list_statuses()]


@app.get("/status/{community_id}")
def get_status(community_id: int) -> dict:
    """Retorna o status consolidado de uma comunidade especifica."""
    try:
        status = store.get_status(community_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return status.model_dump(mode="json")


@app.get("/alerts")
def list_alerts(communityId: int | None = None) -> list[dict]:
    """Lista alertas gerados, com filtro opcional por comunidade."""
    alerts = store.alerts
    if communityId is not None:
        alerts = [alert for alert in alerts if alert.communityId == communityId]
    return [alert.model_dump(mode="json") for alert in alerts]


@app.get("/mission-control")
def get_mission_control() -> dict:
    """Monta o plano operacional de Mission Control para o frontend e automacao."""
    return build_mission_control_plan(store.list_statuses())

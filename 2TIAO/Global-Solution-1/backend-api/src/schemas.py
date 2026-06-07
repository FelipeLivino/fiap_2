from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


RISK_VALUES = {"verde", "amarelo", "laranja", "vermelho"}
VISUAL_CLASSES = {"transparente", "azulada", "limpa", "turva", "amarelada", "com sedimentos"}


class Community(BaseModel):
    """Representa uma comunidade monitorada pelo AstroWater AI."""

    id: int
    name: str
    location: str | None = None
    scenario: str | None = None
    expectedRisk: str | None = None


class WaterReadingCreate(BaseModel):
    """Payload de entrada para leituras enviadas por ESP32/Wokwi ou Node-RED."""

    model_config = ConfigDict(populate_by_name=True)

    communityId: int | None = None
    community: str | None = None
    deviceId: str = Field(alias="device_id")
    ph: float | None = Field(default=None, ge=0, le=14)
    turbidity: float | None = Field(default=None, ge=0, le=100)
    temperature: float | None = Field(default=None, ge=0, le=45)
    hardness: float | None = Field(default=None, alias="Hardness")
    solids: float | None = Field(default=None, alias="Solids")
    chloramines: float | None = Field(default=None, alias="Chloramines")
    sulfate: float | None = Field(default=None, alias="Sulfate")
    conductivity: float | None = Field(default=None, alias="Conductivity")
    organicCarbon: float | None = Field(default=None, alias="Organic_carbon")
    trihalomethanes: float | None = Field(default=None, alias="Trihalomethanes")
    mlTurbidity: float | None = Field(default=None, alias="Turbidity")
    networkSwitch: str | None = None
    mlPotabilityPrediction: int | None = None
    mlPotabilityProbability: float | None = None
    mlQualityLabel: str | None = None
    mlModelName: str | None = None
    edgeRisk: str | None = None
    timestamp: datetime | None = None
    source: str | None = None

    @field_validator("edgeRisk")
    @classmethod
    def validate_edge_risk(cls, value: str | None) -> str | None:
        """Normaliza e valida o risco calculado na borda pelo ESP32."""
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in RISK_VALUES:
            raise ValueError("edgeRisk deve ser verde, amarelo, laranja ou vermelho.")
        return normalized


class WaterReading(WaterReadingCreate):
    """Leitura persistida com id, comunidade resolvida e timestamp obrigatorio."""

    id: int
    communityId: int
    timestamp: datetime


class VisualAnalysisCreate(BaseModel):
    """Payload de entrada para analises visuais enviadas pelo Raspberry Pi."""

    model_config = ConfigDict(populate_by_name=True)

    communityId: int | None = None
    community: str | None = None
    deviceId: str = Field(alias="device_id")
    imageName: str | None = None
    visualClass: str
    visualTurbidityScore: float | None = Field(default=None, ge=0, le=100)
    particlesDetected: int | None = Field(default=None, ge=0)
    dominantColor: str | None = None
    modelName: str | None = None
    modelClass: str | None = None
    modelConfidence: float | None = Field(default=None, ge=0, le=1)
    pollutionScore: float | None = Field(default=None, ge=0, le=100)
    timestamp: datetime | None = None
    source: str | None = None

    @field_validator("visualClass")
    @classmethod
    def validate_visual_class(cls, value: str) -> str:
        """Normaliza e valida as classes visuais aceitas pela POC."""
        normalized = value.strip().lower()
        if normalized not in VISUAL_CLASSES:
            raise ValueError(
                "visualClass deve ser transparente, azulada, limpa, turva, amarelada ou com sedimentos."
            )
        return normalized


class VisualAnalysis(VisualAnalysisCreate):
    """Analise visual persistida com id, comunidade resolvida e timestamp."""

    id: int
    communityId: int
    timestamp: datetime


class Alert(BaseModel):
    """Alerta gerado a partir do status consolidado de uma comunidade."""

    id: int
    communityId: int
    severity: str
    message: str
    timestamp: datetime


class CommunityStatus(BaseModel):
    """Status consolidado que une comunidade, leitura, visao, risco e recomendacao."""

    community: Community
    latestReading: WaterReading | None
    latestVisualAnalysis: VisualAnalysis | None
    finalRisk: str
    reasons: list[str]
    recommendation: str

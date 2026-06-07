from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class RiskLevel(IntEnum):
    """Escala ordenada de prioridade usada para consolidar risco."""

    verde = 1
    amarelo = 2
    laranja = 3
    vermelho = 4


RISK_LABELS = {
    RiskLevel.verde: "verde",
    RiskLevel.amarelo: "amarelo",
    RiskLevel.laranja: "laranja",
    RiskLevel.vermelho: "vermelho",
}


@dataclass(frozen=True)
class PartialRisk:
    """Resultado parcial de uma fonte de evidencia, como pH, turbidez ou visual."""

    source: str
    risk: RiskLevel
    reason: str


@dataclass(frozen=True)
class RiskResult:
    """Resultado final de classificacao de uma amostra de agua."""

    final_risk: str
    partials: list[PartialRisk]
    reasons: list[str]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        """Converte o resultado de risco para o formato JSON usado pela API."""
        return {
            "finalRisk": self.final_risk,
            "partials": [
                {
                    "source": partial.source,
                    "risk": RISK_LABELS[partial.risk],
                    "reason": partial.reason,
                }
                for partial in self.partials
            ],
            "reasons": self.reasons,
            "recommendation": self.recommendation,
        }


def classify_ph(ph: float | None) -> PartialRisk:
    """Classifica o risco parcial com base na faixa de pH informada."""
    if ph is None:
        return PartialRisk("ph", RiskLevel.amarelo, "pH ausente; recomenda-se nova leitura.")
    if ph < 6.0:
        return PartialRisk("ph", RiskLevel.vermelho, "pH abaixo de 6.0 indica acidez elevada.")
    if ph < 6.5:
        return PartialRisk("ph", RiskLevel.amarelo, "pH entre 6.0 e 6.5 exige atencao.")
    if ph <= 8.5:
        return PartialRisk("ph", RiskLevel.verde, "pH dentro da faixa aceitavel para triagem.")
    if ph <= 9.0:
        return PartialRisk("ph", RiskLevel.amarelo, "pH entre 8.5 e 9.0 exige atencao.")
    return PartialRisk("ph", RiskLevel.vermelho, "pH acima de 9.0 indica alcalinidade elevada.")


def classify_turbidity(turbidity: float | None) -> PartialRisk:
    """Classifica o risco parcial com base na turbidez operacional em NTU."""
    if turbidity is None:
        return PartialRisk("turbidity", RiskLevel.amarelo, "Turbidez ausente; recomenda-se nova leitura.")
    if turbidity <= 5:
        return PartialRisk("turbidity", RiskLevel.verde, "Turbidez ate 5 NTU indica baixo sinal visual de particulas.")
    if turbidity <= 25:
        return PartialRisk("turbidity", RiskLevel.amarelo, "Turbidez acima de 5 ate 25 NTU exige atencao.")
    if turbidity <= 50:
        return PartialRisk("turbidity", RiskLevel.laranja, "Turbidez acima de 25 ate 50 NTU indica risco elevado.")
    return PartialRisk("turbidity", RiskLevel.vermelho, "Turbidez acima de 50 NTU indica condicao critica.")


def classify_temperature(temperature: float | None) -> PartialRisk:
    """Classifica o risco parcial com base na temperatura da amostra."""
    if temperature is None:
        return PartialRisk("temperature", RiskLevel.amarelo, "Temperatura ausente; recomenda-se nova leitura.")
    if temperature < 5:
        return PartialRisk("temperature", RiskLevel.amarelo, "Temperatura abaixo de 5C exige atencao operacional.")
    if temperature <= 30:
        return PartialRisk("temperature", RiskLevel.verde, "Temperatura dentro da faixa normal para triagem.")
    if temperature <= 35:
        return PartialRisk("temperature", RiskLevel.amarelo, "Temperatura acima de 30C exige atencao.")
    return PartialRisk("temperature", RiskLevel.laranja, "Temperatura acima de 35C aumenta risco de armazenamento.")


def classify_visual(visual_class: str | None) -> PartialRisk:
    """Classifica o risco parcial a partir da classe visual enviada pelo Raspberry Pi."""
    if not visual_class:
        return PartialRisk("visual", RiskLevel.amarelo, "Analise visual ausente; recomenda-se capturar imagem.")

    normalized = visual_class.strip().lower()
    if normalized in {"transparente", "limpa"}:
        return PartialRisk("visual", RiskLevel.verde, "Amostra sem indicio visual critico.")
    if normalized == "azulada":
        return PartialRisk("visual", RiskLevel.amarelo, "Coloracao azulada e incomum e exige atencao.")
    if normalized in {"turva", "amarelada"}:
        return PartialRisk("visual", RiskLevel.laranja, "Aspecto visual indica turbidez ou coloracao suspeita.")
    if normalized == "com sedimentos":
        return PartialRisk("visual", RiskLevel.vermelho, "Sedimentos visiveis elevam a triagem para estado critico.")

    return PartialRisk("visual", RiskLevel.amarelo, f"Classe visual desconhecida: {visual_class}.")


def consolidate_risk(partials: list[PartialRisk]) -> RiskLevel:
    """Combina riscos parciais e eleva prioridade quando ha multiplas evidencias."""
    base_risk = max(partial.risk for partial in partials)
    attention_count = sum(1 for partial in partials if partial.risk == RiskLevel.amarelo)
    if base_risk == RiskLevel.vermelho:
        return RiskLevel.vermelho
    if base_risk == RiskLevel.laranja and attention_count >= 1:
        return RiskLevel.vermelho
    if base_risk == RiskLevel.amarelo and attention_count >= 2:
        return RiskLevel.laranja
    return base_risk


def recommendation_for(risk: RiskLevel) -> str:
    """Retorna uma recomendacao preventiva para a prioridade consolidada."""
    if risk == RiskLevel.verde:
        return (
            "A amostra esta em prioridade de rotina na triagem automatizada. "
            "A classificacao e apoio operacional e nao substitui analise laboratorial oficial."
        )
    if risk == RiskLevel.amarelo:
        return (
            "A amostra esta em prioridade de atencao. Recomenda-se acompanhamento, "
            "nova medicao e cuidado preventivo."
        )
    if risk == RiskLevel.laranja:
        return (
            "A amostra esta em prioridade alta de triagem. Recomenda-se evitar consumo direto "
            "e priorizar nova verificacao ou tratamento preventivo quando apropriado."
        )
    return (
        "A amostra esta em prioridade critica na triagem automatizada. "
        "O consumo direto nao e recomendado. Encaminhe a amostra para avaliacao oficial quando possivel."
    )


def classify_water_sample(
    *,
    ph: float | None,
    turbidity: float | None,
    temperature: float | None,
    visual_class: str | None = None,
) -> RiskResult:
    """Executa a classificacao completa combinando sensores e visao computacional."""
    partials = [
        classify_ph(ph),
        classify_turbidity(turbidity),
        classify_temperature(temperature),
        classify_visual(visual_class),
    ]
    final_level = consolidate_risk(partials)
    return RiskResult(
        final_risk=RISK_LABELS[final_level],
        partials=partials,
        reasons=[partial.reason for partial in partials if partial.risk > RiskLevel.verde],
        recommendation=recommendation_for(final_level),
    )

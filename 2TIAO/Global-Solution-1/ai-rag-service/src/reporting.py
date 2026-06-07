from dataclasses import dataclass
from typing import Any


RISK_TITLES = {
    "verde": "Prioridade de rotina",
    "amarelo": "Prioridade de atencao",
    "laranja": "Prioridade alta de triagem",
    "vermelho": "Prioridade critica de triagem",
}

PRIORITY_LABELS = {
    "verde": "rotina",
    "amarelo": "atencao",
    "laranja": "prioridade alta",
    "vermelho": "prioridade critica",
}


@dataclass(frozen=True)
class ReportInput:
    """Agrupa os dados de sensores, ML e visao usados no relatorio de triagem."""

    community: str
    final_risk: str
    ph: float | None = None
    turbidity: float | None = None
    temperature: float | None = None
    hardness: float | None = None
    solids: float | None = None
    chloramines: float | None = None
    sulfate: float | None = None
    conductivity: float | None = None
    organic_carbon: float | None = None
    trihalomethanes: float | None = None
    ml_turbidity: float | None = None
    ml_potability_prediction: int | None = None
    ml_potability_probability: float | None = None
    ml_quality_label: str | None = None
    ml_model_name: str | None = None
    visual_class: str | None = None
    visual_turbidity_score: float | None = None
    particles_detected: int | None = None
    reasons: list[str] | None = None


def _fmt(value: float | int | None, suffix: str = "") -> str:
    """Formata valores opcionais para texto legivel no prompt e no relatorio."""
    if value is None:
        return "nao informado"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def build_prompt(data: ReportInput, context: str | None = None) -> str:
    """Monta o prompt base com contexto RAG, sensores, ML, visao e limites de seguranca."""
    context_block = context or "Sem contexto externo recuperado nesta etapa."
    ml_interpretation = _ml_summary(data)
    return f"""Voce e um assistente de saneamento para comunidades remotas.
Explique a triagem de qualidade da agua em linguagem simples, sem declarar laudo definitivo.

Contexto de apoio:
{context_block}

Dados da amostra:
- Comunidade: {data.community}
- Prioridade final de triagem: {PRIORITY_LABELS.get(data.final_risk.lower(), data.final_risk)}
- pH: {_fmt(data.ph)}
- Turbidez: {_fmt(data.turbidity, " NTU")}
- Temperatura: {_fmt(data.temperature, " C")}
- Hardness: {_fmt(data.hardness, " mg/L")}
- Solids: {_fmt(data.solids, " ppm")}
- Chloramines: {_fmt(data.chloramines, " ppm")}
- Sulfate: {_fmt(data.sulfate, " mg/L")}
- Conductivity: {_fmt(data.conductivity, " uS/cm")}
- Organic carbon: {_fmt(data.organic_carbon, " ppm")}
- Trihalomethanes: {_fmt(data.trihalomethanes, " ug/L")}
- Turbidity ML: {_fmt(data.ml_turbidity)}
- Perfil quimico estimado pelo modelo ML tabular: {ml_interpretation}
- Classe visual: {data.visual_class or "nao informada"}
- Score visual de turbidez: {_fmt(data.visual_turbidity_score)}
- Particulas detectadas: {_fmt(data.particles_detected)}
- Justificativas tecnicas: {"; ".join(data.reasons or []) or "sem justificativas adicionais"}

Explique divergencias entre o perfil quimico ML e a prioridade final quando elas existirem.
A prioridade final da POC e uma fusao de evidencias: sensores operacionais, modelo ML tabular e visao computacional.
Responda com resumo, explicacao, acoes preventivas e limite de seguranca.
"""


def _sensor_summary(data: ReportInput) -> str:
    """Resume os principais sinais operacionais da amostra analisada."""
    return (
        f"pH {_fmt(data.ph)}, turbidez {_fmt(data.turbidity, ' NTU')}, "
        f"temperatura {_fmt(data.temperature, ' C')} e analise visual "
        f"{data.visual_class or 'nao informada'}."
    )


def _ml_summary(data: ReportInput) -> str:
    """Traduz o resultado do modelo tabular para uma explicacao compreensivel."""
    if not data.ml_quality_label:
        return "nao informado"
    label = {
        "potavel": "perfil quimico compativel",
        "nao_potavel": "perfil quimico incompativel",
        "dados_insuficientes": "dados insuficientes",
        "modelo_indisponivel": "modelo indisponivel",
        "erro_inferencia": "erro de inferencia",
    }.get(data.ml_quality_label, data.ml_quality_label)
    probability = _fmt(data.ml_potability_probability)
    model = data.ml_model_name or "modelo nao informado"
    return (
        f"{label} pelo modelo {model}, "
        f"predicao={_fmt(data.ml_potability_prediction)}, probabilidade={probability}"
    )


def _actions_for_risk(risk: str) -> list[str]:
    """Seleciona acoes preventivas de acordo com a prioridade final de triagem."""
    if risk == "verde":
        return [
            "Manter o monitoramento periodico.",
            "Registrar novas leituras para acompanhar mudancas no historico.",
            "Usar analise oficial quando houver exigencia sanitaria.",
        ]
    if risk == "amarelo":
        return [
            "Realizar nova medicao para confirmar o sinal de atencao.",
            "Evitar consumo por pessoas vulneraveis ate nova verificacao.",
            "Aplicar filtragem ou fervura quando fizer sentido para o contexto local.",
        ]
    if risk == "laranja":
        return [
            "Evitar consumo direto da amostra.",
            "Aplicar medidas preventivas como filtragem e fervura quando apropriado.",
            "Priorizar coleta de nova amostra e verificacao por responsavel local.",
        ]
    return [
        "Nao recomendar consumo direto da amostra.",
        "Isolar a fonte ou reservatorio ate nova verificacao.",
        "Encaminhar amostra para avaliacao oficial quando possivel.",
        "Comunicar responsaveis pela comunidade ou equipe de apoio.",
    ]


def generate_report(data: ReportInput, context: str | None = None) -> dict[str, Any]:
    """Gera um relatorio deterministico local usado como fallback ou base para Gemini."""
    risk = data.final_risk.lower()
    title = RISK_TITLES.get(risk, "Triagem de qualidade da agua")
    reasons = data.reasons or []
    actions = _actions_for_risk(risk)

    if risk == "verde":
        summary = (
            f"A amostra da {data.community} esta em prioridade de rotina na triagem automatizada."
        )
    elif risk == "amarelo":
        summary = (
            f"A amostra da {data.community} esta em prioridade de atencao e deve ser acompanhada."
        )
    elif risk == "laranja":
        summary = (
            f"A amostra da {data.community} esta em prioridade alta para verificacao preventiva."
        )
    else:
        summary = (
            f"A amostra da {data.community} esta em prioridade critica na triagem automatizada."
        )

    explanation = (
        f"A avaliacao combinou sensores e visao computacional: {_sensor_summary(data)} "
        f"A prioridade final foi classificada como {PRIORITY_LABELS.get(risk, risk)}."
    )
    if data.ml_quality_label:
        explanation += (
            f" O modelo tabular indicou {_ml_summary(data)}. "
            "Esse resultado e tratado como evidencia auxiliar, porque a prioridade final tambem considera "
            "telemetria operacional, sedimentos e analise visual."
        )
    if reasons:
        explanation += " Principais motivos: " + " ".join(reasons)

    limitation = (
        "Este resultado e uma triagem tecnologica de apoio. Ele nao substitui laudo laboratorial, "
        "vigilancia sanitaria ou avaliacao de profissional responsavel."
    )

    return {
        "title": title,
        "risk": risk,
        "summary": summary,
        "explanation": explanation,
        "preventiveActions": actions,
        "safetyLimit": limitation,
        "prompt": build_prompt(data, context),
    }

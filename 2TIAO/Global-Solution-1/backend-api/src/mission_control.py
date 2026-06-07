from datetime import datetime, timezone
from typing import Any

from .schemas import CommunityStatus


PRIORITY_ORDER = {"verde": 1, "amarelo": 2, "laranja": 3, "vermelho": 4}
PRIORITY_LABELS = {
    "verde": "Rotina",
    "amarelo": "Atencao",
    "laranja": "Alta",
    "vermelho": "Critica",
}


def build_mission_control_plan(statuses: list[CommunityStatus]) -> dict[str, Any]:
    """Monta a fila operacional de Mission Control a partir dos status das comunidades."""
    generated_at = datetime.now(timezone.utc).isoformat()
    queue = [_build_mission_item(status) for status in statuses]
    queue.sort(key=lambda item: (-item["priorityScore"], item["community"]))

    return {
        "missionCycleId": f"ASTRO-MISSION-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generatedAt": generated_at,
        "summary": {
            "totalCommunities": len(statuses),
            "critical": sum(1 for status in statuses if status.finalRisk == "vermelho"),
            "high": sum(1 for status in statuses if status.finalRisk == "laranja"),
            "attention": sum(1 for status in statuses if status.finalRisk == "amarelo"),
            "routine": sum(1 for status in statuses if status.finalRisk == "verde"),
        },
        "queue": queue,
    }


def _build_mission_item(status: CommunityStatus) -> dict[str, Any]:
    """Converte o status de uma comunidade em item priorizado da fila de missao."""
    priority = status.finalRisk
    latest_reading = status.latestReading
    latest_visual = status.latestVisualAnalysis
    reason = status.reasons[0] if status.reasons else "Sem anomalia relevante na ultima triagem."

    return {
        "communityId": status.community.id,
        "community": status.community.name,
        "location": status.community.location,
        "priority": priority,
        "priorityLabel": PRIORITY_LABELS.get(priority, priority),
        "priorityScore": PRIORITY_ORDER.get(priority, 0),
        "reason": reason,
        "nextActions": _next_actions(priority, status),
        "assignedModule": _assigned_module(priority, status),
        "slaMinutes": _sla_minutes(priority),
        "evidence": {
            "ph": latest_reading.ph if latest_reading else None,
            "turbidity": latest_reading.turbidity if latest_reading else None,
            "temperature": latest_reading.temperature if latest_reading else None,
            "mlProfile": latest_reading.mlQualityLabel if latest_reading else None,
            "visualClass": latest_visual.visualClass if latest_visual else None,
            "particlesDetected": latest_visual.particlesDetected if latest_visual else None,
        },
    }


def _next_actions(priority: str, status: CommunityStatus) -> list[str]:
    """Define proximas acoes recomendadas para cada nivel de prioridade."""
    latest_visual = status.latestVisualAnalysis
    has_sediments = latest_visual and latest_visual.visualClass == "com sedimentos"

    if priority == "vermelho":
        actions = [
            "Repetir leitura de pH e turbidez no ESP32.",
            "Capturar nova imagem com Raspberry Pi.",
            "Evitar consumo direto ate avaliacao oficial.",
            "Encaminhar amostra para laboratorio ou responsavel sanitario.",
        ]
        if has_sediments:
            actions.insert(2, "Inspecionar fonte ou reservatorio por sedimentos visiveis.")
        return actions

    if priority == "laranja":
        return [
            "Agendar nova leitura em curto prazo.",
            "Capturar imagem de confirmacao se houver alteracao visual.",
            "Orientar tratamento preventivo conforme protocolo local.",
        ]

    if priority == "amarelo":
        return [
            "Manter comunidade em observacao.",
            "Repetir medicao no proximo ciclo operacional.",
            "Comparar tendencia com historico do dashboard.",
        ]

    return [
        "Manter monitoramento periodico.",
        "Registrar telemetria para historico.",
    ]


def _assigned_module(priority: str, status: CommunityStatus) -> str:
    """Escolhe o modulo responsavel pela proxima acao operacional."""
    latest_visual = status.latestVisualAnalysis
    if latest_visual and latest_visual.visualClass in {"com sedimentos", "turva", "amarelada"}:
        return "vision-rpi"
    if priority in {"laranja", "vermelho"}:
        return "field-response"
    return "monitoring-loop"


def _sla_minutes(priority: str) -> int:
    """Define o SLA de atendimento em minutos conforme a prioridade."""
    return {
        "vermelho": 30,
        "laranja": 90,
        "amarelo": 240,
        "verde": 720,
    }.get(priority, 720)

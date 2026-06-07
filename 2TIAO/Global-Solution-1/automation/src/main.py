import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "automation" / "logs"
DEFAULT_BACKEND_URL = "http://localhost:8000"
FALLBACK_SCENARIOS = [
    {
        "communityId": 1,
        "title": "Turbidez elevada em captacao superficial",
        "expectedRisk": "vermelho",
    },
    {
        "communityId": 2,
        "title": "pH fora da faixa ideal em poco comunitario",
        "expectedRisk": "laranja",
    },
    {
        "communityId": 3,
        "title": "Reservatorio em condicao operacional estavel",
        "expectedRisk": "amarelo",
    },
]


@dataclass(frozen=True)
class Notification:
    """Representa uma notificacao simulada gerada a partir de um alerta."""

    alert_id: int
    severity: str
    message: str
    timestamp: str
    channel: str
    status: str


@dataclass(frozen=True)
class MissionOrder:
    """Representa uma ordem operacional enviada para a fila de Mission Control."""

    mission_cycle_id: str
    community_id: int
    community: str
    priority: str
    reason: str
    next_actions: list[str]
    assigned_module: str
    sla_minutes: int
    timestamp: str
    status: str


def load_alerts_from_backend(backend_url: str) -> list[dict]:
    """Consulta a API backend para buscar os alertas registrados no sistema."""
    response = httpx.get(f"{backend_url.rstrip('/')}/alerts", timeout=8)
    response.raise_for_status()
    return response.json()


def load_mission_control_from_backend(backend_url: str) -> dict:
    """Consulta a API backend para obter o plano atual de Mission Control."""
    response = httpx.get(f"{backend_url.rstrip('/')}/mission-control", timeout=8)
    response.raise_for_status()
    return response.json()


def wait_for_backend(backend_url: str, attempts: int = 6, delay: int = 5) -> list[dict]:
    """Aguarda o backend ficar disponivel antes de desistir da leitura de alertas."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return load_alerts_from_backend(backend_url)
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                print(f"Backend ainda indisponivel ({attempt}/{attempts}); nova tentativa em {delay}s.")
                time.sleep(delay)
    raise RuntimeError(last_error)


def load_fallback_alerts() -> list[dict]:
    """Carrega alertas de contingencia quando o backend nao esta acessivel."""
    scenarios_path = PROJECT_ROOT / "data" / "seed" / "scenarios.json"
    if scenarios_path.exists():
        scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    else:
        scenarios = FALLBACK_SCENARIOS
    alerts = []
    for index, scenario in enumerate(scenarios, start=1):
        risk = scenario["expectedRisk"]
        if risk not in {"laranja", "vermelho"}:
            continue
        alerts.append(
            {
                "id": index,
                "communityId": scenario["communityId"],
                "severity": risk,
                "message": f"Cenario {scenario['title']}: risco {risk} detectado na triagem.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    return alerts


def should_notify(alert: dict, min_severity: str) -> bool:
    """Verifica se um alerta atingiu a severidade minima configurada."""
    order = {"verde": 1, "amarelo": 2, "laranja": 3, "vermelho": 4}
    return order.get(alert.get("severity", ""), 0) >= order[min_severity]


def build_notification(alert: dict, channel: str) -> Notification:
    """Converte um alerta da API em uma notificacao simulada para registro."""
    return Notification(
        alert_id=int(alert["id"]),
        severity=alert["severity"],
        message=alert["message"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel=channel,
        status="simulated",
    )


def write_notification_log(notifications: list[Notification]) -> Path:
    """Grava notificacoes simuladas em arquivo JSONL para auditoria da automacao."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "notifications.jsonl"
    with path.open("a", encoding="utf-8") as file:
        for notification in notifications:
            file.write(json.dumps(notification.__dict__, ensure_ascii=False) + "\n")
    return path


def build_mission_orders(plan: dict, min_severity: str) -> list[MissionOrder]:
    """Cria ordens de missao a partir da fila retornada pelo Mission Control."""
    mission_cycle_id = plan.get("missionCycleId", "ASTRO-MISSION-FALLBACK")
    queue = plan.get("queue", [])
    orders = []
    for item in queue:
        if not should_notify({"severity": item.get("priority")}, min_severity):
            continue
        orders.append(
            MissionOrder(
                mission_cycle_id=mission_cycle_id,
                community_id=int(item["communityId"]),
                community=item["community"],
                priority=item["priority"],
                reason=item.get("reason", "Sem motivo informado."),
                next_actions=list(item.get("nextActions", [])),
                assigned_module=item.get("assignedModule", "mission-control"),
                sla_minutes=int(item.get("slaMinutes", 120)),
                timestamp=datetime.now(timezone.utc).isoformat(),
                status="queued",
            )
        )
    return orders


def write_mission_order_log(orders: list[MissionOrder]) -> Path:
    """Grava ordens de missao em arquivo JSONL para demonstrar rastreabilidade."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "mission_orders.jsonl"
    with path.open("a", encoding="utf-8") as file:
        for order in orders:
            file.write(json.dumps(order.__dict__, ensure_ascii=False) + "\n")
    return path


def run_once(backend_url: str, min_severity: str, channel: str) -> list[Notification]:
    """Executa um ciclo da automacao: Mission Control, alertas e notificacoes."""
    try:
        plan = load_mission_control_from_backend(backend_url)
        orders = build_mission_orders(plan, min_severity)
        if orders:
            order_path = write_mission_order_log(orders)
            print(f"{len(orders)} ordens de missao registradas em {order_path}.")
            for order in orders:
                print(f"[MISSION {order.priority.upper()}] {order.community}: {order.reason}")
        else:
            print(f"Nenhuma ordem de missao acima de {min_severity}.")
    except Exception as exc:
        print(f"Mission Control indisponivel; mantendo automacao por alertas. Motivo: {exc}")

    try:
        alerts = wait_for_backend(backend_url)
        source = "backend"
    except Exception as exc:
        print(f"Backend indisponivel, usando alertas seed. Motivo: {exc}")
        alerts = load_fallback_alerts()
        source = "fallback"

    notifications = [
        build_notification(alert, channel)
        for alert in alerts
        if should_notify(alert, min_severity)
    ]

    if notifications:
        log_path = write_notification_log(notifications)
        print(f"{len(notifications)} notificacoes simuladas registradas em {log_path} ({source}).")
        for notification in notifications:
            print(f"[{notification.severity.upper()}] {notification.message}")
    else:
        print(f"Nenhum alerta acima de {min_severity} encontrado ({source}).")
    return notifications


def parse_args() -> argparse.Namespace:
    """Configura os argumentos de linha de comando do modo once/watch."""
    parser = argparse.ArgumentParser(description="Automacao de alertas do AstroWater AI.")
    parser.add_argument("--mode", choices=["once", "watch"], default="once")
    parser.add_argument("--backend-url", default=os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL))
    parser.add_argument("--min-severity", choices=["laranja", "vermelho"], default=os.getenv("ALERT_MIN_SEVERITY", "laranja"))
    parser.add_argument("--channel", default=os.getenv("ALERT_CHANNEL", "console"))
    parser.add_argument("--interval", type=int, default=int(os.getenv("AUTOMATION_INTERVAL_SECONDS", "60")))
    return parser.parse_args()


def main() -> None:
    """Ponto de entrada da automacao, executando uma vez ou em loop recorrente."""
    load_dotenv()
    args = parse_args()

    if args.mode == "once":
        run_once(args.backend_url, args.min_severity, args.channel)
        return

    while True:
        run_once(args.backend_url, args.min_severity, args.channel)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

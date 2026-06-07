import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    psycopg = None
    dict_row = None

from .ml_quality import predict_potability
from .risk import classify_water_sample
from .schemas import (
    Alert,
    Community,
    CommunityStatus,
    VisualAnalysis,
    VisualAnalysisCreate,
    WaterReading,
    WaterReadingCreate,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = PROJECT_ROOT / "data" / "seed"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS communities (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT,
  scenario TEXT,
  expected_risk TEXT
);

CREATE TABLE IF NOT EXISTS water_readings (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  device_id TEXT NOT NULL,
  ph NUMERIC,
  turbidity NUMERIC,
  temperature NUMERIC,
  hardness NUMERIC,
  solids NUMERIC,
  chloramines NUMERIC,
  sulfate NUMERIC,
  conductivity NUMERIC,
  organic_carbon NUMERIC,
  trihalomethanes NUMERIC,
  ml_turbidity NUMERIC,
  network_switch TEXT,
  ml_potability_prediction INTEGER,
  ml_potability_probability NUMERIC,
  ml_quality_label TEXT,
  ml_model_name TEXT,
  edge_risk TEXT,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS hardness NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS solids NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS chloramines NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS sulfate NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS conductivity NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS organic_carbon NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS trihalomethanes NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_turbidity NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS network_switch TEXT;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_potability_prediction INTEGER;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_potability_probability NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_quality_label TEXT;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_model_name TEXT;

CREATE TABLE IF NOT EXISTS visual_analyses (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  device_id TEXT NOT NULL,
  image_name TEXT,
  visual_class TEXT,
  visual_turbidity_score NUMERIC,
  particles_detected INTEGER,
  dominant_color TEXT,
  model_name TEXT,
  model_class TEXT,
  model_confidence NUMERIC,
  pollution_score NUMERIC,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_name TEXT;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_class TEXT;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_confidence NUMERIC;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS pollution_score NUMERIC;

CREATE TABLE IF NOT EXISTS alerts (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

DEFAULT_COMMUNITIES = [
    {
        "id": 1,
        "name": "Comunidade Aurora",
        "location": "Regiao ribeirinha",
        "scenario": "Captacao de agua superficial",
        "expectedRisk": "Turbidez e sedimentos",
    },
    {
        "id": 2,
        "name": "Comunidade Horizonte",
        "location": "Regiao rural",
        "scenario": "Poco artesiano comunitario",
        "expectedRisk": "pH fora da faixa ideal",
    },
    {
        "id": 3,
        "name": "Comunidade Vega",
        "location": "Abrigo temporario",
        "scenario": "Reservatorio compartilhado",
        "expectedRisk": "Variacao de temperatura e alerta operacional",
    },
]

READING_METRICS = [
    "ph",
    "turbidity",
    "temperature",
    "hardness",
    "solids",
    "chloramines",
    "sulfate",
    "conductivity",
    "organicCarbon",
    "trihalomethanes",
    "mlTurbidity",
]

RISK_DISTRIBUTION_KEYS = ["verde", "amarelo", "laranja", "vermelho"]
RISK_PRIORITY = {"verde": 1, "amarelo": 2, "laranja": 3, "vermelho": 4}
ALERT_RISKS = {"laranja", "vermelho"}
ALERT_DEDUP_WINDOW = timedelta(minutes=10)


class InMemoryStore:
    """Repositorio em memoria usado para desenvolvimento local ou fallback sem PostgreSQL."""

    def __init__(self) -> None:
        """Inicializa listas internas e contadores incrementais do armazenamento em memoria."""
        self.communities: list[Community] = []
        self.readings: list[WaterReading] = []
        self.visual_analyses: list[VisualAnalysis] = []
        self.alerts: list[Alert] = []
        self._next_reading_id = 1
        self._next_visual_id = 1
        self._next_alert_id = 1

    def load_seed(self) -> None:
        """Carrega comunidades e dados seed em memoria, reconstruindo alertas iniciais."""
        self.communities = [Community(**item) for item in DEFAULT_COMMUNITIES]
        self.readings = self._load_seed_file("water_readings.json", WaterReading)
        self.visual_analyses = self._load_seed_file("visual_analyses.json", VisualAnalysis)
        self._next_reading_id = self._next_id(self.readings)
        self._next_visual_id = self._next_id(self.visual_analyses)
        self._rebuild_alerts()

    def create_reading(self, payload: WaterReadingCreate) -> WaterReading:
        """Cria uma leitura de agua, executa ML, salva em memoria e registra alerta se preciso."""
        community_id = self._resolve_community_id(payload.communityId, payload.community)
        ml_result = predict_potability(payload)
        reading = WaterReading(
            id=self._next_reading_id,
            communityId=community_id,
            community=payload.community,
            deviceId=payload.deviceId,
            ph=payload.ph,
            turbidity=payload.turbidity,
            temperature=payload.temperature,
            hardness=payload.hardness,
            solids=payload.solids,
            chloramines=payload.chloramines,
            sulfate=payload.sulfate,
            conductivity=payload.conductivity,
            organicCarbon=payload.organicCarbon,
            trihalomethanes=payload.trihalomethanes,
            mlTurbidity=payload.mlTurbidity,
            networkSwitch=payload.networkSwitch,
            mlPotabilityPrediction=ml_result["mlPotabilityPrediction"],
            mlPotabilityProbability=ml_result["mlPotabilityProbability"],
            mlQualityLabel=ml_result["mlQualityLabel"],
            mlModelName=ml_result["mlModelName"],
            edgeRisk=payload.edgeRisk,
            timestamp=payload.timestamp or self._now(),
            source=payload.source,
        )
        self._next_reading_id += 1
        self.readings.append(reading)
        self._register_alert_for_status(community_id)
        return reading

    def get_latest_reading(self, community_id: int | None = None) -> WaterReading:
        """Retorna a leitura mais recente geral ou de uma comunidade especifica."""
        readings = self.readings
        if community_id is not None:
            self._get_community(community_id)
            readings = [reading for reading in readings if reading.communityId == community_id]

        latest_reading = self._latest(readings)
        if latest_reading is None:
            if community_id is not None:
                raise ValueError(f"Nenhuma leitura encontrada para comunidade {community_id}.")
            raise ValueError("Nenhuma leitura encontrada.")
        return latest_reading

    def list_readings_timeseries(
        self, community_id: int | None = None, limit: int = 50
    ) -> list[WaterReading]:
        """Retorna as ultimas leituras em ordem cronologica para graficos do dashboard."""
        readings = self.readings
        if community_id is not None:
            self._get_community(community_id)
            readings = [reading for reading in readings if reading.communityId == community_id]

        latest_readings = sorted(readings, key=lambda item: (item.timestamp, item.id), reverse=True)[
            :limit
        ]
        return sorted(latest_readings, key=lambda item: (item.timestamp, item.id))

    def get_reading_stats(self, community_id: int | None = None) -> dict:
        """Calcula estatisticas agregadas das leituras armazenadas em memoria."""
        readings = self.readings
        if community_id is not None:
            self._get_community(community_id)
            readings = [reading for reading in readings if reading.communityId == community_id]
        return self._build_reading_stats(readings, community_id)

    def create_visual_analysis(self, payload: VisualAnalysisCreate) -> VisualAnalysis:
        """Cria uma analise visual, salva em memoria e atualiza alertas da comunidade."""
        community_id = self._resolve_community_id(payload.communityId, payload.community)
        analysis = VisualAnalysis(
            id=self._next_visual_id,
            communityId=community_id,
            community=payload.community,
            deviceId=payload.deviceId,
            imageName=payload.imageName,
            visualClass=payload.visualClass,
            visualTurbidityScore=payload.visualTurbidityScore,
            particlesDetected=payload.particlesDetected,
            dominantColor=payload.dominantColor,
            modelName=payload.modelName,
            modelClass=payload.modelClass,
            modelConfidence=payload.modelConfidence,
            pollutionScore=payload.pollutionScore,
            timestamp=payload.timestamp or self._now(),
            source=payload.source,
        )
        self._next_visual_id += 1
        self.visual_analyses.append(analysis)
        self._register_alert_for_status(community_id)
        return analysis

    def list_statuses(self) -> list[CommunityStatus]:
        """Monta o status consolidado de todas as comunidades cadastradas."""
        return [self.get_status(community.id) for community in self.communities]

    def get_status(self, community_id: int) -> CommunityStatus:
        """Consolida ultima leitura, ultima analise visual, risco e recomendacao."""
        community = self._get_community(community_id)
        latest_reading = self._latest(
            [reading for reading in self.readings if reading.communityId == community_id]
        )
        latest_visual = self._latest(
            [analysis for analysis in self.visual_analyses if analysis.communityId == community_id]
        )

        result = classify_water_sample(
            ph=latest_reading.ph if latest_reading else None,
            turbidity=latest_reading.turbidity if latest_reading else None,
            temperature=latest_reading.temperature if latest_reading else None,
            visual_class=latest_visual.visualClass if latest_visual else None,
        )
        return CommunityStatus(
            community=community,
            latestReading=latest_reading,
            latestVisualAnalysis=latest_visual,
            finalRisk=result.final_risk,
            reasons=result.reasons,
            recommendation=result.recommendation,
        )

    def _register_alert_for_status(self, community_id: int) -> None:
        """Cria alerta quando o status consolidado atinge prioridade laranja ou vermelha."""
        status = self.get_status(community_id)
        severity = self._alert_severity(status)
        if severity not in ALERT_RISKS:
            return

        timestamp = self._now()
        if self._should_skip_duplicate_alert(community_id, severity, timestamp):
            return

        self.alerts.append(
            Alert(
                id=self._next_alert_id,
                communityId=community_id,
                severity=severity,
                message=self._build_alert_message(status, severity),
                timestamp=timestamp,
            )
        )
        self._next_alert_id += 1

    def _rebuild_alerts(self) -> None:
        """Recalcula todos os alertas a partir do estado atual das comunidades."""
        self.alerts = []
        self._next_alert_id = 1
        for community in self.communities:
            self._register_alert_for_status(community.id)

    def _resolve_community_id(self, community_id: int | None, community_name: str | None) -> int:
        """Resolve a comunidade por id ou nome recebido no payload."""
        if community_id is not None:
            self._get_community(community_id)
            return community_id
        if community_name:
            normalized = community_name.strip().lower()
            for community in self.communities:
                if community.name.strip().lower() == normalized:
                    return community.id
        raise ValueError("Comunidade nao encontrada. Informe communityId ou community valido.")

    def _get_community(self, community_id: int) -> Community:
        """Busca uma comunidade pelo id ou levanta erro quando ela nao existe."""
        for community in self.communities:
            if community.id == community_id:
                return community
        raise ValueError(f"Comunidade {community_id} nao encontrada.")

    @staticmethod
    def _latest(items):
        """Retorna o item mais recente de uma lista usando o campo timestamp."""
        if not items:
            return None
        return max(items, key=lambda item: item.timestamp)

    def _should_skip_duplicate_alert(
        self, community_id: int, severity: str, timestamp: datetime
    ) -> bool:
        """Evita criar alertas duplicados para a mesma comunidade em janela curta."""
        community_alerts = [alert for alert in self.alerts if alert.communityId == community_id]
        latest_alert = self._latest(community_alerts)
        if latest_alert is None:
            return False
        if latest_alert.severity != severity:
            return False
        return timestamp - latest_alert.timestamp <= ALERT_DEDUP_WINDOW

    @staticmethod
    def _alert_severity(status: CommunityStatus) -> str:
        """Define a severidade do alerta considerando risco final e edgeRisk do ESP32."""
        latest_reading = status.latestReading
        edge_risk = latest_reading.edgeRisk if latest_reading else None
        if edge_risk and RISK_PRIORITY[edge_risk] > RISK_PRIORITY[status.finalRisk]:
            return edge_risk
        return status.finalRisk

    @staticmethod
    def _build_alert_message(status: CommunityStatus, severity: str) -> str:
        """Monta mensagem de alerta com causas provaveis e contexto da leitura."""
        latest_reading = status.latestReading
        causes = list(status.reasons[:2])
        if latest_reading and latest_reading.edgeRisk in ALERT_RISKS:
            causes.append(f"edgeRisk {latest_reading.edgeRisk} informado pelo ESP32")

        details = []
        if latest_reading:
            details.append(f"dispositivo {latest_reading.deviceId}")
            if latest_reading.turbidity is not None:
                details.append(f"turbidez operacional {latest_reading.turbidity:.1f} NTU")
            if latest_reading.ph is not None:
                details.append(f"pH {latest_reading.ph:.2f}")

        message = f"{status.community.name}: risco {severity} detectado."
        if causes:
            message += f" Causa provavel: {'; '.join(causes)}."
        if details:
            message += f" Contexto: {', '.join(details)}."
        return message

    @staticmethod
    def _build_reading_stats(readings: list[WaterReading], community_id: int | None = None) -> dict:
        """Gera resumo estatistico de metricas e distribuicao de risco."""
        latest_reading = InMemoryStore._latest(readings)
        return {
            "count": len(readings),
            "communityId": community_id,
            "latestRisk": latest_reading.edgeRisk if latest_reading else None,
            "metrics": {
                metric: InMemoryStore._metric_summary(
                    [getattr(reading, metric) for reading in readings]
                )
                for metric in READING_METRICS
            },
            "riskDistribution": {
                risk: sum(1 for reading in readings if reading.edgeRisk == risk)
                for risk in RISK_DISTRIBUTION_KEYS
            },
        }

    @staticmethod
    def _metric_summary(values: list[float | None]) -> dict:
        """Calcula minimo, media e maximo ignorando valores ausentes."""
        numeric_values = [value for value in values if value is not None]
        if not numeric_values:
            return {"min": None, "avg": None, "max": None}
        return {
            "min": min(numeric_values),
            "avg": round(sum(numeric_values) / len(numeric_values), 2),
            "max": max(numeric_values),
        }

    @staticmethod
    def _now() -> datetime:
        """Retorna o horario atual em UTC para padronizar timestamps."""
        return datetime.now(timezone.utc)

    @staticmethod
    def _read_json(path: Path):
        """Le um arquivo JSON usando UTF-8."""
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_seed_file(filename: str, schema):
        """Carrega um arquivo seed e converte cada item para o schema informado."""
        path = SEED_DIR / filename
        if not path.exists():
            return []
        return [schema(**item) for item in json.loads(path.read_text(encoding="utf-8"))]

    @staticmethod
    def _next_id(items) -> int:
        """Calcula o proximo id incremental com base nos itens existentes."""
        if not items:
            return 1
        return max(item.id for item in items) + 1


class PostgresStore(InMemoryStore):
    """Repositorio persistente baseado em PostgreSQL usado no Docker Compose."""

    def __init__(self, database_url: str) -> None:
        """Inicializa o store PostgreSQL reaproveitando estruturas do store em memoria."""
        super().__init__()
        self.database_url = database_url

    def load_seed(self) -> None:
        """Garante schema, insere comunidades padrao e recarrega caches locais."""
        self._ensure_schema()
        self._seed_communities()
        self.communities = self._load_communities()
        self.readings = self._load_readings()
        self.visual_analyses = self._load_visual_analyses()
        self.alerts = self._load_alerts()
        self._next_reading_id = self._next_id(self.readings)
        self._next_visual_id = self._next_id(self.visual_analyses)
        self._next_alert_id = self._next_id(self.alerts)

    def create_reading(self, payload: WaterReadingCreate) -> WaterReading:
        """Persiste uma leitura no PostgreSQL, executa ML e registra alerta se necessario."""
        community_id = self._resolve_community_id(payload.communityId, payload.community)
        timestamp = payload.timestamp or self._now()
        ml_result = predict_potability(payload)
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO water_readings
                  (community_id, device_id, ph, turbidity, temperature, hardness, solids,
                   chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                   ml_turbidity, network_switch, ml_potability_prediction,
                   ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                   source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, community_id, device_id, ph, turbidity, temperature, hardness,
                  solids, chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                  ml_turbidity, network_switch, ml_potability_prediction,
                  ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                  source, created_at
                """,
                (
                    community_id,
                    payload.deviceId,
                    payload.ph,
                    payload.turbidity,
                    payload.temperature,
                    payload.hardness,
                    payload.solids,
                    payload.chloramines,
                    payload.sulfate,
                    payload.conductivity,
                    payload.organicCarbon,
                    payload.trihalomethanes,
                    payload.mlTurbidity,
                    payload.networkSwitch,
                    ml_result["mlPotabilityPrediction"],
                    ml_result["mlPotabilityProbability"],
                    ml_result["mlQualityLabel"],
                    ml_result["mlModelName"],
                    payload.edgeRisk,
                    payload.source,
                    timestamp,
                ),
            ).fetchone()
            conn.commit()
        reading = self._reading_from_row(row, payload.community)
        self.readings.append(reading)
        self._register_alert_for_status(community_id)
        return reading

    def get_latest_reading(self, community_id: int | None = None) -> WaterReading:
        """Busca no PostgreSQL a leitura mais recente geral ou por comunidade."""
        if community_id is not None:
            self._get_community(community_id)
            where_clause = "WHERE community_id = %s"
            params = (community_id,)
        else:
            where_clause = ""
            params = ()

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, community_id, device_id, ph, turbidity, temperature, hardness, solids,
                  chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                  ml_turbidity, network_switch, ml_potability_prediction,
                  ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                  source, created_at
                FROM water_readings
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()

        if row is None:
            if community_id is not None:
                raise ValueError(f"Nenhuma leitura encontrada para comunidade {community_id}.")
            raise ValueError("Nenhuma leitura encontrada.")
        return self._reading_from_row(row)

    def list_readings_timeseries(
        self, community_id: int | None = None, limit: int = 50
    ) -> list[WaterReading]:
        """Consulta leituras recentes no banco em ordem cronologica para series temporais."""
        if community_id is not None:
            self._get_community(community_id)
            where_clause = "WHERE community_id = %s"
            params = (community_id, limit)
        else:
            where_clause = ""
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, community_id, device_id, ph, turbidity, temperature, hardness, solids,
                  chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                  ml_turbidity, network_switch, ml_potability_prediction,
                  ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                  source, created_at
                FROM (
                  SELECT id, community_id, device_id, ph, turbidity, temperature, hardness, solids,
                    chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                    ml_turbidity, network_switch, ml_potability_prediction,
                    ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                    source, created_at
                  FROM water_readings
                  {where_clause}
                  ORDER BY created_at DESC, id DESC
                  LIMIT %s
                ) limited_readings
                ORDER BY created_at ASC, id ASC
                """,
                params,
            ).fetchall()
        return [self._reading_from_row(row) for row in rows]

    def get_reading_stats(self, community_id: int | None = None) -> dict:
        """Consulta leituras no banco e calcula estatisticas agregadas."""
        if community_id is not None:
            self._get_community(community_id)
            where_clause = "WHERE community_id = %s"
            params = (community_id,)
        else:
            where_clause = ""
            params = ()

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, community_id, device_id, ph, turbidity, temperature, hardness, solids,
                  chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                  ml_turbidity, network_switch, ml_potability_prediction,
                  ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                  source, created_at
                FROM water_readings
                {where_clause}
                ORDER BY created_at ASC, id ASC
                """,
                params,
            ).fetchall()
        return self._build_reading_stats([self._reading_from_row(row) for row in rows], community_id)

    def create_visual_analysis(self, payload: VisualAnalysisCreate) -> VisualAnalysis:
        """Persiste uma analise visual no PostgreSQL e atualiza alertas relacionados."""
        community_id = self._resolve_community_id(payload.communityId, payload.community)
        timestamp = payload.timestamp or self._now()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO visual_analyses
                  (community_id, device_id, image_name, visual_class, visual_turbidity_score,
                   particles_detected, dominant_color, model_name, model_class, model_confidence,
                   pollution_score, source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, community_id, device_id, image_name, visual_class,
                  visual_turbidity_score, particles_detected, dominant_color, model_name,
                  model_class, model_confidence, pollution_score, source, created_at
                """,
                (
                    community_id,
                    payload.deviceId,
                    payload.imageName,
                    payload.visualClass,
                    payload.visualTurbidityScore,
                    payload.particlesDetected,
                    payload.dominantColor,
                    payload.modelName,
                    payload.modelClass,
                    payload.modelConfidence,
                    payload.pollutionScore,
                    payload.source,
                    timestamp,
                ),
            ).fetchone()
            conn.commit()
        analysis = self._visual_from_row(row, payload.community)
        self.visual_analyses.append(analysis)
        self._register_alert_for_status(community_id)
        return analysis

    def _register_alert_for_status(self, community_id: int) -> None:
        """Persiste alerta no banco quando o status exige prioridade operacional."""
        status = self.get_status(community_id)
        severity = self._alert_severity(status)
        if severity not in ALERT_RISKS:
            return

        timestamp = self._now()
        if self._should_skip_duplicate_alert(community_id, severity, timestamp):
            return

        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO alerts (community_id, severity, message, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id, community_id, severity, message, created_at
                """,
                (
                    community_id,
                    severity,
                    self._build_alert_message(status, severity),
                    timestamp,
                ),
            ).fetchone()
            conn.commit()
        self.alerts.append(self._alert_from_row(row))

    def _connect(self):
        """Abre uma conexao PostgreSQL configurada para retornar linhas como dicionario."""
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg nao esta instalado. Use o ambiente Docker ou instale requirements.txt.")
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _ensure_schema(self) -> None:
        """Cria ou atualiza as tabelas necessarias para o backend funcionar."""
        with self._connect() as conn:
            for statement in SCHEMA_SQL.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(statement)
            conn.commit()

    def _seed_communities(self) -> None:
        """Insere comunidades padrao sem sobrescrever registros ja existentes."""
        with self._connect() as conn:
            for community in DEFAULT_COMMUNITIES:
                conn.execute(
                    """
                    INSERT INTO communities (id, name, location, scenario, expected_risk)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        community["id"],
                        community["name"],
                        community.get("location"),
                        community.get("scenario"),
                        community.get("expectedRisk"),
                    ),
                )
            conn.commit()

    def _load_communities(self) -> list[Community]:
        """Carrega comunidades persistidas no PostgreSQL."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, location, scenario, expected_risk FROM communities ORDER BY id"
            ).fetchall()
        return [
            Community(
                id=row["id"],
                name=row["name"],
                location=row["location"],
                scenario=row["scenario"],
                expectedRisk=row["expected_risk"],
            )
            for row in rows
        ]

    def _load_readings(self) -> list[WaterReading]:
        """Carrega leituras persistidas no PostgreSQL para cache local."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, community_id, device_id, ph, turbidity, temperature, hardness, solids,
                  chloramines, sulfate, conductivity, organic_carbon, trihalomethanes,
                  ml_turbidity, network_switch, ml_potability_prediction,
                  ml_potability_probability, ml_quality_label, ml_model_name, edge_risk,
                  source, created_at
                FROM water_readings ORDER BY id
                """
            ).fetchall()
        return [self._reading_from_row(row) for row in rows]

    def _load_visual_analyses(self) -> list[VisualAnalysis]:
        """Carrega analises visuais persistidas no PostgreSQL para cache local."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, community_id, device_id, image_name, visual_class,
                  visual_turbidity_score, particles_detected, dominant_color, model_name,
                  model_class, model_confidence, pollution_score, source, created_at
                FROM visual_analyses ORDER BY id
                """
            ).fetchall()
        return [self._visual_from_row(row) for row in rows]

    def _load_alerts(self) -> list[Alert]:
        """Carrega alertas persistidos no PostgreSQL para cache local."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, community_id, severity, message, created_at FROM alerts ORDER BY id"
            ).fetchall()
        return [self._alert_from_row(row) for row in rows]

    @staticmethod
    def _reading_from_row(row, community_name: str | None = None) -> WaterReading:
        """Converte uma linha SQL de water_readings para o schema WaterReading."""
        return WaterReading(
            id=row["id"],
            communityId=row["community_id"],
            community=community_name,
            deviceId=row["device_id"],
            ph=float(row["ph"]) if row["ph"] is not None else None,
            turbidity=float(row["turbidity"]) if row["turbidity"] is not None else None,
            temperature=float(row["temperature"]) if row["temperature"] is not None else None,
            hardness=float(row["hardness"]) if row.get("hardness") is not None else None,
            solids=float(row["solids"]) if row.get("solids") is not None else None,
            chloramines=float(row["chloramines"]) if row.get("chloramines") is not None else None,
            sulfate=float(row["sulfate"]) if row.get("sulfate") is not None else None,
            conductivity=float(row["conductivity"]) if row.get("conductivity") is not None else None,
            organicCarbon=(
                float(row["organic_carbon"]) if row.get("organic_carbon") is not None else None
            ),
            trihalomethanes=(
                float(row["trihalomethanes"]) if row.get("trihalomethanes") is not None else None
            ),
            mlTurbidity=float(row["ml_turbidity"]) if row.get("ml_turbidity") is not None else None,
            networkSwitch=row.get("network_switch"),
            mlPotabilityPrediction=row.get("ml_potability_prediction"),
            mlPotabilityProbability=(
                float(row["ml_potability_probability"])
                if row.get("ml_potability_probability") is not None
                else None
            ),
            mlQualityLabel=row.get("ml_quality_label"),
            mlModelName=row.get("ml_model_name"),
            edgeRisk=row["edge_risk"],
            timestamp=row["created_at"],
            source=row["source"],
        )

    @staticmethod
    def _visual_from_row(row, community_name: str | None = None) -> VisualAnalysis:
        """Converte uma linha SQL de visual_analyses para o schema VisualAnalysis."""
        return VisualAnalysis(
            id=row["id"],
            communityId=row["community_id"],
            community=community_name,
            deviceId=row["device_id"],
            imageName=row["image_name"],
            visualClass=row["visual_class"],
            visualTurbidityScore=(
                float(row["visual_turbidity_score"])
                if row["visual_turbidity_score"] is not None
                else None
            ),
            particlesDetected=row["particles_detected"],
            dominantColor=row["dominant_color"],
            modelName=row.get("model_name"),
            modelClass=row.get("model_class"),
            modelConfidence=(
                float(row["model_confidence"]) if row.get("model_confidence") is not None else None
            ),
            pollutionScore=(
                float(row["pollution_score"]) if row.get("pollution_score") is not None else None
            ),
            timestamp=row["created_at"],
            source=row["source"],
        )

    @staticmethod
    def _alert_from_row(row) -> Alert:
        """Converte uma linha SQL de alerts para o schema Alert."""
        return Alert(
            id=row["id"],
            communityId=row["community_id"],
            severity=row["severity"],
            message=row["message"],
            timestamp=row["created_at"],
        )


def create_store():
    """Escolhe PostgreSQL quando DATABASE_URL existe; caso contrario usa memoria."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url or psycopg is None:
        return InMemoryStore()
    return PostgresStore(database_url)


store = create_store()

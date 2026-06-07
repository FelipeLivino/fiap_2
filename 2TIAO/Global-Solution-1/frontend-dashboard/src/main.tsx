import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Risk = "verde" | "amarelo" | "laranja" | "vermelho";

type Community = {
  id: number;
  name: string;
  location?: string;
  scenario?: string;
  expectedRisk?: string;
};

type WaterReading = {
  id: number;
  communityId: number;
  deviceId: string;
  ph?: number | null;
  turbidity?: number | null;
  temperature?: number | null;
  hardness?: number | null;
  solids?: number | null;
  chloramines?: number | null;
  sulfate?: number | null;
  conductivity?: number | null;
  organicCarbon?: number | null;
  trihalomethanes?: number | null;
  mlTurbidity?: number | null;
  mlPotabilityPrediction?: number | null;
  mlPotabilityProbability?: number | null;
  mlQualityLabel?: string | null;
  mlModelName?: string | null;
  networkSwitch?: string | null;
  edgeRisk?: Risk;
  timestamp: string;
  source?: string;
};

type VisualAnalysis = {
  id: number;
  communityId: number;
  deviceId: string;
  imageName?: string;
  visualClass: string;
  visualTurbidityScore?: number;
  particlesDetected?: number;
  dominantColor?: string;
  modelName?: string | null;
  modelClass?: string | null;
  modelConfidence?: number | null;
  pollutionScore?: number | null;
  timestamp: string;
  source?: string;
};

type CommunityStatus = {
  community: Community;
  latestReading: WaterReading | null;
  latestVisualAnalysis: VisualAnalysis | null;
  finalRisk: Risk;
  reasons: string[];
  recommendation: string;
};

type Alert = {
  id: number;
  communityId: number;
  severity: Risk;
  message: string;
  timestamp: string;
};

type MetricSummary = {
  min: number | null;
  avg: number | null;
  max: number | null;
};

type ReadingStats = {
  count: number;
  communityId: number | null;
  latestRisk: Risk | null;
  metrics: Record<string, MetricSummary>;
  riskDistribution: Record<Risk, number>;
};

type AiReportSource = {
  title?: string;
  source?: string;
  sourceUrl?: string;
  sourceScore?: number;
  retrievalMethod?: string;
  trustedLevel?: string;
};

type AiReport = {
  generatedText?: string;
  summary?: string;
  explanation?: string;
  preventiveActions?: string[];
  safetyLimit?: string;
  provider?: string;
  model?: string | null;
  safetyLevel?: string;
  outputRewritten?: boolean;
  retrievalMethod?: string;
  embeddingModel?: string;
  sources?: AiReportSource[];
  localRecommendation?: string;
};

type MissionOrder = {
  communityId: number;
  community: string;
  location?: string | null;
  priority: Risk;
  priorityLabel: string;
  priorityScore: number;
  reason: string;
  nextActions: string[];
  assignedModule: string;
  slaMinutes: number;
  evidence: {
    ph?: number | null;
    turbidity?: number | null;
    temperature?: number | null;
    mlProfile?: string | null;
    visualClass?: string | null;
    particlesDetected?: number | null;
  };
};

type MissionControlPlan = {
  missionCycleId: string;
  generatedAt: string;
  summary: {
    totalCommunities: number;
    critical: number;
    high: number;
    attention: number;
    routine: number;
  };
  queue: MissionOrder[];
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const riskOrder: Record<Risk, number> = {
  verde: 1,
  amarelo: 2,
  laranja: 3,
  vermelho: 4,
};

const fallbackStatuses: CommunityStatus[] = [
  {
    community: {
      id: 1,
      name: "Comunidade Aurora",
      location: "Regiao ribeirinha",
      scenario: "Captacao de agua superficial",
      expectedRisk: "Turbidez e sedimentos",
    },
    latestReading: {
      id: 4,
      communityId: 1,
      deviceId: "ASTRO-ESP32-001",
      ph: 6.5,
      turbidity: 68.2,
      temperature: 27.1,
      edgeRisk: "vermelho",
      timestamp: "2026-05-29T14:00:00-03:00",
      source: "seed",
    },
    latestVisualAnalysis: {
      id: 3,
      communityId: 1,
      deviceId: "ASTRO-RPI-CAM-001",
      imageName: "aurora_sedimentos_001.jpg",
      visualClass: "com sedimentos",
      visualTurbidityScore: 86,
      particlesDetected: 216,
      dominantColor: "marrom",
      timestamp: "2026-05-29T14:05:00-03:00",
      source: "seed",
    },
    finalRisk: "vermelho",
    reasons: ["Turbidez acima de 50 NTU indica condicao critica.", "Sedimentos visiveis elevam a triagem para estado critico."],
    recommendation: "O consumo direto nao e recomendado. Encaminhe a amostra para avaliacao oficial quando possivel.",
  },
  {
    community: {
      id: 2,
      name: "Comunidade Horizonte",
      location: "Regiao rural",
      scenario: "Poco artesiano comunitario",
      expectedRisk: "pH fora da faixa ideal",
    },
    latestReading: {
      id: 8,
      communityId: 2,
      deviceId: "ASTRO-ESP32-002",
      ph: 9.3,
      turbidity: 6.2,
      temperature: 24.5,
      edgeRisk: "vermelho",
      timestamp: "2026-05-29T14:00:00-03:00",
      source: "seed",
    },
    latestVisualAnalysis: {
      id: 5,
      communityId: 2,
      deviceId: "ASTRO-RPI-CAM-002",
      imageName: "horizonte_azulada_001.jpg",
      visualClass: "azulada",
      visualTurbidityScore: 18,
      particlesDetected: 12,
      dominantColor: "azul claro",
      timestamp: "2026-05-29T12:05:00-03:00",
      source: "seed",
    },
    finalRisk: "vermelho",
    reasons: ["pH acima de 9.0 indica alcalinidade elevada.", "Coloracao azulada e incomum e exige atencao."],
    recommendation: "A amostra foi classificada como critica na triagem automatizada.",
  },
  {
    community: {
      id: 3,
      name: "Comunidade Vega",
      location: "Abrigo temporario",
      scenario: "Reservatorio compartilhado",
      expectedRisk: "Variacao de temperatura e alerta operacional",
    },
    latestReading: {
      id: 12,
      communityId: 3,
      deviceId: "ASTRO-ESP32-003",
      ph: 8.7,
      turbidity: 28.1,
      temperature: 37.6,
      edgeRisk: "laranja",
      timestamp: "2026-05-29T14:00:00-03:00",
      source: "seed",
    },
    latestVisualAnalysis: {
      id: 7,
      communityId: 3,
      deviceId: "ASTRO-RPI-CAM-003",
      imageName: "vega_turva_001.jpg",
      visualClass: "turva",
      visualTurbidityScore: 61,
      particlesDetected: 97,
      dominantColor: "cinza claro",
      timestamp: "2026-05-29T14:05:00-03:00",
      source: "seed",
    },
    finalRisk: "vermelho",
    reasons: ["Temperatura acima de 35C aumenta risco de armazenamento.", "Aspecto visual indica turbidez ou coloracao suspeita."],
    recommendation: "A amostra apresenta risco critico na triagem combinada. Evite consumo direto.",
  },
];

const fallbackReadings = fallbackStatuses
  .map((status) => status.latestReading)
  .filter(Boolean) as WaterReading[];

const fallbackVisualAnalyses = fallbackStatuses
  .map((status) => status.latestVisualAnalysis)
  .filter(Boolean) as VisualAnalysis[];

const fallbackAlerts: Alert[] = fallbackStatuses
  .filter((status) => riskOrder[status.finalRisk] >= riskOrder.laranja)
  .map((status, index) => ({
    id: index + 1,
    communityId: status.community.id,
    severity: status.finalRisk,
    message: `${status.community.name}: risco ${status.finalRisk} detectado na triagem.`,
    timestamp: status.latestReading?.timestamp ?? new Date().toISOString(),
  }));

const emptyMetric = { min: null, avg: null, max: null };

/**
 * Monta estatisticas locais quando a API nao esta disponivel e o dashboard usa dados demo.
 */
function buildFallbackStats(communityId: number, readings: WaterReading[]): ReadingStats {
  const selected = readings.filter((reading) => reading.communityId === communityId);
  const latest = selected.at(-1);
  return {
    count: selected.length,
    communityId,
    latestRisk: latest?.edgeRisk ?? null,
    metrics: {
      ph: summarize(selected.map((reading) => reading.ph)),
      turbidity: summarize(selected.map((reading) => reading.turbidity)),
      temperature: summarize(selected.map((reading) => reading.temperature)),
      hardness: emptyMetric,
      solids: emptyMetric,
      chloramines: emptyMetric,
      sulfate: emptyMetric,
      conductivity: emptyMetric,
      organicCarbon: emptyMetric,
      trihalomethanes: emptyMetric,
      mlTurbidity: emptyMetric,
    },
    riskDistribution: {
      verde: selected.filter((reading) => reading.edgeRisk === "verde").length,
      amarelo: selected.filter((reading) => reading.edgeRisk === "amarelo").length,
      laranja: selected.filter((reading) => reading.edgeRisk === "laranja").length,
      vermelho: selected.filter((reading) => reading.edgeRisk === "vermelho").length,
    },
  };
}

/**
 * Calcula minimo, media e maximo ignorando valores nulos ou indefinidos.
 */
function summarize(values: Array<number | null | undefined>): MetricSummary {
  const numericValues = values.filter((value): value is number => value !== null && value !== undefined);
  if (!numericValues.length) return emptyMetric;
  return {
    min: Math.min(...numericValues),
    avg: numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length,
    max: Math.max(...numericValues),
  };
}

/**
 * Faz uma chamada HTTP na API backend e valida se a resposta foi bem-sucedida.
 */
async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Erro ${response.status} ao carregar ${path}`);
  }
  return response.json();
}

/**
 * Formata numeros para exibicao nos cards, usando "--" quando nao ha valor.
 */
function formatNumber(value?: number | null, decimals = 1) {
  if (value === undefined || value === null) return "--";
  return value.toFixed(decimals);
}

/**
 * Formata data e hora no padrao brasileiro para historico e alertas.
 */
function formatDate(value?: string | null) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/**
 * Formata apenas o horario usado no eixo do grafico de sensores.
 */
function formatTime(value?: string | null) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/**
 * Converte o codigo interno de risco para o texto completo exibido no dashboard.
 */
function riskLabel(risk: Risk) {
  const labels: Record<Risk, string> = {
    verde: "Rotina",
    amarelo: "Atencao",
    laranja: "Prioridade alta",
    vermelho: "Prioridade critica",
  };
  return labels[risk];
}

/**
 * Converte o codigo interno de risco para uma versao curta usada em badges e listas.
 */
function riskShortLabel(risk: Risk) {
  const labels: Record<Risk, string> = {
    verde: "Rotina",
    amarelo: "Atencao",
    laranja: "Alta",
    vermelho: "Critica",
  };
  return labels[risk];
}

/**
 * Traduz o rotulo tecnico do modelo de ML para uma mensagem mais amigavel.
 */
function qualityLabel(label?: string | null) {
  const labels: Record<string, string> = {
    potavel: "Sem alerta ML",
    nao_potavel: "Alerta ML",
    baixa_confianca: "Inconclusivo",
    dados_insuficientes: "Dados insuf.",
    modelo_indisponivel: "Modelo off",
    erro_inferencia: "Erro ML",
  };
  return label ? labels[label] ?? label : "--";
}

/**
 * Destaca divergencia quando o ML parece favoravel, mas a prioridade final e alta ou critica.
 */
function chemicalProfileLabel(label?: string | null, finalRisk?: Risk) {
  if (label === "potavel" && (finalRisk === "laranja" || finalRisk === "vermelho")) {
    return "Divergente";
  }
  return qualityLabel(label);
}

/**
 * Explica no card por que o perfil quimico ML deve ser tratado como evidencia auxiliar.
 */
function chemicalProfileHelper(reading?: WaterReading | null, finalRisk?: Risk) {
  if (!reading?.mlQualityLabel) {
    return "modelo indisponivel | evidencia auxiliar";
  }
  if (reading.mlQualityLabel === "baixa_confianca") {
    return `${reading.mlModelName ?? "modelo ML"} | baixa confianca`;
  }
  const modelName = reading.mlModelName ?? "modelo ML";
  if (reading.mlQualityLabel === "potavel" && (finalRisk === "laranja" || finalRisk === "vermelho")) {
    return `${modelName} | nao sobrepoe a prioridade ${riskShortLabel(finalRisk).toLowerCase()}`;
  }
  return `${modelName} | evidencia auxiliar`;
}

/**
 * Converte a classe visual da analise do Raspberry Pi em texto curto para a interface.
 */
function visualMetricLabel(label?: string | null) {
  if (!label) return "--";
  const labels: Record<string, string> = {
    "com sedimentos": "Sedimentos",
    transparente: "Transparente",
    azulada: "Azulada",
    limpa: "Limpa",
    turva: "Turva",
    amarelada: "Amarelada",
  };
  return labels[label] ?? label;
}

/**
 * Seleciona a principal justificativa tecnica de um status consolidado.
 */
function primaryReason(status: CommunityStatus) {
  return status.reasons[0] ?? "Sem justificativa tecnica adicional.";
}

/**
 * Cria um plano Mission Control local quando o backend nao responde.
 */
function buildFallbackMissionPlan(statuses: CommunityStatus[]): MissionControlPlan {
  const queue = statuses
    .map((status) => ({
      communityId: status.community.id,
      community: status.community.name,
      location: status.community.location,
      priority: status.finalRisk,
      priorityLabel: riskShortLabel(status.finalRisk),
      priorityScore: riskOrder[status.finalRisk],
      reason: primaryReason(status),
      nextActions: missionActionsForRisk(status.finalRisk),
      assignedModule: status.latestVisualAnalysis ? "vision-rpi" : "monitoring-loop",
      slaMinutes: missionSla(status.finalRisk),
      evidence: {
        ph: status.latestReading?.ph,
        turbidity: status.latestReading?.turbidity,
        temperature: status.latestReading?.temperature,
        mlProfile: status.latestReading?.mlQualityLabel,
        visualClass: status.latestVisualAnalysis?.visualClass,
        particlesDetected: status.latestVisualAnalysis?.particlesDetected,
      },
    }))
    .sort((a, b) => b.priorityScore - a.priorityScore);

  return {
    missionCycleId: "ASTRO-MISSION-DEMO",
    generatedAt: new Date().toISOString(),
    summary: {
      totalCommunities: statuses.length,
      critical: statuses.filter((status) => status.finalRisk === "vermelho").length,
      high: statuses.filter((status) => status.finalRisk === "laranja").length,
      attention: statuses.filter((status) => status.finalRisk === "amarelo").length,
      routine: statuses.filter((status) => status.finalRisk === "verde").length,
    },
    queue,
  };
}

/**
 * Define acoes operacionais padrao para cada prioridade de triagem.
 */
function missionActionsForRisk(risk: Risk) {
  if (risk === "vermelho") {
    return ["Repetir leitura ESP32", "Capturar nova imagem", "Evitar consumo direto", "Encaminhar amostra"];
  }
  if (risk === "laranja") {
    return ["Agendar nova leitura", "Confirmar imagem", "Orientar tratamento preventivo"];
  }
  if (risk === "amarelo") {
    return ["Manter observacao", "Repetir medicao no proximo ciclo"];
  }
  return ["Manter monitoramento periodico"];
}

/**
 * Retorna o SLA em minutos para cada nivel de prioridade.
 */
function missionSla(risk: Risk) {
  return { vermelho: 30, laranja: 90, amarelo: 240, verde: 720 }[risk];
}

/**
 * Remove marcacoes simples de Markdown para deixar o texto da IA limpo no dashboard.
 */
function cleanAiText(value?: string | null) {
  if (!value) return "";
  return value
    .replace(/\*\*/g, "")
    .replace(/###?/g, "")
    .replace(/\s+\n/g, "\n")
    .trim();
}

/**
 * Formata scores de recuperacao, confianca e similaridade exibidos nos metadados.
 */
function formatScore(value?: number | null) {
  if (value === undefined || value === null) return "--";
  return value.toFixed(2);
}

/**
 * Componente principal que carrega dados da API, controla abas e renderiza o dashboard.
 */
function App() {
  const [statuses, setStatuses] = useState<CommunityStatus[]>(fallbackStatuses);
  const [latestReading, setLatestReading] = useState<WaterReading | null>(fallbackReadings[0] ?? null);
  const [timeseries, setTimeseries] = useState<WaterReading[]>(fallbackReadings.filter((reading) => reading.communityId === 1));
  const [stats, setStats] = useState<ReadingStats>(buildFallbackStats(1, fallbackReadings));
  const [alerts, setAlerts] = useState<Alert[]>(fallbackAlerts);
  const [selectedCommunityId, setSelectedCommunityId] = useState(1);
  const [apiState, setApiState] = useState<"online" | "fallback" | "loading">("loading");
  const [aiReport, setAiReport] = useState<AiReport | null>(null);
  const [aiReportLoading, setAiReportLoading] = useState(false);
  const [aiReportError, setAiReportError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<"monitoring" | "mission">("monitoring");
  const [missionPlan, setMissionPlan] = useState<MissionControlPlan>(buildFallbackMissionPlan(fallbackStatuses));

  useEffect(() => {
    let active = true;
    // Carrega o status geral e os alertas iniciais para detectar se a API esta online.
    Promise.all([
      fetchJson<CommunityStatus[]>("/status"),
      fetchJson<Alert[]>("/alerts"),
    ])
      .then(([statusData, alertData]) => {
        if (!active) return;
        setStatuses(statusData);
        setAlerts(alertData);
        setSelectedCommunityId(statusData[0]?.community.id ?? 1);
        setApiState("online");
      })
      .catch(() => {
        if (!active) return;
        setApiState("fallback");
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    // Atualiza periodicamente a comunidade selecionada com leitura, serie temporal, estatisticas e alertas.
    const loadSelectedCommunity = () => {
      setApiState((current) => (current === "online" || current === "fallback" ? current : "loading"));
      Promise.all([
        fetchJson<WaterReading>(`/readings/latest?communityId=${selectedCommunityId}`).catch(() => null),
        fetchJson<WaterReading[]>(`/readings/timeseries?communityId=${selectedCommunityId}&limit=50`),
        fetchJson<ReadingStats>(`/readings/stats?communityId=${selectedCommunityId}`),
        fetchJson<Alert[]>(`/alerts?communityId=${selectedCommunityId}`),
      ])
        .then(([latestData, timeseriesData, statsData, alertData]) => {
          if (!active) return;
          setLatestReading(latestData);
          setTimeseries(timeseriesData);
          setStats(statsData);
          setAlerts(alertData);
          setApiState("online");
        })
        .catch(() => {
          if (!active) return;
          const fallbackSelected = fallbackReadings.filter((reading) => reading.communityId === selectedCommunityId);
          setLatestReading(fallbackSelected.at(-1) ?? null);
          setTimeseries(fallbackSelected);
          setStats(buildFallbackStats(selectedCommunityId, fallbackReadings));
          setAlerts(fallbackAlerts.filter((alert) => alert.communityId === selectedCommunityId));
          setApiState("fallback");
        });
    };

    loadSelectedCommunity();
    const intervalId = window.setInterval(loadSelectedCommunity, 5000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [selectedCommunityId]);

  useEffect(() => {
    let active = true;
    // Atualiza periodicamente a fila operacional de Mission Control.
    const loadMissionControl = () => {
      fetchJson<MissionControlPlan>("/mission-control")
        .then((plan) => {
          if (!active) return;
          setMissionPlan(plan);
        })
        .catch(() => {
          if (!active) return;
          setMissionPlan(buildFallbackMissionPlan(statuses));
        });
    };

    loadMissionControl();
    const intervalId = window.setInterval(loadMissionControl, 10000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [statuses]);

  const selectedStatus = useMemo(
    () => statuses.find((status) => status.community.id === selectedCommunityId) ?? statuses[0],
    [selectedCommunityId, statuses],
  );
  const selectedReadingId = selectedStatus?.latestReading?.id ?? null;

  useEffect(() => {
    if (!selectedReadingId) {
      setAiReport(null);
      setAiReportLoading(false);
      setAiReportError(null);
      return;
    }

    let active = true;
    setAiReportLoading(true);
    setAiReportError(null);

    // Gera relatorio IA somente quando existe leitura de sensores para evitar gasto sem evidencia.
    fetchJson<AiReport>(`/communities/${selectedCommunityId}/ai-report`)
      .then((report) => {
        if (!active) return;
        setAiReport(report);
        setAiReportLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setAiReport(null);
        setAiReportError("Relatorio IA indisponivel. Exibindo recomendacao local.");
        setAiReportLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedCommunityId, selectedReadingId]);

  const overview = useMemo(() => {
    // Calcula os totais do topo do dashboard a partir do status consolidado.
    const critical = statuses.filter((status) => status.finalRisk === "vermelho").length;
    const elevated = statuses.filter((status) => status.finalRisk === "laranja").length;
    const attention = statuses.filter((status) => status.finalRisk === "amarelo").length;
    return { critical, elevated, attention, total: statuses.length };
  }, [statuses]);

  const selectedAlerts = useMemo(
    () => alerts.filter((alert) => alert.communityId === selectedStatus?.community.id),
    [alerts, selectedStatus],
  );

  const aiReportText = cleanAiText(aiReport?.generatedText ?? aiReport?.summary);
  const aiReportSources = (aiReport?.sources ?? []).slice(0, 3);
  const hasSensorReading = Boolean(selectedStatus?.latestReading);

  if (!selectedStatus) {
    return <main className="page">Carregando dashboard...</main>;
  }

  return (
    <main className="page">
      <div className="space-scene" aria-hidden="true">
        <div className="jupiter" />
        <div className="europa" />
        <div className="orbit-line orbit-one" />
        <div className="orbit-line orbit-two" />
      </div>
      <header className="topbar">
        <div>
          <p className="eyebrow">Global Solution 2026.1 | Europa analog mission</p>
          <h1>AstroWater AI</h1>
          <p className="mission-copy">Triagem de agua inspirada em suporte a vida para ambientes extremos.</p>
        </div>
        <div className={`api-pill ${apiState}`}>
          <span />
          {apiState === "online" ? "API conectada" : apiState === "loading" ? "Conectando API" : "Dados demo"}
        </div>
      </header>

      <nav className="view-tabs" aria-label="Modos do dashboard">
        <button className={activeView === "monitoring" ? "active" : ""} onClick={() => setActiveView("monitoring")}>
          Monitoramento
        </button>
        <button className={activeView === "mission" ? "active" : ""} onClick={() => setActiveView("mission")}>
          Mission Control
        </button>
      </nav>

      {activeView === "mission" ? (
        <MissionControlView plan={missionPlan} />
      ) : (
        <>

      <section className="summary-grid" aria-label="Resumo operacional">
        <Summary title="Comunidades" value={overview.total} detail="monitoradas na POC" />
        <Summary title="Criticas" value={overview.critical} detail="prioridade critica" tone="danger" />
        <Summary title="Altas" value={overview.elevated} detail="prioridade alta" tone="warning" />
        <Summary title="Alertas" value={selectedAlerts.length} detail="da comunidade" tone="info" />
      </section>

      <section className="status-legend" aria-label="Legenda de prioridade de triagem">
        <div>
          <span>Legenda</span>
          <strong>Prioridade de triagem</strong>
        </div>
        <ul>
          <li><em className="risk-dot verde">Rotina</em><span>sem sinais criticos imediatos</span></li>
          <li><em className="risk-dot amarelo">Atencao</em><span>acompanhar e medir novamente</span></li>
          <li><em className="risk-dot laranja">Alta</em><span>priorizar verificacao preventiva</span></li>
          <li><em className="risk-dot vermelho">Critica</em><span>evitar consumo direto e acionar avaliacao oficial</span></li>
        </ul>
      </section>

      <section className="workspace">
        <aside className="sidebar" aria-label="Comunidades">
          <h2>Comunidades</h2>
          <div className="community-list">
            {statuses.map((status) => (
              <button
                className={`community-button ${status.community.id === selectedCommunityId ? "active" : ""}`}
                key={status.community.id}
                onClick={() => setSelectedCommunityId(status.community.id)}
              >
                <span>
                  <strong>{status.community.name}</strong>
                  <small>{status.community.location}</small>
                  <small className="community-reason">{primaryReason(status)}</small>
                </span>
                <em className={`risk-dot ${status.finalRisk}`}>{riskShortLabel(status.finalRisk)}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="detail">
          <div className="detail-header">
            <div>
              <h2>{selectedStatus.community.name}</h2>
              <p>{selectedStatus.community.scenario}</p>
            </div>
            <div className={`risk-badge ${selectedStatus.finalRisk}`}>
              <span>{riskLabel(selectedStatus.finalRisk)}</span>
              <strong>{riskShortLabel(selectedStatus.finalRisk)}</strong>
            </div>
          </div>

          <section className="priority-reasons" aria-label="Justificativas da prioridade atual">
            <div>
              <span>Por que esta prioridade?</span>
              <strong>{primaryReason(selectedStatus)}</strong>
            </div>
            <ul>
              {selectedStatus.reasons.slice(0, 4).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
              {!selectedStatus.reasons.length ? <li>Nenhum sinal de atencao foi destacado na ultima triagem.</li> : null}
            </ul>
          </section>

          <div className="metric-grid">
            <Metric label="pH" value={formatNumber(latestReading?.ph, 2)} helper="faixa ideal 6.5 a 8.5" />
            <Metric label="Turbidez" value={formatNumber(latestReading?.turbidity, 1)} unit="NTU" helper="ate 5 NTU em triagem" />
            <Metric label="Temperatura" value={formatNumber(latestReading?.temperature, 1)} unit="C" helper="5C a 30C" />
            <Metric label="Rede" value={latestReading?.networkSwitch ?? "--"} helper={latestReading?.deviceId ?? "sem dispositivo"} />
            <Metric label="Visual" value={visualMetricLabel(selectedStatus.latestVisualAnalysis?.visualClass)} helper={selectedStatus.latestVisualAnalysis?.dominantColor ?? "sem cor dominante"} />
            <Metric
              label="Perfil quimico ML"
              value={chemicalProfileLabel(latestReading?.mlQualityLabel, selectedStatus.finalRisk)}
              helper={chemicalProfileHelper(latestReading, selectedStatus.finalRisk)}
            />
          </div>

          <div className="content-grid">
            <section className="panel">
              <div className="panel-title">
                <h3>Historico de sensores</h3>
                <span>{timeseries.length} {timeseries.length === 1 ? "leitura" : "leituras"}</span>
              </div>
              <SensorChart readings={timeseries} />
              <div className="timeline">
                {timeseries.slice(-6).map((reading) => (
                  <div className="timeline-row" key={reading.id}>
                    <time>{formatDate(reading.timestamp)}</time>
                    <span>pH {formatNumber(reading.ph, 2)}</span>
                    <span>{formatNumber(reading.turbidity, 1)} NTU</span>
                    <strong className={`risk-text ${reading.edgeRisk ?? "verde"}`}>{reading.edgeRisk ?? "sem risco"}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-title">
                <h3>Perfil quimico ML</h3>
                <span>{stats.count} amostras</span>
              </div>
              <div className="ml-grid">
                <MetricMini label="Hardness" value={latestReading?.hardness} unit="mg/L" summary={stats.metrics.hardness} />
                <MetricMini label="Solids" value={latestReading?.solids} unit="ppm" summary={stats.metrics.solids} />
                <MetricMini label="Chloramines" value={latestReading?.chloramines} unit="ppm" summary={stats.metrics.chloramines} />
                <MetricMini label="Sulfate" value={latestReading?.sulfate} unit="mg/L" summary={stats.metrics.sulfate} />
                <MetricMini label="Conductivity" value={latestReading?.conductivity} unit="uS/cm" summary={stats.metrics.conductivity} />
                <MetricMini label="Organic carbon" value={latestReading?.organicCarbon} unit="ppm" summary={stats.metrics.organicCarbon} />
                <MetricMini label="Trihalomethanes" value={latestReading?.trihalomethanes} unit="ug/L" summary={stats.metrics.trihalomethanes} />
                <MetricMini label="Turbidity ML" value={latestReading?.mlTurbidity} unit="dataset" summary={stats.metrics.mlTurbidity} />
                <MetricMini label="Confianca ML" value={latestReading?.mlPotabilityProbability} unit="modelo" />
              </div>
            </section>

            <section className="panel">
              <div className="panel-title">
                <h3>Estatisticas</h3>
                <span>min / media / max</span>
              </div>
              <div className="stats-list">
                <StatsRow label="pH" metric={stats.metrics.ph} decimals={2} />
                <StatsRow label="Turbidez" metric={stats.metrics.turbidity} suffix="NTU" />
                <StatsRow label="Temperatura" metric={stats.metrics.temperature} suffix="C" />
              </div>
              <div className="risk-bars">
                {(["verde", "amarelo", "laranja", "vermelho"] as Risk[]).map((risk) => (
                  <RiskBar key={risk} risk={risk} count={stats.riskDistribution[risk] ?? 0} total={stats.count} />
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-title">
                <h3>Visao computacional</h3>
                <span>Raspberry Pi</span>
              </div>
              <div className="vision-box">
                <div className={`water-sample ${selectedStatus.latestVisualAnalysis?.visualClass?.replaceAll(" ", "-") ?? "limpa"}`} />
                <div>
                  <p>Classe visual</p>
                  <strong>{selectedStatus.latestVisualAnalysis?.visualClass ?? "--"}</strong>
                  <p>Score de turbidez</p>
                  <strong>{formatNumber(selectedStatus.latestVisualAnalysis?.visualTurbidityScore, 0)}</strong>
                  <p>Particulas</p>
                  <strong>{selectedStatus.latestVisualAnalysis?.particlesDetected ?? "--"}</strong>
                  <p>Modelo</p>
                  <strong>{selectedStatus.latestVisualAnalysis?.modelClass ?? "--"}</strong>
                  <p>Confianca</p>
                  <strong>{formatNumber(selectedStatus.latestVisualAnalysis?.modelConfidence, 2)}</strong>
                </div>
              </div>
            </section>

            <section className="panel ai-panel">
              <div className="panel-title">
                <h3>Relatorio IA</h3>
                <span>{!hasSensorReading ? "aguardando leitura" : aiReportLoading ? "gerando" : aiReport?.provider ?? "RAG + sensores"}</span>
              </div>
              {hasSensorReading ? (
                <div className="ai-status" aria-label="Metadados do relatorio IA">
                  <span>{aiReport?.provider ?? "local"}</span>
                  <span>{aiReport?.retrievalMethod ?? "sem recuperacao"}</span>
                  <span>{aiReport?.safetyLevel ?? "sem status"}</span>
                </div>
              ) : null}
              <p className="recommendation">
                {!hasSensorReading
                  ? "Relatorio IA aguardando a primeira leitura de sensores. Sem telemetria da amostra, o sistema nao aciona o modelo generativo nem consome tokens."
                  : aiReportLoading
                  ? "Gerando relatorio com dados da comunidade, sensores e base RAG..."
                  : aiReportText || selectedStatus.recommendation}
              </p>
              {aiReportError && hasSensorReading ? <p className="ai-error">{aiReportError}</p> : null}
              {!hasSensorReading ? (
                <div className="ai-block">
                  <strong>Proxima etapa</strong>
                  <ul className="reason-list">
                    <li>Enviar uma leitura pelo ESP32/Wokwi via MQTT.</li>
                    <li>Executar nova captura visual no Raspberry Pi quando houver amostra.</li>
                    <li>Gerar relatorio IA somente apos existir evidencia para analise.</li>
                  </ul>
                </div>
              ) : aiReport?.preventiveActions?.length ? (
                <div className="ai-block">
                  <strong>Acoes preventivas</strong>
                  <ul className="reason-list">
                    {aiReport.preventiveActions.map((action) => (
                      <li key={action}>{cleanAiText(action)}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <ul className="reason-list">
                  {selectedStatus.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
              {aiReport?.safetyLimit ? (
                <p className="ai-limit">{cleanAiText(aiReport.safetyLimit)}</p>
              ) : null}
              {hasSensorReading && aiReportSources.length ? (
                <div className="ai-sources">
                  <strong>Fontes</strong>
                  {aiReportSources.map((source, index) => (
                    <div className="ai-source" key={`${source.title ?? "fonte"}-${index}`}>
                      <span>{source.title ?? "Fonte recuperada"}</span>
                      <small>{source.trustedLevel ?? "fonte"} | score {formatScore(source.sourceScore)}</small>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-title">
                <h3>Alertas</h3>
                <span>{alerts.length} total</span>
              </div>
              <div className="alert-list">
                {selectedAlerts.slice(-5).map((alert) => (
                  <div className="alert-row" key={alert.id}>
                    <strong className={`risk-text ${alert.severity}`}>{alert.severity}</strong>
                    <span>{alert.message}</span>
                    <time>{formatDate(alert.timestamp)}</time>
                  </div>
                ))}
                {!selectedAlerts.length ? <p className="empty-state">Nenhum alerta para a comunidade selecionada.</p> : null}
              </div>
            </section>
          </div>
        </section>
      </section>
        </>
      )}
    </main>
  );
}

/**
 * Renderiza a aba Mission Control com a fila recorrente de ordens operacionais.
 */
function MissionControlView({ plan }: { plan: MissionControlPlan }) {
  return (
    <section className="mission-view" aria-label="Mission Control">
      <div className="mission-hero">
        <div>
          <p className="eyebrow">Mission Control Automation</p>
          <h2>Fila operacional de triagem</h2>
          <p>
            A automacao transforma telemetria, visao computacional e prioridade em ordens de acao para campo.
          </p>
        </div>
        <div className="mission-cycle">
          <span>Ciclo</span>
          <strong>{plan.missionCycleId}</strong>
          <small>{formatDate(plan.generatedAt)}</small>
        </div>
      </div>

      <div className="mission-summary">
        <Summary title="Criticas" value={plan.summary.critical} detail="SLA 30 min" tone="danger" />
        <Summary title="Altas" value={plan.summary.high} detail="SLA 90 min" tone="warning" />
        <Summary title="Atencao" value={plan.summary.attention} detail="acompanhar" tone="info" />
        <Summary title="Rotina" value={plan.summary.routine} detail="monitorar" />
      </div>

      <div className="mission-queue">
        {plan.queue.map((order, index) => (
          <article className={`mission-card ${order.priority}`} key={`${order.communityId}-${order.priority}`}>
            <div className="mission-rank">{String(index + 1).padStart(2, "0")}</div>
            <div className="mission-card-main">
              <div className="mission-card-head">
                <div>
                  <h3>{order.community}</h3>
                  <p>{order.reason}</p>
                </div>
                <em className={`risk-dot ${order.priority}`}>{order.priorityLabel}</em>
              </div>
              <div className="mission-meta">
                <span>Modulo: {order.assignedModule}</span>
                <span>SLA: {order.slaMinutes} min</span>
                <span>Visual: {visualMetricLabel(order.evidence.visualClass)}</span>
                <span>ML: {chemicalProfileLabel(order.evidence.mlProfile, order.priority)}</span>
              </div>
              <ol>
                {order.nextActions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ol>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

/**
 * Renderiza um grafico SVG simples com pH, turbidez e temperatura das ultimas leituras.
 */
function SensorChart({ readings }: { readings: WaterReading[] }) {
  const points = readings.slice(-20);
  const series = [
    { key: "ph", label: "pH", color: "#2f78bd", max: 14 },
    { key: "turbidity", label: "Turbidez", color: "#d78a1f", max: 100 },
    { key: "temperature", label: "Temp.", color: "#2f9b63", max: 45 },
  ] as const;

  if (!points.length) {
    return <div className="chart empty-state">Sem leituras para plotar.</div>;
  }

  return (
    <div className="chart" aria-label="Grafico de serie temporal">
      <svg viewBox="0 0 680 210" role="img">
        <line x1="44" y1="18" x2="44" y2="174" className="axis" />
        <line x1="44" y1="174" x2="660" y2="174" className="axis" />
        {[0, 1, 2, 3].map((step) => (
          <line key={step} x1="44" y1={18 + step * 52} x2="660" y2={18 + step * 52} className="gridline" />
        ))}
        {series.map((item) => {
          const path = points
            .map((reading, index) => {
              const rawValue = Number(reading[item.key] ?? 0);
              const x = 44 + (index * 616) / Math.max(points.length - 1, 1);
              const y = 174 - (Math.min(rawValue, item.max) / item.max) * 150;
              return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
            })
            .join(" ");
          return <path key={item.key} d={path} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" />;
        })}
        {points.map((reading, index) => (
          <text key={reading.id} x={44 + (index * 616) / Math.max(points.length - 1, 1)} y="198" textAnchor="middle">
            {index % 3 === 0 || index === points.length - 1 ? formatTime(reading.timestamp) : ""}
          </text>
        ))}
      </svg>
      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.key}>
            <i style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Renderiza um card compacto para parametros do modelo de Machine Learning.
 */
function MetricMini({ label, value, unit, summary }: { label: string; value?: number | null; unit: string; summary?: MetricSummary }) {
  return (
    <article className="metric-mini">
      <span>{label}</span>
      <strong>{formatNumber(value, 2)}</strong>
      <small>{unit}</small>
      <em>media {formatNumber(summary?.avg, 2)}</em>
    </article>
  );
}

/**
 * Renderiza uma linha de estatistica com minimo, media e maximo de uma metrica.
 */
function StatsRow({ label, metric, suffix = "", decimals = 1 }: { label: string; metric?: MetricSummary; suffix?: string; decimals?: number }) {
  return (
    <div className="stats-row">
      <span>{label}</span>
      <strong>{formatNumber(metric?.min, decimals)}{suffix ? ` ${suffix}` : ""}</strong>
      <strong>{formatNumber(metric?.avg, decimals)}{suffix ? ` ${suffix}` : ""}</strong>
      <strong>{formatNumber(metric?.max, decimals)}{suffix ? ` ${suffix}` : ""}</strong>
    </div>
  );
}

/**
 * Renderiza uma barra de distribuicao para cada nivel de risco.
 */
function RiskBar({ risk, count, total }: { risk: Risk; count: number; total: number }) {
  const width = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="risk-bar">
      <span className={`risk-text ${risk}`}>{risk}</span>
      <div>
        <i className={risk} style={{ width: `${width}%` }} />
      </div>
      <strong>{count}</strong>
    </div>
  );
}

/**
 * Renderiza um card de resumo usado no topo e na tela de Mission Control.
 */
function Summary({ title, value, detail, tone = "neutral" }: { title: string; value: number; detail: string; tone?: string }) {
  return (
    <article className={`summary ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

/**
 * Renderiza um card de metrica principal da comunidade selecionada.
 */
function Metric({ label, value, unit, helper }: { label: string; value: string; unit?: string; helper: string }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>
        {value}
        {unit ? <small>{unit}</small> : null}
      </strong>
      <em>{helper}</em>
    </article>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

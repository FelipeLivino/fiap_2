# backend-api

API principal do AstroWater AI.

## Visao para avaliacao

Este modulo e o nucleo da POC. Ele recebe dados do ESP32/Wokwi via Node-RED, recebe analises visuais do Raspberry Pi, executa o modelo de Machine Learning, consolida prioridade de triagem, registra historico no banco e entrega os dados ao dashboard.

O backend tambem e o ponto seguro de integracao com o AI/RAG Service. O frontend nao chama a IA diretamente; ele chama o backend, que monta o contexto e encaminha ao servico generativo.

Responsabilidades:

- Receber leituras do Wokwi ESP32.
- Receber resultados visuais do Raspberry Pi.
- Calcular risco consolidado da agua.
- Executar o modelo de Machine Learning de potabilidade antes de salvar leituras.
- Persistir historico, alertas e relatorios.
- Expor dados para o dashboard.

## Estrutura da pasta

```text
backend-api/
├── Dockerfile
├── README.md
├── requirements.txt
├── models/
│   ├── astrowater_potability_model.joblib
│   └── astrowater_potability_model_metadata.json
└── src/
    ├── __init__.py
    ├── ai_rag_client.py
    ├── main.py
    ├── mission_control.py
    ├── ml_quality.py
    ├── risk.py
    ├── schemas.py
    └── store.py
```

### Arquivos da raiz

| Arquivo | Resumo |
| --- | --- |
| `Dockerfile` | Define a imagem Docker do backend FastAPI. Instala dependencias, copia `src` e `models`, e executa a API na porta `8000`. |
| `README.md` | Documentacao do modulo backend, com endpoints, arquitetura, persistencia, ML, RAG e exemplos de payload. |
| `requirements.txt` | Dependencias Python da API, incluindo FastAPI, Uvicorn, Pydantic, psycopg, joblib, pandas e bibliotecas de suporte ao ML. |

### Pasta `models`

| Arquivo | Resumo |
| --- | --- |
| `astrowater_potability_model.joblib` | Modelo treinado no modulo `machine-learning`, usado para inferir o perfil quimico auxiliar da amostra. |
| `astrowater_potability_model_metadata.json` | Metadados do modelo, como lista de features esperadas e nome do melhor algoritmo treinado. |

### Pasta `src`

| Arquivo | Resumo |
| --- | --- |
| `__init__.py` | Marca `src` como pacote Python para imports internos. |
| `main.py` | Entrada FastAPI. Define endpoints de comunidades, leituras, analises visuais, status, alertas, risco, Mission Control e AI/RAG. |
| `schemas.py` | Define contratos Pydantic usados na API, como leitura de agua, analise visual, alerta e status consolidado. |
| `store.py` | Camada de persistencia. Implementa armazenamento em memoria e PostgreSQL, cria leituras, analises visuais, alertas e estatisticas. |
| `risk.py` | Motor de classificacao de risco. Classifica pH, turbidez, temperatura e classe visual, consolidando prioridade final. |
| `ml_quality.py` | Carrega o modelo treinado, extrai features da leitura e gera predicao auxiliar de potabilidade/confianca. |
| `mission_control.py` | Monta a fila operacional de Mission Control com prioridade, SLA, evidencias, modulo responsavel e proximas acoes. |
| `ai_rag_client.py` | Cliente HTTP usado pelo backend para chamar o `ai-rag-service`, gerar relatorios IA e aplicar fallback seguro. |

### Classes e estruturas principais

| Classe/estrutura | Arquivo | O que representa |
| --- | --- | --- |
| `RiskRequest` | `src/main.py` | Payload usado no endpoint `/risk/classify` para testar regras de risco sem persistir dados. |
| `RagQuestionRequest` | `src/main.py` | Payload usado para encaminhar perguntas ao AI/RAG Service. |
| `Community` | `src/schemas.py` | Comunidade monitorada pela POC, com nome, local, cenario e risco esperado. |
| `WaterReadingCreate` | `src/schemas.py` | Payload recebido de sensores via Node-RED/Wokwi, incluindo parametros operacionais e features do ML. |
| `WaterReading` | `src/schemas.py` | Leitura persistida com id, comunidade resolvida e timestamp. |
| `VisualAnalysisCreate` | `src/schemas.py` | Payload enviado pelo Raspberry Pi com classe visual, score, particulas e metadados do modelo. |
| `VisualAnalysis` | `src/schemas.py` | Analise visual persistida com id, comunidade e timestamp. |
| `Alert` | `src/schemas.py` | Alerta criado quando a prioridade consolidada ou `edgeRisk` chega a `laranja` ou `vermelho`. |
| `CommunityStatus` | `src/schemas.py` | Status consolidado da comunidade, unindo ultima leitura, ultima analise visual, risco, motivos e recomendacao. |
| `RiskLevel` | `src/risk.py` | Enum ordenado das prioridades `verde`, `amarelo`, `laranja` e `vermelho`. |
| `PartialRisk` | `src/risk.py` | Risco parcial gerado por uma evidencia especifica, como pH, turbidez ou visual. |
| `RiskResult` | `src/risk.py` | Resultado final da classificacao de risco com motivos e recomendacao. |
| `InMemoryStore` | `src/store.py` | Repositorio em memoria usado para desenvolvimento local ou fallback sem PostgreSQL. |
| `PostgresStore` | `src/store.py` | Repositorio persistente usado no Docker Compose quando `DATABASE_URL` esta configurada. |

### Funcoes principais

| Funcao | Arquivo | Resumo |
| --- | --- | --- |
| `lifespan` | `src/main.py` | Carrega seeds e prepara o store na inicializacao da API. |
| `create_reading` | `src/main.py` / `src/store.py` | Recebe, valida, persiste leitura de sensores, executa ML e registra alerta se necessario. |
| `create_visual_analysis` | `src/main.py` / `src/store.py` | Recebe a analise visual do Raspberry Pi e recalcula status/alertas. |
| `build_ai_report_payload` | `src/main.py` | Monta o contexto enviado ao AI/RAG Service para relatorio da comunidade. |
| `get_community_ai_report` | `src/main.py` | Endpoint que gera relatorio IA somente quando existe leitura de sensores. |
| `classify_water_sample` | `src/risk.py` | Combina pH, turbidez, temperatura e visual para gerar prioridade final. |
| `consolidate_risk` | `src/risk.py` | Junta riscos parciais e eleva prioridade quando ha multiplas evidencias. |
| `predict_potability` | `src/ml_quality.py` | Executa o modelo tabular e retorna predicao, probabilidade, label e nome do modelo. |
| `build_mission_control_plan` | `src/mission_control.py` | Gera a fila operacional usada pelo frontend e pelo modulo `automation`. |
| `generate_ai_report` | `src/ai_rag_client.py` | Chama o AI/RAG Service para gerar relatorio e usa fallback seguro em caso de erro. |
| `query_rag` | `src/ai_rag_client.py` | Encaminha perguntas livres ao RAG pelo backend. |
| `create_store` | `src/store.py` | Escolhe `PostgresStore` quando ha `DATABASE_URL`; caso contrario usa `InMemoryStore`. |

### Como os arquivos se conectam

```mermaid
flowchart TD
    Main["src/main.py\nEndpoints FastAPI"] --> Schemas["src/schemas.py\nContratos Pydantic"]
    Main --> Store["src/store.py\nPersistencia e cache"]
    Main --> Risk["src/risk.py\nClassificacao de prioridade"]
    Main --> Mission["src/mission_control.py\nFila operacional"]
    Main --> RagClient["src/ai_rag_client.py\nProxy AI/RAG"]
    Store --> ML["src/ml_quality.py\nModelo tabular"]
    Store --> Risk
    Store --> DB["PostgreSQL ou memoria"]
    RagClient --> Rag["ai-rag-service\nGemini + pgvector"]
    Mission --> Dashboard["frontend-dashboard\nMission Control"]
```

## Diagrama de arquitetura do backend

```mermaid
flowchart LR
    Wokwi["ESP32/Wokwi"] --> MQTT["MQTT"]
    MQTT --> NodeRed["Node-RED"]
    NodeRed --> Readings["POST /readings"]
    RPi["Raspberry Pi Camera"] --> Visual["POST /visual-analyses"]
    Readings --> ML["ml_quality.py"]
    Readings --> Store["store.py"]
    Visual --> Risk["risk.py"]
    ML --> Risk
    Store --> DB["PostgreSQL"]
    Risk --> Status["GET /status"]
    Status --> Frontend["Dashboard React"]
    Status --> Mission["GET /mission-control"]
    Status --> AiReport["GET /communities/{id}/ai-report"]
    AiReport --> Rag["AI/RAG Service"]
```

## Decisoes de arquitetura

- O ESP32 nao chama o backend diretamente; ele publica MQTT para economizar energia e simplificar o firmware.
- O Node-RED faz a ponte visual entre MQTT e REST API.
- O backend centraliza validacao, persistencia e regras de negocio.
- O modelo de ML e tratado como evidencia auxiliar, nao como laudo de potabilidade.
- O RAG fica atras do backend para proteger chaves e aplicar governanca.

## Endpoints

- `GET /health`: verifica se a API esta ativa.
- `GET /communities`: lista comunidades da POC.
- `POST /readings`: recebe leitura do Wokwi ESP32.
- `GET /readings`: lista leituras.
- `GET /readings/latest`: retorna a leitura mais recente geral ou filtrada por `communityId`.
- `GET /readings/timeseries`: retorna historico ordenado para graficos, com `communityId` e `limit`.
- `GET /readings/stats`: retorna estatisticas agregadas das leituras, com filtro opcional por `communityId`.
- `POST /visual-analyses`: recebe analise visual do Raspberry Pi.
- `GET /visual-analyses`: lista analises visuais.
- `GET /status`: lista status consolidado por comunidade.
- `GET /status/{community_id}`: retorna status consolidado de uma comunidade.
- `GET /alerts`: lista alertas gerados, com causa provavel, dispositivo e contexto da leitura.
- `POST /risk/classify`: classifica uma amostra sem persistir.

## Machine Learning de potabilidade

Quando `POST /readings` recebe uma leitura completa com os parametros do dataset `water_potability`, o backend carrega o modelo `SVM RBF` treinado em `machine-learning` e grava a predicao junto da leitura.

Campos adicionados na resposta e no banco:

- `mlPotabilityPrediction`: `1` para potavel, `0` para nao potavel.
- `mlPotabilityProbability`: probabilidade/confiança retornada pelo modelo quando disponivel.
- `mlQualityLabel`: `potavel`, `nao_potavel`, `baixa_confianca`, `dados_insuficientes`, `modelo_indisponivel` ou `erro_inferencia`.
- `mlModelName`: nome do modelo usado, por exemplo `SVM RBF`.

O backend so trata a classificacao do modelo como forte quando `mlPotabilityProbability >= 0.65`. Abaixo desse valor, a leitura e salva como `baixa_confianca`, porque a predicao nao deve sobrepor a prioridade consolidada por sensores e visao computacional.

Correspondencia dos status de ML:

| `mlQualityLabel` | Significado |
| --- | --- |
| `potavel` | Perfil quimico compativel com potabilidade no dataset. |
| `nao_potavel` | Perfil quimico nao compativel com potabilidade no dataset. |
| `baixa_confianca` | Probabilidade abaixo de `0.65`; resultado inconclusivo. |
| `dados_insuficientes` | Faltam parametros para inferencia. |
| `modelo_indisponivel` | Arquivo do modelo nao encontrado no backend. |
| `erro_inferencia` | Falha durante execucao do modelo. |

O fluxo correto fica:

```text
ESP32/Wokwi -> MQTT -> Node-RED -> POST /readings -> Backend -> Modelo ML -> PostgreSQL
```

## Motor de risco

O modulo `src/risk.py` classifica:

- pH
- turbidez
- temperatura
- classe visual da amostra

Endpoint inicial:

```http
POST /risk/classify
```

## Exemplo de leitura do Wokwi

```json
{
  "deviceId": "ASTRO-ESP32-001",
  "community": "Comunidade Aurora",
  "ph": 6.99,
  "turbidity": 29.3,
  "temperature": 25.0,
  "Hardness": 196.9,
  "Solids": 20984.4,
  "Chloramines": 7.13,
  "Sulfate": 333.8,
  "Conductivity": 422.1,
  "Organic_carbon": 14.2,
  "Trihalomethanes": 66.4,
  "Turbidity": 3.5,
  "edgeRisk": "laranja",
  "networkSwitch": "ON",
  "source": "wokwi-esp32"
}
```

## Consultar ultima leitura

```http
GET /readings/latest
GET /readings/latest?communityId=1
```

Sem `communityId`, a API retorna a leitura mais recente do sistema. Com `communityId`, retorna a leitura mais recente daquela comunidade. Caso a comunidade nao exista ou nao tenha leituras, a API retorna `404` com uma mensagem clara.

## Consultar serie temporal

```http
GET /readings/timeseries
GET /readings/timeseries?communityId=1&limit=50
```

A resposta vem ordenada do registro mais antigo para o mais recente dentro do limite solicitado. O parametro `limit` aceita valores de `1` a `500` e usa `50` como padrao.

## Consultar estatisticas

```http
GET /readings/stats
GET /readings/stats?communityId=1
```

A resposta inclui quantidade de leituras, ultimo risco, resumo `min`, `avg` e `max` dos parametros numericos e distribuicao dos riscos `verde`, `amarelo`, `laranja` e `vermelho`. Quando nao existem leituras, a API retorna `count` igual a `0`, metricas nulas e distribuicao zerada.

## Alertas

Alertas sao gerados quando o risco consolidado ou o `edgeRisk` do ESP32 chega a `laranja` ou `vermelho`. A mensagem inclui causa provavel, dispositivo, turbidez operacional e pH quando esses valores estao disponiveis. Para evitar repeticao excessiva, leituras da mesma comunidade com a mesma severidade nao geram outro alerta dentro de uma janela curta.

## Integracao com AI/RAG

O backend chama o `ai-rag-service` por meio da variavel `AI_RAG_BASE_URL`, usando `http://ai-rag-service:8001` no Docker Compose. O tempo maximo de espera e controlado por `AI_RAG_TIMEOUT_SECONDS`, com padrao de `60` segundos.

Esse timeout maior e importante porque a geracao com Gemini, busca vetorial e validacao de guardrails podem demorar mais que uma chamada REST comum. Se o limite for baixo, o servico RAG pode concluir com `200 OK`, mas o backend ja tera devolvido `backend-fallback` ao frontend.

## Testes

```bash
python -m unittest discover -s backend-api/tests
```

A suite cobre payload completo do Wokwi, campos normalizados, persistencia dos parametros de ML, ultima leitura, serie temporal, estatisticas, alertas, comunidade inexistente e validacoes de `pH` e `edgeRisk`.

## Exemplo de analise visual do Raspberry Pi

```json
{
  "deviceId": "ASTRO-RPI-CAM-001",
  "communityId": 1,
  "imageName": "aurora_turva_001.jpg",
  "visualClass": "turva",
  "visualTurbidityScore": 54,
  "particlesDetected": 84,
  "dominantColor": "marrom claro",
  "modelName": "astrowater_yolov8s_cls_best",
  "modelClass": "Plastic Water Bottle",
  "modelConfidence": 0.91,
  "pollutionScore": 85.4,
  "source": "raspberry-pi-camera+yolov8s-cls"
}
```

## Persistencia

A API usa PostgreSQL quando `DATABASE_URL` esta configurada. No Docker Compose, o backend recebe:

```text
postgresql://astrowater:astrowater@database:5432/astrowater
```

Quando `DATABASE_URL` nao existe ou as dependencias de Postgres nao estao instaladas no ambiente local, a API cai para armazenamento em memoria e carrega os dados iniciais de `data/seed`.

Tabelas principais:

- `communities`
- `water_readings`
- `visual_analyses`
- `alerts`

A tabela `water_readings` tambem persiste os parametros usados pelo modelo de Machine Learning:

- `hardness`
- `solids`
- `chloramines`
- `sulfate`
- `conductivity`
- `organic_carbon`
- `trihalomethanes`
- `ml_turbidity`
- `network_switch`

Exemplo:

```json
{
  "ph": 6.8,
  "turbidity": 37.9,
  "temperature": 26.3,
  "visualClass": "turva"
}
```

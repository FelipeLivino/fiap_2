# Base de fontes ouro do RAG

Esta pasta guarda fontes curadas para alimentar o RAG vetorial do AstroWater AI.

O objetivo e manter uma base auditavel, com origem clara e util para explicar recomendacoes sobre triagem de agua, saneamento preventivo, contaminantes, suporte de vida espacial e monitoramento remoto.

## Estrutura

```text
data/rag_sources/
  manifest.json
  raw/
  processed/
```

- `manifest.json`: catalogo das fontes, com URL, tipo, nivel de confianca e caminho local.
- `raw/`: textos brutos, resumos tecnicos ou notas de coleta preservando a referencia original.
- `processed/`: textos limpos e prontos para chunking, embedding e carga no `pgvector`.

## Politica de curadoria

As fontes devem priorizar:

- organizacoes oficiais de saude, saneamento, meio ambiente ou espaco;
- documentos tecnicos com origem verificavel;
- materiais diretamente relacionados ao escopo do AstroWater AI;
- textos que ajudem o RAG a responder com cautela, sem declarar potabilidade oficial.

Evitar:

- conteudo sem autoria clara;
- blogs opinativos sem base tecnica;
- copia integral desnecessaria de artigos ou paginas;
- material fora do escopo de agua, sensores, saneamento, suporte de vida espacial ou acoes preventivas.

## Uso na pipeline

Na Etapa 6, o script de ingestao devera:

1. ler `manifest.json`;
2. abrir os arquivos em `processed/`;
3. dividir os textos em chunks;
4. gerar embeddings;
5. salvar documentos e chunks nas tabelas `rag_documents` e `rag_chunks`.

## Niveis de confianca

- `gold`: fonte oficial ou documento tecnico altamente confiavel.
- `project`: documento produzido pela equipe para explicar a POC.
- `support`: fonte complementar usada apenas como apoio.


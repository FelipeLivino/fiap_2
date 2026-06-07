# Seed

Dados iniciais para popular a aplicacao durante a POC.

## Arquivos

- `communities.json`: comunidades ficticias usadas no MVP.
- `water_readings.json`: leituras simuladas de pH, turbidez e temperatura geradas pelo no Wokwi ESP32.
- `visual_analyses.json`: resultados simulados do modulo Raspberry Pi + camera.
- `scenarios.json`: cenarios combinando sensores e visao computacional com risco esperado.

## Comunidades

- Comunidade Aurora: captacao de agua superficial, com foco em turbidez e sedimentos.
- Comunidade Horizonte: poco artesiano, com foco em pH fora da faixa ideal.
- Comunidade Vega: abrigo temporario, com foco em temperatura e alerta operacional.

## Classes visuais

- `transparente`
- `azulada`
- `limpa`
- `turva`
- `amarelada`
- `com sedimentos`

## Niveis de risco

- `verde`: propria para triagem.
- `amarelo`: atencao.
- `laranja`: risco elevado.
- `vermelho`: impropria para triagem.

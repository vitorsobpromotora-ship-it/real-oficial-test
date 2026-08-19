# Roadmap v2 — Real Oficial Desktop

Funcionalidades planejadas e **não incluídas na v1**, em ordem sugerida de implementação.

## 1. Live Monitoring (Twitch / Kick / YouTube)

Acompanhar transmissões ao vivo e gerar cortes de highlights durante/logo após a live.

Desenho técnico proposto:
- Captura por **streamlink** (`streamlink <url> best -O`) alimentando um buffer circular em disco
  (segmentos .ts de 30s, janela de ~2h) — novo job de longa duração `live_monitor` (lane própria).
- Análise incremental: a cada N segmentos, extrair áudio → whisper incremental → RHPT em janela
  deslizante → picos acima de limiar disparam candidatos (Claude no trecho, com contexto curto).
- Sinal extra específico de live: **velocidade do chat** (IRC da Twitch / API do Kick) como quarto
  componente da curva RHPT (o pico de chat costuma ATRASAR 10–20s do momento — aplicar offset).
- Limite de monitoramentos simultâneos (config) — custo de CPU por stream é alto.
- UI: página "Lives" com cards de streams monitoradas, feed de highlights em tempo real e botão
  "virar corte" (reaproveita o pipeline padrão a partir do buffer).

## 2. Editor de timeline avançado

- Timeline com waveform + palavras clicáveis (dados já existem no DB);
- Remoção de trechos internos (silêncios/hesitações) com re-concat automático no filtergraph
  (o builder atual já suporta N segmentos — falta UI e recálculo de legendas);
- Ajuste manual do enquadramento por segmento (arrastar a janela de crop; editar `crop_plan`);
- Edição de legenda inline sobre o preview (word_overrides já suportado no motor).

## 3. Publicação automática

- Upload direto TikTok/Reels/Shorts via APIs oficiais (OAuth por conta, fila de publicação,
  agendamento). Requer registro de app nas plataformas.

## 4. Qualidade de reframe

- ASD real (active speaker detection, ex.: TalkNet/LR-ASD) substituindo a correlação
  de movimento de boca; suaviza troca de falante em mesas com 3+ pessoas.
- Diarização (pyannote) para rotular falantes na transcrição e nos cortes.

## 5. Desempenho

- CUDA opcional no faster-whisper (detecção de GPU + toggle em Configurações);
- Cache de análise por chunk (hash da transcrição) para reprocessamentos;
- Renderização com NVENC quando disponível (`-c:v h264_nvenc`).

## 6. Métricas de publicação

- Importar métricas reais (views/likes) por corte publicado e correlacionar com o score —
  fecha o ciclo da "qualidade do ranking" com dados de mercado.

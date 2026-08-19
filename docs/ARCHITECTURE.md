# Arquitetura — Real Oficial Desktop

## Visão geral

Dois processos cooperando na máquina do usuário:

| Processo | Stack | Papel |
|---|---|---|
| **App** | Electron + React 18 + TypeScript (Vite) | UI PT-BR, diálogos nativos, ciclo de vida do motor |
| **Motor (sidecar)** | Python 3.11 + FastAPI + SQLite (WAL) | Pipeline de IA, renderização, API REST local |

O app spawna o motor no boot (porta livre em 8756–8856), espera o `/health`, lê o token de
`<data_dir>/api_token` e conversa por HTTP + SSE. O motor se auto-encerra se o processo pai morrer
(watchdog `--parent-pid`) e aceita `POST /system/shutdown` para desligamento gracioso.

## Motor — módulos

```
engine/app/
├── main.py            FastAPI + lifespan (DB, token, JobRunner) + CLI (--port/--data-dir/--parent-pid)
├── config.py          diretórios (dados, modelos, assets — ciente de PyInstaller/_MEIPASS)
├── db/                SQLAlchemy 2.x, WAL, migrações user_version, settings store
├── jobs/              EventBus (SSE c/ replay), JobRunner (lanes pipeline=1, render=min(cpu,2), misc=2)
├── api/               rotas: projects, sources, cuts, renders, media, brand_kits, jobs,
│                      events (SSE), reports, settings, shorts (fachada), system
├── pipeline/
│   ├── orchestrator   job process_source: ingest → transcribe → analyze → reframe (checkpoints)
│   ├── ingest         yt-dlp / arquivo, ffprobe, wav 16k mono
│   ├── transcribe     faster-whisper (CTranslate2 int8 CPU), PT-BR, timestamps por palavra, VAD
│   ├── audio_features RHPT: RMS + pitch (autocorrelação FFT) + ritmo + eventos → curva de picos
│   ├── semantic       chunks ~12min c/ overlap 60s → Claude (saída estruturada) → 18 parâmetros
│   ├── heuristic      fallback local determinístico (picos + léxicos PT-BR)
│   ├── fusion         score final = 0.65×semântico(ponderado) + 0.35×RHPT
│   ├── candidates     snap a frases, dedup IoU>0.45, diversidade temporal, persistência ranqueada
│   ├── reframe        YuNet→Haar, cenas (histograma HSV), falante por movimento de boca, crop plan
│   ├── captions       ASS 1080×1920, karaokê {\k}, presets, quebra PT-BR, headline
│   ├── censor         wordlist normalizada (exata + prefixo*), intervalos mute/beep
│   └── render         filtergraph única passada + fila em lote
├── services/          ffmpeg (descoberta/execução/progresso), claude_client, model_assets
├── reports/           métricas (aproveitamento, economia, Spearman) + HTML Jinja2
└── schemas/           pydantic da API + ChunkAnalysis (18 parâmetros)
```

### Decisões técnicas relevantes

- **SSE, não WebSocket** — o tráfego em tempo real é unidirecional (motor→UI); comandos são POSTs.
  Replay por `Last-Event-ID` com ring buffer de 500 eventos; a UI usa `fetch-event-source`
  (permite header `Authorization`).
- **Jobs sem broker** — fila persistida na tabela `jobs` + workers asyncio no próprio processo
  (desktop não precisa de Redis/Celery). Estágios idempotentes com checkpoint em disco/DB ⇒
  retomada automática após restart.
- **Crop com variação temporal em UMA passada** — `split → trim/setpts/crop → concat → scale`,
  com `x` interpolado por expressão sem vírgulas (`x0+(x1-x0)*(t/D)`). Rejeitados: `sendcmd`
  (timing frágil) e renders intermediários por segmento (perda geracional).
- **Windows sem escape de caminho no filtro `ass`** — o ffmpeg roda com `cwd` no diretório
  temporário do render e caminhos RELATIVOS (`subs.ass`, `fonts/`).
- **Fontes longas (10h)** — input seeking (`-ss`/`-t`) no render; áudio processado em blocos de 1s
  via soundfile; palavras persistidas em lotes de 2000; frames amostrados só nos trechos dos cortes.
- **Claude** — `messages.parse()` com modelo pydantic (18 parâmetros tipados), thinking adaptativo,
  system prompt com `cache_control: ephemeral` (reuso entre ~50 chunks de um vídeo de 10h),
  registro de tokens/custo por chamada em `claude_calls`. Escada de fallback POR CHUNK:
  primário → `stop_reason=refusal`/erro → modelo de contingência → heurística local.
  Modo econômico opcional via Message Batches (−50%).
- **Detector facial em camadas** — YuNet ONNX (baixado no 1º uso, ~230 KB) quando disponível;
  senão Haar cascade que JÁ VEM no wheel do OpenCV 4.x ⇒ o produto nunca fica sem detector.
- **OpenCV fixado em <5** — o 5.x removeu o `CascadeClassifier` (fallback) do módulo principal.

## Fluxo do pipeline (job `process_source`)

| Estágio | Banda de progresso | Saída |
|---|---|---|
| ingest | 0–15% | arquivo gerenciado + wav 16k + metadados |
| transcribe | 15–55% | frases + palavras (timestamps) |
| analyze | 55–85% | candidatos com score 0–100 + 18 parâmetros |
| reframe | 85–100% | `crop_plan` por corte (ou blur_pad) |

Render (`render_cut`, lane `render`) é acionado por demanda: preview 540×960 (revisão) ou final
1080×1920 CRF 19 veryfast, `loudnorm I=-14`, `+faststart`.

## Dados

SQLite em `<data_dir>/real-oficial.sqlite3` (WAL). `<data_dir>` = `%USERPROFILE%\.real-oficial`
(ou `REAL_OFICIAL_DATA_DIR`; no app empacotado: `%APPDATA%/real-oficial/engine-data`).
Subpastas: `media/sources`, `media/audio`, `media/previews`, `renders/`, `models/`, `logs/`, `tmp/`.

## Empacotamento

- Motor: PyInstaller **onedir** (`engine/engine.spec`) — coleta ctranslate2/faster-whisper/
  onnxruntime; exclui torch/tensorflow (faster-whisper não usa torch). Smoke test em CI nos dois SOs.
- App: electron-builder **NSIS x64** com `extraResources`: `engine/` (PyInstaller), `ffmpeg/`
  (build GPL BtbN, processo separado) e fontes.
- Modelos whisper NÃO são embarcados (instalador ~250 MB): download no 1º uso para `models/`.

## Segurança

- API só em `127.0.0.1`, Bearer token aleatório (`secrets.token_urlsafe(32)`) gerado no 1º boot,
  arquivo `api_token` com chmod 600 (POSIX); comparação em tempo constante.
- Electron: `contextIsolation`, `sandbox`, sem `nodeIntegration`; preload expõe só a ponte mínima;
  CSP restrita a `127.0.0.1`.
- A chave da Anthropic fica no SQLite local e nunca é exibida completa pela API (mascarada).

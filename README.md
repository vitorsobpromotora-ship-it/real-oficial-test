# Real Oficial — Desktop (Windows 10/11)

**Real Oficial** transforma vídeos longos (podcasts, entrevistas, lives, aulas — até ~10h) em
**cortes verticais 9:16 prontos para TikTok, Reels e Shorts**, com inteligência artificial:

- 🎯 **Detecção automática de momentos** — análise multimodal: transcrição (semântica via Claude),
  áudio (**RHPT — Real HotPeak Tracking**: energia, pitch, ritmo de fala, risadas, pausas) e
  visão computacional (rostos/cenas)
- 🏆 **Score 0–100 por corte** com detalhamento em **18 parâmetros** (força do gancho, emoção,
  humor, completude, independência de contexto…) — priorize os melhores primeiro
- 📐 **Auto Reframe 16:9 → 9:16** — detecção facial (YuNet/Haar), atribuição de falante por
  movimento de boca, jump cuts entre falantes; fallback automático de fundo desfocado
- 💬 **Legendas automáticas em PT-BR** queimadas no vídeo (ASS/libass), com **karaokê palavra a
  palavra**, 4 presets e quebra de linha tipográfica em português
- 🔇 **Censura de palavrões** (beep 1 kHz ou mudo) com wordlist PT-BR extensível
- 🎨 **Brand Kit** — logo, cores, fonte e estilo reutilizáveis em todos os cortes
- ⚡ **Bulk Editing + renderização em lote** — aprove/estilize/renderize dezenas de cortes de uma vez
- 📊 **Relatórios** — taxa de aproveitamento, tempo economizado, correlação score×avaliação humana,
  custo de IA e tempos por estágio (HTML + JSON)
- 🔌 **API REST local** com Bearer token — inclusive a fachada `/shorts` no formato da API pública
  (enviar vídeo → consultar clipes com score → baixar MP4)

Processamento de mídia é **100% local** (FFmpeg + faster-whisper + OpenCV). A análise semântica usa a
**API do Claude** (modelo configurável: Opus 5 / Sonnet 5 / Haiku 4.5) com **fallback local por
heurística** quando não há chave de API — o app funciona offline, com qualidade editorial reduzida.

---

## Arquitetura

```
┌────────────────────────── Real Oficial (Electron) ──────────────────────────┐
│  UI React (PT-BR): Painel · Projeto · Revisão de corte · Kits de Marca ·    │
│  Fila de Renderização · Relatórios · Configurações                          │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ HTTP + SSE (Bearer token, 127.0.0.1)
┌──────────────▼──────────────── Motor (Python/FastAPI, sidecar) ─────────────┐
│  ingestão (yt-dlp/arquivo) → transcrição (faster-whisper PT-BR, palavra a   │
│  palavra) → análise (RHPT + Claude/heurística → 18 parâmetros → score) →    │
│  candidatos (snap/dedup/diversidade) → reframe (rostos/falantes) →          │
│  legendas ASS → censura → render FFmpeg (1080×1920 H.264/AAC, loudnorm,     │
│  faststart) · fila de jobs com progresso, cancelamento e retomada · SQLite  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**➡️ Guia de instalação e configuração passo a passo: [`docs/CONFIGURACAO.md`](docs/CONFIGURACAO.md)**

Detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · referência da API em
[`docs/API.md`](docs/API.md) · roadmap v2 em [`docs/V2-ROADMAP.md`](docs/V2-ROADMAP.md).

## Instalador Windows

O instalador NSIS (`RealOficial-Setup-<versão>-x64.exe`) é produzido pelo GitHub Actions:

1. **Por push/tag** — o workflow **CI** gera o artefato `RealOficial-Setup-x64` em toda execução do
   job *Instalador Windows*; baixe em *Actions → CI → artifacts*.
2. **Release** — crie uma tag `v1.0.0` e o workflow **Release** anexa o instalador à release.

O instalador embarca o motor (PyInstaller), FFmpeg estático (build GPL do BtbN, executado como
processo separado — ver [`docs/LICENSES.md`](docs/LICENSES.md)) e as fontes Inter/Montserrat.
No primeiro uso, o app baixa o modelo Whisper escolhido (tiny/base/small/medium) e o YuNet (~230 KB).

## Desenvolvimento

Requisitos: Python 3.11+, Node 22+, FFmpeg no PATH (dev), espeak-ng (só para os testes).

```bash
# Motor
cd engine
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q                              # suíte completa (inclui e2e com render real)
python -m app.main --port 8756                   # sobe a API local (token em <data_dir>/api_token)

# App (em outro terminal)
cd app
npm install
npm run dev                                      # renderer em http://localhost:5173
npx electron dist-electron/main.js               # ou: npm run build && npm start
```

No modo dev o Electron spawna o motor usando `engine/.venv` automaticamente
(sobrescreva com `REAL_OFICIAL_PYTHON` ou aponte para um motor já rodando com
`REAL_OFICIAL_ENGINE_URL=http://127.0.0.1:8756`).

## Usando a API local (automações)

O token está em **Configurações → Token da API local** (ou `<data_dir>/api_token`).

```bash
TOKEN="…"; BASE="http://127.0.0.1:8756"

# Fluxo "shorts" (formato da API pública): enviar vídeo → acompanhar → clipes com score
curl -s -X POST "$BASE/api/v1/shorts" -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"video_url": "https://www.youtube.com/watch?v=XXXX"}'
# → {"short_job_id": "…", "source_video_id": "…", "project_id": "…"}

curl -s "$BASE/api/v1/shorts/SHORT_JOB_ID" -H "Authorization: Bearer $TOKEN"
# → {"status": "processing", "progress": 0.62, "clips": [{"id", "score", "title", …}]}

# Renderizar os melhores e baixar
curl -s -X POST "$BASE/api/v1/renders/batch" -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"cut_ids": ["CUT1", "CUT2"]}'
curl -sL "$BASE/api/v1/media/RENDER_ID/file?token=$TOKEN" -o corte.mp4

# Relatório editorial
curl -s "$BASE/api/v1/reports/sources/SOURCE_ID" -H "Authorization: Bearer $TOKEN"
```

Documentação interativa (Swagger) em `http://127.0.0.1:<porta>/docs` com o motor rodando.

## Estrutura do repositório

```
engine/   motor Python (FastAPI, pipeline de IA e render, testes pytest)
app/      aplicação Electron + React (UI PT-BR, testes vitest)
scripts/  fetch_ffmpeg.py, fetch_fonts.py (assets de build)
docs/     ARCHITECTURE.md · API.md · V2-ROADMAP.md · LICENSES.md
.github/  CI (lint+testes+PyInstaller Linux; instalador Windows) e Release
```

## Métricas que o produto se propõe a otimizar

1. **Taxa de aproveitamento** = cortes que você publicaria ÷ cortes gerados;
2. **Tempo economizado** = (duração do vídeo + 8 min × cortes aprovados) − tempo de revisão;
3. **Qualidade do ranking** = correlação de Spearman entre o rank da IA e o seu (`human_rank`).

Os três aparecem no relatório de cada vídeo processado — avalie a ferramenta pelos números dela mesma.

# Real Oficial — Desktop (Windows 10/11)

> **v4.0.0 — Motion Engine.** O Editor virou um motor de **motion design para
> short-form** (nicho inicial: batalhas de rima/freestyle): **Motion Manifest**
> como fonte única da verdade, tipografia cinética com 3 fases
> (entrada/sustain/saída), 14 presets de ênfase + **Text Callout/Typography
> Takeover** (7 presets), track de **efeitos de vídeo** (punch zoom, shake
> procedural com seed, RGB split, darken, blur, flash…), **composições**
> (Fatality/Punchline comandam texto+vídeo+cena num arco editável),
> **B-roll** com biblioteca por projeto e áudio principal intacto, camada
> **Smart Motion** (sugestões semânticas por estilo editorial e densidade,
> nunca aplicadas sem você), galeria animada de presets, workspace
> redimensionável e **paridade preview×render ≤ 1 frame** garantida por
> contrato de testes compartilhado. Determinístico: mesma edição + mesma seed
> = mesmo vídeo; "Nova variação" = nova seed.
>
> v3 continua aí: decisão editorial na tela do corte, canvas 9:16 WYSIWYG,
> editor de palavras, ênfase por palavra, família Palavra Pop e posição livre
> da legenda.

**Real Oficial** transforma vídeos longos (podcasts, entrevistas, lives, aulas — até ~10h) em
**cortes verticais 9:16 prontos para TikTok, Reels e Shorts**, com inteligência artificial:

- 🎯 **Detecção automática de momentos** — análise multimodal: transcrição (semântica via
  Claude/GPT), áudio (**RHPT — Real HotPeak Tracking**: energia, pitch, ritmo de fala, risadas,
  pausas) e visão computacional (rostos/cenas), em **múltiplas passagens** (descoberta ampla →
  refino de bordas → ranking → diversidade) com **funil transparente** do que foi descartado e
  por quê
- 🏆 **Score 0–100 por corte** com detalhamento em **18 parâmetros**, veredito
  (postar/revisar/descartar) e análise editorial por corte; **perfis de quantidade**
  (Conservador · Balanceado · Alto volume · Personalizado) + **reservas**: “Mostrar mais
  oportunidades” sem reanalisar
- ✂️ **Editor de Corte (v2)** — timeline com miniaturas reais, waveform e trim com snap em
  palavra/pausa; dividir/excluir/restaurar trechos (**EDL não destrutiva**: a MESMA edição
  alimenta prévia e render), fades, transições de junção, volume/mudo, correção de palavra por
  clique e **remoção de pausas** (Leve/Normal/Agressivo, preservando pausas dramáticas)
- 📐 **Reenquadramento 16:9 → 9:16** — falante ativo por movimento de boca com histerese e
  anti-tremor; modos **Esquerda/Direita/Centro/Fit/Fundo desfocado/Duas pessoas/Split Screen**,
  overrides manuais por trecho (“18–24s → foco à esquerda”) e **punch-in** opcional
- 💬 **Legendas em PT-BR** queimadas (ASS/libass) com **8 presets reais** (Karaokê Bold, Clean,
  Podcast, Minimal, Palavra Pop, Highlight Box, Bounce, Subtitle Bar), âncora fixa sem pulos,
  regra temporal que impede sobreposição de cartões e excedente virando cartão sequencial
- 🎬 **Motion Engine (v4)** — tipografia cinética por palavra (14 presets com quality gate),
  callouts que tomam a tela, efeitos de vídeo temporais na track FX, composições
  Fatality/Punchline, B-roll por projeto, sugestões Smart Motion por estilo editorial
  (Limpa · Dinâmica · Batalha · Agressiva) e galeria animada — tudo declarativo, editável,
  determinístico e com paridade preview×render testada dos dois lados
- 🎨 **Estúdio de Marca (v2)** — canvas 9:16 com camadas (vídeo do corte com cantos
  arredondados/borda/sombra, imagens/logo, textos com `{titulo}`, formas, vídeo decorativo,
  área das legendas), fundos (cor/degradê/desfoque/imagem/vídeo), animações e templates prontos;
  kits antigos abrem migrados automaticamente
- 🔇 **Censura de palavrões** (beep 1 kHz ou mudo) com wordlist PT-BR extensível
- ⚡ **Bulk Editing + renderização em lote** — fila operacional com miniatura, etapa, ETA e ações
- 📊 **Relatórios internos** — aproveitamento, tempo economizado, edição, custo de IA, tempos por
  estágio e **perfil editorial transparente** aprendido das suas decisões (+ exportação HTML)
- 🔌 **API REST local** com Bearer token — inclusive a fachada `/shorts` no formato da API pública

Processamento de mídia é **100% local** (FFmpeg + faster-whisper + OpenCV). A análise semântica usa
a **API do Claude** (Opus 5 / Sonnet 5 / Haiku 4.5) ou **GPT (OpenAI)** com **fallback local por
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
2. **Release** — dispare o workflow **Release** (Actions → Release → *Run workflow*, informando a
   tag, ex.: `v1.1.0`) ou crie a tag manualmente; a release recebe o instalador NSIS e o **zip
   portátil** (`RealOficial-<versão>-x64.zip` — extrair e executar, sem instalação).

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

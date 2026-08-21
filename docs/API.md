# API REST local — Real Oficial

Base: `http://127.0.0.1:<porta>` (padrão 8756). Autenticação: `Authorization: Bearer <token>`
(token em Configurações ou `<data_dir>/api_token`). Swagger interativo em `/docs`.

Rotas de mídia/HTML aceitam também `?token=` (para `<video>`/iframe/navegador).

## Sistema

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Status do motor (sem auth) |
| POST | `/system/shutdown` | Desligamento gracioso |

## Projetos e fontes

| Método | Rota | Corpo / Observações |
|---|---|---|
| GET/POST | `/api/v1/projects` | `{name, description}` |
| GET/PATCH/DELETE | `/api/v1/projects/{id}` | |
| POST | `/api/v1/projects/{id}/sources` | `{origin: "url"\|"file", url?, file_path?, auto_process=true, options{whisper_model?, max_cuts_per_30min?, force_analyze?}}` → `{source, job_id}` |
| GET | `/api/v1/projects/{id}/sources` | |
| GET/DELETE | `/api/v1/sources/{id}` | |
| GET | `/api/v1/sources/{id}/transcript?include_words=` | frases + (opcional) palavras |
| POST | `/api/v1/sources/{id}/process` | `{options}` → `{job_id}` (reprocessa; estágios prontos são pulados) |

## Cortes

| Método | Rota | Corpo / Observações |
|---|---|---|
| GET | `/api/v1/projects/{id}/cuts?status=&source_video_id=&sort=score\|time` | ordenado por score por padrão |
| GET/DELETE | `/api/v1/cuts/{id}` | inclui `score_breakdown` (18 parâmetros), `crop_plan`, `censor_plan` |
| PATCH | `/api/v1/cuts/{id}` | `{status?, description?, platform_metadata?, start_s?, end_s?, framing?, punch_in?, title?, caption_style?, brand_kit_id?, edits?, edl?, human_rank?, review_started?}` — trim invalida o `crop_plan` (recalculado no próximo render) |
| GET | `/api/v1/captions/presets` | presets de legenda com rótulo PT-BR e `family` (Clássicos / Palavra Pop) |
| GET | `/api/v1/cuts/{id}/caption-cards` | cartões RESOLVIDOS pelo mesmo código do render: `{style, fps, out_duration, cards[{start, end, breaks, words[{idx, ins_id, start_s, end_s, word, emphasis}]}]}` — base do preview WYSIWYG |
| GET | `/api/v1/cuts/{id}/words?pad_s=` | palavras da transcrição na janela do corte (tempos da FONTE) |
| GET | `/api/v1/cuts/{id}/waveform?pps=&pad_s=` | picos de áudio para a timeline |
| POST | `/api/v1/cuts/{id}/pauses-preview` | `{nivel: "leve"\|"normal"\|"agressivo"}` → EDL com as pausas removidas (não aplica) |
| POST | `/api/v1/cuts/bulk` | `{cut_ids[], patch{…}}` — edição em massa |
| POST | `/api/v1/cuts/{id}/preview` | agenda preview 540×960 → `{render_id, job_id}` |

`caption_style`: `{preset: "bold_karaoke"|"clean"|"podcast"|"minimal", …overrides}`.
`edits`: `{word_overrides: {"<idx>": "texto corrigido"}, caption_words: [...]}`.

## Renderização

| Método | Rota | Corpo |
|---|---|---|
| POST | `/api/v1/renders` | `{cut_id, kind="final", brand_kit_id?, overrides{caption_style?, headline?, crf?, video_preset?, censor_enabled?, censor_mode?}}` |
| POST | `/api/v1/renders/batch` | `{cut_ids[], name?, brand_kit_id?, overrides{}}` → lote |
| GET | `/api/v1/renders?status=&batch_id=&cut_id=` | |
| GET | `/api/v1/renders/{id}` · `/api/v1/renders/batches/{id}` | |
| POST | `/api/v1/renders/{id}/cancel` | |
| GET | `/api/v1/media/{render_id}/file?token=` | MP4 final/preview |
| GET | `/api/v1/media/cuts/{cut_id}/preview?token=` | preview mais recente do corte |
| GET | `/api/v1/media/cuts/{cut_id}/filmstrip?t0=&t1=&frames=&token=` | tira de miniaturas da timeline |
| GET | `/api/v1/media/sources/{id}/file?token=` | vídeo original (player do Editor) |

Saída final: 1080×1920 H.264 CRF 19 + AAC 192k, `loudnorm I=-14:TP=-1.5:LRA=11`, `+faststart`.

## Brand Kits

| Método | Rota | Corpo |
|---|---|---|
| GET/POST | `/api/v1/brand-kits` | `{name, logo_position tl\|tr\|bl\|br, logo_opacity, primary_color, secondary_color, font_family, caption_preset, caption_style?, headline_template ("{titulo}"), is_default}` |
| PATCH/DELETE | `/api/v1/brand-kits/{id}` | |
| POST | `/api/v1/brand-kits/{id}/logo` | multipart `file` (png/jpg/webp ≤ 8 MB) |

## Jobs e eventos

| Método | Rota | Observações |
|---|---|---|
| GET | `/api/v1/jobs?status=&type=&source_video_id=&limit=` | |
| GET | `/api/v1/jobs/{id}` | inclui `result` |
| POST | `/api/v1/jobs/{id}/cancel` | cancelamento cooperativo |
| GET | `/api/v1/events` (SSE) | eventos `job.updated`, `render.progress`; replay via `Last-Event-ID`; `?max_events=` p/ depuração |

## Relatórios

| Método | Rota | Conteúdo |
|---|---|---|
| GET | `/api/v1/reports/sources/{id}` | JSON: taxa de aproveitamento, tempo economizado, intervenção por corte, Spearman score×humano, custo Claude, timings |
| GET | `/api/v1/reports/sources/{id}/html?token=` | relatório HTML autossuficiente |
| GET | `/api/v1/reports/projects/{id}` | agregado do projeto |

## Configurações

| Método | Rota | Observações |
|---|---|---|
| GET/PUT | `/api/v1/settings` | chave Anthropic nunca retorna completa (`anthropic_api_key_masked`) |
| POST | `/api/v1/settings/test-anthropic` | `{api_key?}` — testa a chave informada ou a salva |

## Fachada `/shorts` (formato da API pública)

| Método | Rota | Observações |
|---|---|---|
| POST | `/api/v1/shorts` | `{video_url\|file_path, project_id?, options?}` → `{short_job_id, source_video_id, project_id}` |
| GET | `/api/v1/shorts` | lista com `clips_count` |
| GET | `/api/v1/shorts/{short_job_id}` | `{status queued\|processing\|done\|failed, progress, clips: [{id, score, title, hook, start_s, end_s, status, download_url?}]}` |

Fluxo típico de automação:
```text
POST /shorts (URL) → poll GET /shorts/{id} até done → escolher clips por score
→ POST /renders/batch {cut_ids} → poll GET /renders?batch_id= → GET /media/{render_id}/file
```

## Códigos de erro

`401` token ausente/inválido · `404` recurso inexistente · `409` job/render já finalizado ·
`422` validação (ex.: arquivo não encontrado, `end_s ≤ start_s`) · `503` motor inicializando.
Corpo de erro: `{"detail": "mensagem em português"}`.


## Estado editorial e ciclo de render (v3)

`CutOut` separa as duas dimensões — e nunca as mistura:

| Campo | Valores | Significado |
|---|---|---|
| `status` | `pending_review` · `approved` · `rejected` · `reserve` | decisão **editorial** (`draft` ainda é aceito no PATCH como sinônimo de `pending_review`) |
| `render_state` | `not_rendered` · `queued` · `rendering` · `rendered` · `render_failed` | derivado do render **final** mais recente |
| `render_outdated` | bool | `edit_revision` do corte > revisão carimbada no render concluído |
| `edit_revision` | int | incrementa a cada alteração **visual** salva |
| `latest_render_id` | id \| null | render final mais recente (assistir / re-renderizar) |

Renderizar um corte `rejected` devolve **422**.

## Camada de edição do corte (`edits`)

```jsonc
{
  "framing": "auto|left|right|center|blur|fit|two|split",
  "punch_in": "off|leve|dinamico",
  "framing_segments": [{"start_s": 18.0, "end_s": 24.0, "mode": "left"}],
  "word_overrides": {"42": "paletó"},          // substituir (mantém o tempo)
  "word_deleted": [43],                         // some da legenda, não da transcrição
  "word_inserted": [                            // ancorada na vizinha (não desloca ninguém)
    {"id": "w1", "anchor_idx": 44, "placement": "before", "text": "realmente"}
  ],
  "word_emphasis": [                            // uma palavra, várias, ou uma expressão
    {"idx": [44], "effect": "fatality", "intensity": "forte", "color": "#FF2D2D"}
  ]
}
```

Efeitos de ênfase: `pop`, `punch`, `impact`, `fatality`, `color_hit`, `shake`,
`highlight_box`, `soft_lift`, `glow`, `outline_burst`, `flash`, `bounce`.

`caption_style` aceita, além do `preset`, as cores (`text_color`,
`highlight_color`, `outline_color`, `back_color`, `shadow_color`) e a posição
**normalizada** `pos_x` / `pos_y` (0–1) com `max_width_pct` e `align` — é o que
garante que a prévia 540×960 e o render 1080×1920 mostrem a legenda na mesma
posição proporcional.

Precedência de estilo: `palavra (ênfase) › corte › Kit de Marca › preset`.

## Motion Engine (v4)

O corte carrega um **Motion Manifest** (`cut.motion`) — a fonte única da verdade
de todos os efeitos. `null` = sem efeitos.

```jsonc
{
  "version": 1,
  "effects": [{
    "id": "fx_ab12cd34",
    "type": "text_emphasis|text_callout|video_fx|broll|transition|sfx",
    "preset": "punch",                       // id no catálogo do tipo
    "target": {"kind": "words|card|video|clip|media", "idx": [5], "media_id": "…"},
    "start": 3.2, "end": 3.8,                // tempo de SAÍDA (pós-EDL)
    "intensity": "suave|normal|forte",       // ou 0..2 contínuo
    "easing": "ease_out",
    "params": {},                            // overrides por efeito (cor, pos_x/pos_y, modo b-roll…)
    "keyframes": {"scale": [{"t": 0, "v": 100, "ease": "linear"}]},
    "enabled": true,
    "seed": 7,                               // determinismo (shake, jitter, stagger)
    "layer": 0,
    "group": "grp_x", "group_label": "Fatality", // composições
    "origin": "auto", "reason": "…"          // sugestões aplicadas
  }],
  "assets": []
}
```

| Método | Rota | Observações |
|---|---|---|
| PATCH | `/api/v1/cuts/{id}` | `{motion: manifest\|null}` — validado/normalizado; `422` se inválido; conta como edição **visual** (`edit_revision`) |
| GET | `/api/v1/motion/presets` | catálogos completos: `presets` (14 de texto), `video_presets` (10 FX), `callout_presets` (7), `composite_presets` (Fatality/Punchline), `easings` |
| POST | `/api/v1/cuts/{id}/motion/suggest` | `{style, density}` → sugestões da camada semântica (**puro** — nada é gravado; a UI aplica com `origin:"auto"` + `reason`). `422` para estilo/densidade desconhecidos; devolve também `styles` e `densities` |
| GET/POST | `/api/v1/projects/{id}/media` | biblioteca de B-roll do projeto; POST multipart `file` (mp4/mov/webm/png/jpg/webp) — copiado para o data dir e sondado com ffprobe |
| DELETE | `/api/v1/projects/{id}/media/{media_id}` | remove da biblioteca (efeitos que apontam para ela passam a "mídia ausente") |
| GET | `/api/v1/media/broll/{media_id}?token=` | arquivo da mídia (thumb/preview na UI) |

Garantias do motor: presets são **dados** (nunca funções); mesmo manifest +
mesma `seed` ⇒ vídeo bit-idêntico ("Nova variação" = nova seed); paridade
preview×render verificada por contrato compartilhado (`shared/motion-cases.json`,
testado no engine **e** no app); áudio principal **nunca** é tocado pelo B-roll;
composições (ex.: Fatality) expandem para efeitos reais agrupados — tudo
continua editável peça a peça.

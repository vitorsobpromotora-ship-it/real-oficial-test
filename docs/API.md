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
| PATCH | `/api/v1/cuts/{id}` | `{status?, start_s?, end_s?, title?, caption_style?, brand_kit_id?, edits?, human_rank?, review_started?}` — trim invalida o `crop_plan` (recalculado no próximo render) |
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

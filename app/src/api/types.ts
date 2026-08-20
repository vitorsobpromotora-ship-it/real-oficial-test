// Tipos espelhando os schemas do motor (engine/app/schemas).

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  sources_count: number;
  cuts_count: number;
}

export interface Source {
  id: string;
  project_id: string;
  origin: "url" | "file";
  source_url: string | null;
  file_path: string | null;
  audio_path: string | null;
  title: string;
  duration_s: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  size_bytes: number | null;
  status: "importing" | "ready" | "failed";
  error: string | null;
  created_at: string;
}

export interface Job {
  id: string;
  type: string;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  stage: string;
  progress: number;
  message: string;
  error: string | null;
  project_id: string | null;
  source_video_id: string | null;
  cut_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result?: Record<string, unknown> | null;
}

export interface EdlSegment {
  src_start: number;
  src_end: number;
}

/** Edição NÃO destrutiva do Editor de Corte — a mesma EDL alimenta prévia e render. */
export interface Edl {
  version?: number;
  segments: EdlSegment[];
  fade_in_s?: number;
  fade_out_s?: number;
  transition_s?: number;
  audio?: { gain_db?: number; mute?: boolean; fade_in_s?: number; fade_out_s?: number };
}

export interface TranscriptWord {
  idx: number;
  start_s: number;
  end_s: number;
  word: string;
}

export interface Waveform {
  start_s: number;
  end_s: number;
  pps: number;
  peaks: number[];
  source_duration_s: number;
}

export interface Cut {
  id: string;
  source_video_id: string;
  project_id: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  score: number;
  score_breakdown: Record<string, number> | null;
  rhpt_score: number;
  semantic_score: number;
  hook_text: string;
  title: string;
  hashtags: string[] | null;
  reason: string;
  verdict: "postar" | "revisar" | "descartar";
  analysis: {
    gancho?: string;
    desenvolvimento?: string;
    conclusao?: string;
    ponto_forte?: string;
    ponto_fraco?: string;
    sugestao?: string;
    publico?: string;
  } | null;
  status: "pending_review" | "approved" | "rejected" | "reserve";
  rank: number | null;
  origin: "claude" | "gpt" | "heuristic";
  crop_plan: { mode: string; segments: unknown[]; face_hit_rate?: number } | null;
  censor_plan: unknown[] | null;
  caption_style: Record<string, unknown> | null;
  brand_kit_id: string | null;
  edits: Record<string, unknown> | null;
  edl: Edl | null;
  description: string;
  platform_metadata: Record<string, unknown> | null;
  edit_revision: number;
  // ciclo de RENDER (derivado no motor; nunca confundir com o status editorial)
  render_state: "not_rendered" | "queued" | "rendering" | "rendered" | "render_failed";
  render_outdated: boolean;
  latest_render_id: string | null;
  human_rank: number | null;
  review_started_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface KitLayer {
  id: string;
  type: "source" | "image" | "text" | "shape" | "video" | "captions";
  x: number;
  y: number;
  w: number;
  h?: number;
  hidden?: boolean;
  locked?: boolean;
  opacity?: number;
  // source
  radius?: number;
  border_w?: number;
  border_color?: string;
  shadow?: boolean;
  // image/video
  path?: string;
  loop?: boolean;
  // text
  text?: string;
  font?: string;
  size?: number;
  color?: string;
  bg?: string | null;
  align?: "left" | "center" | "right";
  bold?: boolean;
  // shape
  fill?: string;
  // animação/timing
  anim?: string;
  start_s?: number;
  end_s?: number | null;
}

export interface KitLayout {
  version: number;
  canvas: { w: number; h: number };
  background: {
    type: "color" | "gradient" | "image" | "video" | "blur";
    color?: string;
    color2?: string;
    direction?: "vertical" | "horizontal" | "diagonal";
    path?: string;
    blur_sigma?: number;
  };
  layers: KitLayer[];
}

export interface KitTemplate {
  id: string;
  name: string;
  description: string;
  layout: KitLayout;
}

export interface BrandKit {
  id: string;
  name: string;
  logo_path: string | null;
  logo_position: "tl" | "tr" | "bl" | "br";
  logo_opacity: number;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  caption_preset: string;
  caption_style: Record<string, unknown> | null;
  layout: KitLayout | null;
  headline_template: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface Render {
  id: string;
  cut_id: string;
  cut_title: string;
  batch_id: string | null;
  brand_kit_id: string | null;
  kind: "final" | "preview";
  status: "queued" | "running" | "done" | "failed" | "canceled";
  progress: number;
  output_path: string | null;
  job_id: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RenderBatch {
  id: string;
  name: string;
  total: number;
  done: number;
  status: string;
  created_at: string;
  renders: Render[];
}

export type Agent = "claude" | "gpt" | "local";

export interface Settings {
  default_agent: Agent;
  cut_profile: "conservador" | "balanceado" | "alto_volume" | "personalizado";
  cut_score_min: number | string;
  cut_min_gap: number | string;
  max_total_cuts: number;
  claude_model: string;
  claude_fallback_model: string;
  openai_model: string;
  openai_fallback_model: string;
  whisper_model: string;
  output_dir: string;
  use_batches: boolean;
  max_cuts_per_30min: number;
  min_cut_seconds: number;
  max_cut_seconds: number;
  censor_enabled: boolean;
  censor_mode: "beep" | "mute";
  censor_extra_words: string[];
  ui_language: string;
  has_anthropic_api_key: boolean;
  anthropic_api_key_masked: string;
  has_openai_api_key: boolean;
  openai_api_key_masked: string;
  api_token: string;
  data_dir: string;
  version: string;
}

export const PARAM_LABELS: Record<string, string> = {
  hook_strength: "Força do gancho",
  emotional_intensity: "Intensidade emocional",
  humor: "Humor",
  tension: "Tensão",
  completeness: "Completude",
  context_independence: "Indep. de contexto",
  clarity: "Clareza",
  information_value: "Valor informativo",
  storytelling: "Narrativa",
  controversy: "Controvérsia",
  relatability: "Identificação",
  quotability: "Citabilidade",
  novelty: "Novidade",
  energy: "Energia",
  cta_potential: "Potencial de CTA",
  loopability: "Potencial de loop",
  title_potential: "Potencial de título",
  niche_fit: "Aderência ao nicho",
};

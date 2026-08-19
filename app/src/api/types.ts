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
  status: "draft" | "approved" | "rejected";
  rank: number | null;
  origin: "claude" | "gpt" | "heuristic";
  crop_plan: { mode: string; segments: unknown[]; face_hit_rate?: number } | null;
  censor_plan: unknown[] | null;
  caption_style: Record<string, unknown> | null;
  brand_kit_id: string | null;
  edits: Record<string, unknown> | null;
  human_rank: number | null;
  review_started_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
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
  headline_template: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface Render {
  id: string;
  cut_id: string;
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

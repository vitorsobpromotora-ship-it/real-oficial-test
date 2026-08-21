/**
 * Motion Engine — tipos e avaliador determinístico (v4 FASE B).
 *
 * ESPELHO EXATO de engine/app/pipeline/motion.py: o canvas do Editor avalia
 * AS MESMAS curvas/keyframes/ruído que o render final, e o contrato
 * `shared/motion-cases.json` (gerado pelo motor) é verificado dos dois lados
 * — é isso que garante a paridade preview ↔ render (Entrega 60).
 *
 * O manifest fica em cut.motion e viaja inteiro no Draft: entra no undo/redo
 * editorial e no autosave como qualquer edição visual.
 */

// ---------------------------------------------------------------------------
// Modelo
// ---------------------------------------------------------------------------

export type EffectType =
  | "text_emphasis" | "text_callout" | "video_fx" | "broll" | "transition" | "sfx";

export type TargetKind = "words" | "card" | "video" | "clip" | "media";

export type Intensity = "suave" | "normal" | "forte" | number; // número = custom 0..2

export interface Keyframe {
  t: number; // 0..1 — tempo normalizado na duração do efeito
  v: number;
  ease?: string; // curva do SEGMENTO que chega neste keyframe
}

export interface EffectTarget {
  kind: TargetKind;
  idx?: number[]; // palavras da transcrição (words)
  ins_ids?: string[]; // palavras inseridas manualmente
  media_id?: string; // b-roll/mídia (kind=media)
}

export interface EffectInstance {
  id: string;
  type: EffectType;
  preset: string; // nome no catálogo declarativo do motor
  target: EffectTarget;
  start: number; // tempo de SAÍDA (o relógio 00:00 do Editor)
  end: number;
  intensity?: Intensity;
  easing?: string;
  params?: Record<string, unknown>;
  keyframes?: Record<string, Keyframe[]>;
  enabled?: boolean;
  seed?: number;
  layer?: number;
  [k: string]: unknown; // campos futuros preservados (Entrega 81)
}

export interface MotionManifest {
  version: number;
  effects: EffectInstance[];
  assets?: unknown[];
  [k: string]: unknown;
}

export const INTENSITY_K: Record<string, number> = { suave: 0.6, normal: 1.0, forte: 1.5 };

export function intensityK(v: Intensity | undefined): number {
  if (typeof v === "number") return Math.max(0, Math.min(2, v));
  return INTENSITY_K[v ?? "normal"] ?? 1.0;
}

export function novoId(): string {
  let s = "";
  const hex = "0123456789abcdef";
  for (let i = 0; i < 12; i++) s += hex[Math.floor(Math.random() * 16)];
  return s;
}

/** Seed padrão derivada do id — MESMA derivação do motor (seed_de). */
export function seedDe(texto: string): number {
  let h = 0;
  for (let i = 0; i < texto.length; i++) h = (Math.imul(h, 31) + texto.charCodeAt(i)) >>> 0;
  return h || 1;
}

// ---------------------------------------------------------------------------
// Easing — biblioteca fechada (espelho de EASINGS do motor)
// ---------------------------------------------------------------------------

const linear = (u: number) => u;
const easeIn = (u: number) => u * u * u;
const easeOut = (u: number) => 1 - (1 - u) ** 3;
const easeInOut = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2);
const backOut = (u: number) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2;
};
const elasticOut = (u: number) => {
  if (u <= 0) return 0;
  if (u >= 1) return 1;
  const c4 = (2 * Math.PI) / 3;
  return 2 ** (-10 * u) * Math.sin((u * 10 - 0.75) * c4) + 1;
};
const bounceOut = (u: number) => {
  const n1 = 7.5625;
  const d1 = 2.75;
  if (u < 1 / d1) return n1 * u * u;
  if (u < 2 / d1) { u -= 1.5 / d1; return n1 * u * u + 0.75; }
  if (u < 2.5 / d1) { u -= 2.25 / d1; return n1 * u * u + 0.9375; }
  u -= 2.625 / d1;
  return n1 * u * u + 0.984375;
};

export const EASINGS: Record<string, (u: number) => number> = {
  linear,
  ease_in: easeIn,
  ease_out: easeOut,
  ease_in_out: easeInOut,
  back_out: backOut,
  elastic_out: elasticOut,
  bounce_out: bounceOut,
  // apelidos de produto (Entrega 24)
  suave: easeInOut,
  rapido: easeOut,
  impacto: backOut,
  elastico: elasticOut,
};

export const EASING_LABELS_PTBR: Record<string, string> = {
  linear: "Linear",
  suave: "Suave",
  rapido: "Rápido",
  impacto: "Impacto",
  elastico: "Elástico",
  bounce_out: "Quicado",
};

export function ease(nome: string | undefined, u: number): number {
  const uu = u < 0 ? 0 : u > 1 ? 1 : u;
  return (EASINGS[nome ?? "linear"] ?? linear)(uu);
}

// ---------------------------------------------------------------------------
// Keyframes
// ---------------------------------------------------------------------------

export function evalKeyframes(kfs: Keyframe[], u: number): number {
  if (!kfs.length) return 0;
  if (u <= kfs[0].t) return kfs[0].v;
  for (let i = 0; i + 1 < kfs.length; i++) {
    const a = kfs[i];
    const b = kfs[i + 1];
    if (u <= b.t) {
      const span = b.t - a.t;
      const k = span <= 0 ? 0 : (u - a.t) / span;
      return a.v + (b.v - a.v) * ease(b.ease, k);
    }
  }
  return kfs[kfs.length - 1].v;
}

// ---------------------------------------------------------------------------
// Ruído determinístico — shake reproduzível por seed
// ---------------------------------------------------------------------------

export function hash32(x: number): number {
  x >>>= 0;
  x = ((x ^ 61) ^ (x >>> 16)) >>> 0;
  x = (x + ((x << 3) >>> 0)) >>> 0;
  x = (x ^ (x >>> 4)) >>> 0;
  x = Math.imul(x, 0x27d4eb2d) >>> 0;
  x = (x ^ (x >>> 15)) >>> 0;
  return x;
}

export function rng01(seed: number, i: number): number {
  return hash32(((seed >>> 0) ^ hash32((i + 0x9e3779b9) >>> 0)) >>> 0) / 4294967296;
}

export function shakeOffset(
  t: number, seed: number, ampX: number, ampY: number, rotDeg: number, freq: number,
): { dx: number; dy: number; rot: number } {
  const f = [0, 1, 2, 3, 4].map((i) => rng01(seed, i) * 2 * Math.PI);
  const tau = 2 * Math.PI * freq;
  const dx = ampX * (Math.sin(tau * t + f[0]) * 0.62 + Math.sin(tau * 1.7 * t + f[1]) * 0.38);
  const dy = ampY * (Math.sin(tau * 1.3 * t + f[2]) * 0.62 + Math.sin(tau * 2.1 * t + f[3]) * 0.38);
  const rot = rotDeg * Math.sin(tau * 0.9 * t + f[4]);
  return { dx, dy, rot };
}

// ---------------------------------------------------------------------------
// Helpers de manifest
// ---------------------------------------------------------------------------

export function manifestVazio(): MotionManifest {
  return { version: 1, effects: [] };
}

/** Efeitos habilitados ativos no instante t (tempo de SAÍDA). */
export function effectsAt(m: MotionManifest | null, tOut: number): EffectInstance[] {
  if (!m) return [];
  return m.effects.filter((e) => (e.enabled ?? true) && e.start <= tOut && tOut < e.end);
}

/** Progresso normalizado 0..1 de um efeito no instante t. */
export function progresso(e: EffectInstance, tOut: number): number {
  const d = e.end - e.start;
  if (d <= 0) return 0;
  const u = (tOut - e.start) / d;
  return u < 0 ? 0 : u > 1 ? 1 : u;
}

// ---------------------------------------------------------------------------
// Text Motion Core (FASE C) — espelho de motion_text.text_props_at
// ---------------------------------------------------------------------------

export interface TextPhase {
  dur_ms?: number;
  tracks?: Record<string, Keyframe[]>;
  jitter?: { rot?: number; freq?: number };
}

export interface TextPreset {
  id: string;
  label: string;
  categoria: string;
  descricao?: string;
  color?: string; // cor da palavra durante o efeito (params.color vence)
  outline_color?: string;
  phases: { enter?: TextPhase; hold?: TextPhase; exit?: TextPhase };
}

export interface TextProps {
  scale: number; // % (100 = neutro)
  scale_x: number; // eixos separados (Word Stretch) — 100 = usa `scale`
  scale_y: number;
  blur: number;
  rot: number;
  bord: number; // delta sobre o outline do estilo
  alpha: number; // 0..1 (0 = opaco)
}

export const TEXT_NEUTRAL: TextProps = {
  scale: 100, scale_x: 100, scale_y: 100, blur: 0, rot: 0, bord: 0, alpha: 0,
};
const ROT_MAX = 5;

function faseEm(preset: TextPreset, tMs: number, durMs: number):
    { fase: TextPhase; u: number; tFaseMs: number } {
  const enter = preset.phases.enter ?? { dur_ms: 0, tracks: {} };
  const exit = preset.phases.exit ?? { dur_ms: 0, tracks: {} };
  const hold = preset.phases.hold ?? { tracks: {} };
  const eDur = Math.min(enter.dur_ms ?? 0, durMs * 0.5);
  const xDur = Math.min(exit.dur_ms ?? 0, durMs * 0.3);
  if (tMs < eDur) return { fase: enter, u: eDur > 0 ? tMs / eDur : 1, tFaseMs: tMs };
  if (tMs >= durMs - xDur) {
    const rest = tMs - (durMs - xDur);
    return { fase: exit, u: xDur > 0 ? rest / xDur : 1, tFaseMs: rest };
  }
  const hDur = durMs - eDur - xDur;
  const rest = tMs - eDur;
  return { fase: hold, u: hDur > 0 ? rest / hDur : 0, tFaseMs: rest };
}

/** Propriedades da palavra no instante t (tempo de SAÍDA) — MESMA avaliação
 *  que o compilador ASS do motor amostra; provada por shared/motion-cases. */
export function textPropsAt(e: EffectInstance, preset: TextPreset, tOut: number): TextProps {
  const props: TextProps = { ...TEXT_NEUTRAL };
  if (!(e.enabled ?? true) || tOut < e.start || tOut >= e.end) return props;
  const durMs = (e.end - e.start) * 1000;
  const tMs = (tOut - e.start) * 1000;
  const { fase, u, tFaseMs } = faseEm(preset, tMs, durMs);
  const k = intensityK(e.intensity);
  for (const [prop, trilha] of Object.entries(fase.tracks ?? {})) {
    if (!(prop in TEXT_NEUTRAL)) continue; // propriedade futura: ignorada
    const v = evalKeyframes(trilha, u);
    const neutro = TEXT_NEUTRAL[prop as keyof TextProps];
    props[prop as keyof TextProps] = neutro + (v - neutro) * (prop === "alpha" ? 1 : k);
  }
  if (fase.jitter?.rot) {
    const seed = (e.seed ?? 1) | 0;
    const { rot } = shakeOffset(tFaseMs / 1000, seed, 0, 0,
      fase.jitter.rot * k, fase.jitter.freq ?? 9);
    props.rot += rot;
  }
  props.rot = Math.max(-ROT_MAX, Math.min(ROT_MAX, props.rot));
  props.scale = Math.max(10, Math.min(220, props.scale));
  props.scale_x = Math.max(10, Math.min(220, props.scale_x));
  props.scale_y = Math.max(10, Math.min(220, props.scale_y));
  props.blur = Math.max(0, Math.min(24, props.blur));
  props.alpha = Math.max(0, Math.min(1, props.alpha));
  return props;
}

// ---------------------------------------------------------------------------
// Video FX (FASE F) — espelho de motion_video.video_props_at
// ---------------------------------------------------------------------------

export interface VideoPreset {
  id: string;
  label: string;
  categoria: string;
  descricao?: string;
  params?: Record<string, number>;
}

export interface CalloutPreset extends TextPreset {
  layout?: "stack" | "line";
  bg?: "none" | "darken" | "blur" | "black";
  font_scale?: number;
  stagger_ms?: number;
  last_word_scale?: number;
  last_word_color?: string;
}

export interface VideoProps {
  zoom: number; // 1 = neutro
  dx: number; // px na referência 1080×1920
  dy: number;
  rot: number;
  darken: number; // 0..1
  blur: number; // sigma na referência 1080
  gray: number; // 0..1
  flash: number; // 0..1
  rgb: number; // px de separação na referência 1080
}

export const VIDEO_NEUTRAL: VideoProps = {
  zoom: 1, dx: 0, dy: 0, rot: 0, darken: 0, blur: 0, gray: 0, flash: 0, rgb: 0,
};

export const SHAKE_FREQS = [23, 31, 29, 37] as const;

const smooth = (u: number) => {
  const c = u < 0 ? 0 : u > 1 ? 1 : u;
  return c * c * (3 - 2 * c);
};
const clip01 = (u: number) => (u < 0 ? 0 : u > 1 ? 1 : u);

function paramDe(e: EffectInstance, preset: VideoPreset, nome: string, def = 0): number {
  const ep = (e.params ?? {}) as Record<string, unknown>;
  if (typeof ep[nome] === "number") return ep[nome] as number;
  return preset.params?.[nome] ?? def;
}

/** Estado do vídeo no instante t — MESMAS fórmulas que o filtergraph avalia. */
export function videoPropsAt(e: EffectInstance, preset: VideoPreset, t: number): VideoProps {
  const props: VideoProps = { ...VIDEO_NEUTRAL };
  const t0 = e.start;
  const t1 = e.end;
  const dur = Math.max(0.05, t1 - t0);
  if (!(e.enabled ?? true) || t < t0 || t >= t1) return props;
  const k = intensityK(e.intensity);
  const ts = t - t0;
  const pid = preset.id;
  if (pid === "punch_zoom") {
    const am = paramDe(e, preset, "amount") * k;
    const attack = Math.min(0.18, dur * 0.35);
    const release = dur - attack;
    props.zoom = 1 + am * (clip01(ts / attack) - smooth(clip01((ts - attack) / release)));
  } else if (pid === "zoom_out") {
    const am = paramDe(e, preset, "amount") * k;
    props.zoom = 1 + am * (1 - smooth(clip01(ts / dur)));
  } else if (pid === "shake" || pid === "impact_shake") {
    const amp = paramDe(e, preset, "amp") * k;
    const f = [0, 1, 2, 3].map((i) => rng01((e.seed ?? 1) | 0, i) * 2 * Math.PI);
    const env = pid === "impact_shake"
      ? Math.exp(-paramDe(e, preset, "decay", 6) * ts / dur)
      : Math.max(0, 1 - ts / dur);
    const [f1, f2, f3, f4] = SHAKE_FREQS;
    props.dx = amp * env * (0.6 * Math.sin(2 * Math.PI * f1 * ts + f[0])
      + 0.4 * Math.sin(2 * Math.PI * f2 * ts + f[1]));
    props.dy = amp * env * (0.6 * Math.sin(2 * Math.PI * f3 * ts + f[2])
      + 0.4 * Math.sin(2 * Math.PI * f4 * ts + f[3]));
  } else if (pid === "rgb_split") {
    props.rgb = paramDe(e, preset, "px") * k;
  } else if (pid === "darken") {
    props.darken = Math.min(0.85, paramDe(e, preset, "amount") * k);
  } else if (pid === "flash") {
    const decay = paramDe(e, preset, "decay_s", 0.15);
    props.flash = Math.min(1, paramDe(e, preset, "amount") * k)
      * Math.max(0, 1 - ts / decay);
  } else if (pid === "blur_pulse") {
    props.blur = paramDe(e, preset, "sigma") * k;
  } else if (pid === "vignette_pulse") {
    props.darken = 0.12; // aproximação do preview; o render usa vignette real
  } else if (pid === "grayscale_hit") {
    props.gray = 1;
  }
  return props;
}

/** FX de vídeo ativos e combinados no instante t (para o canvas). */
export function videoFxAt(
  m: MotionManifest | null, presets: VideoPreset[], t: number,
): VideoProps {
  const out: VideoProps = { ...VIDEO_NEUTRAL };
  if (!m) return out;
  for (const e of m.effects) {
    if (e.type !== "video_fx" || e.enabled === false) continue;
    const preset = presets.find((p) => p.id === e.preset);
    if (!preset) continue;
    const v = videoPropsAt(e, preset, t);
    out.zoom *= v.zoom;
    out.dx += v.dx;
    out.dy += v.dy;
    out.darken = Math.min(0.9, out.darken + v.darken);
    out.blur += v.blur;
    out.gray = Math.max(out.gray, v.gray);
    out.flash = Math.min(1, out.flash + v.flash);
    out.rgb = Math.max(out.rgb, v.rgb);
  }
  return out;
}

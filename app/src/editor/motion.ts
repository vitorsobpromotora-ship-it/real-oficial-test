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

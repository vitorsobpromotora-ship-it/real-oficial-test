/**
 * Modelo de estado do Editor (Ponto 36): um único Draft versionado pelo
 * undo/redo, com responsabilidades separadas — corte (EDL), áudio,
 * enquadramento (global + por trecho), punch-in, legenda (estilo do corte),
 * palavras e kit. Alterar uma parte nunca reconstrói as outras.
 *
 * Relógio (Pontos 11–12): o Editor trabalha em TEMPO DE SAÍDA (00:00 = início
 * do corte). Os tempos de FONTE continuam existindo por baixo (src_start/
 * src_end) e aparecem só como informação de origem.
 */
import type { Cut, Edl, EdlSegment } from "../api/types";

export interface FramingSegment {
  start_s: number; // tempos da FONTE (contrato do motor: edits.framing_segments)
  end_s: number;
  mode: string; // left | center | right
}

export interface InsertedWord {
  id: string;
  anchor_idx: number; // palavra da transcrição à qual está ancorada
  placement: "before" | "after";
  text: string;
}

export interface Draft {
  segments: EdlSegment[];
  fade_in_s: number;
  fade_out_s: number;
  transition_s: number;
  audio: { gain_db: number; mute: boolean; fade_in_s: number; fade_out_s: number };
  framing: string; // modo global: auto|left|right|center|blur|fit|two|split
  punch_in: string; // off|leve|dinamico
  framing_segments: FramingSegment[];
  word_overrides: Record<string, string>; // substituir (mesma janela temporal)
  word_deleted: number[]; // excluir da legenda (a transcrição não muda)
  word_inserted: InsertedWord[]; // inserir antes/depois, ancorado (Ponto 14)
  caption_style: Record<string, unknown> | null; // overrides do corte (preset, cores, posição)
  brand_kit_id: string | null;
}

export const PAD_S = 15; // margem de contexto disponível antes/depois na timeline

export function draftFromCut(cut: Cut): Draft {
  const e: Edl | null = cut.edl;
  return {
    segments: e?.segments?.length
      ? e.segments.map((s) => ({ ...s }))
      : [{ src_start: cut.start_s, src_end: cut.end_s }],
    fade_in_s: e?.fade_in_s ?? 0,
    fade_out_s: e?.fade_out_s ?? 0,
    transition_s: e?.transition_s ?? 0,
    audio: {
      gain_db: e?.audio?.gain_db ?? 0,
      mute: e?.audio?.mute ?? false,
      fade_in_s: e?.audio?.fade_in_s ?? 0,
      fade_out_s: e?.audio?.fade_out_s ?? 0,
    },
    framing: ((cut.edits?.framing as string) ?? "auto") || "auto",
    punch_in: ((cut.edits?.punch_in as string) ?? "off") || "off",
    framing_segments: ((cut.edits?.framing_segments as FramingSegment[]) ?? [])
      .map((s) => ({ ...s })),
    word_overrides: { ...((cut.edits?.word_overrides as Record<string, string>) ?? {}) },
    word_deleted: [...((cut.edits?.word_deleted as number[]) ?? [])],
    word_inserted: ((cut.edits?.word_inserted as InsertedWord[]) ?? []).map((w) => ({ ...w })),
    caption_style: cut.caption_style ? { ...cut.caption_style } : null,
    brand_kit_id: cut.brand_kit_id,
  };
}

/** Corpo do PATCH que persiste o Draft inteiro num único salvamento. */
export function patchFromDraft(d: Draft, title: string, baseEdits: Record<string, unknown> | null) {
  const edits = { ...(baseEdits ?? {}) } as Record<string, unknown>;
  if (Object.keys(d.word_overrides).length) edits.word_overrides = d.word_overrides;
  else delete edits.word_overrides;
  if (d.word_deleted.length) edits.word_deleted = d.word_deleted;
  else delete edits.word_deleted;
  const insOk = d.word_inserted.filter((w) => w.text.trim());
  if (insOk.length) edits.word_inserted = insOk;
  else delete edits.word_inserted;
  const frOk = d.framing_segments.filter((s) => s.end_s > s.start_s);
  if (frOk.length) edits.framing_segments = frOk;
  else delete edits.framing_segments;
  delete edits.framing; // geridos pelos campos dedicados do PATCH
  delete edits.punch_in;
  return {
    edl: {
      segments: d.segments,
      fade_in_s: d.fade_in_s,
      fade_out_s: d.fade_out_s,
      transition_s: d.transition_s,
      audio: d.audio,
    },
    title,
    framing: d.framing,
    punch_in: d.punch_in,
    caption_style: d.caption_style,
    brand_kit_id: d.brand_kit_id,
    edits: Object.keys(edits).length ? edits : null,
  };
}

export const outDur = (segs: EdlSegment[]) =>
  segs.reduce((acc, s) => acc + (s.src_end - s.src_start), 0);

export const envelope = (segs: EdlSegment[]): [number, number] => [
  segs[0]?.src_start ?? 0,
  segs[segs.length - 1]?.src_end ?? 0,
];

/** Fonte → saída. Instantes em trechos removidos "colam" no início do próximo. */
export function srcToOut(segs: EdlSegment[], t: number): number {
  let acc = 0;
  for (const s of segs) {
    if (t < s.src_start) return acc;
    if (t < s.src_end) return acc + (t - s.src_start);
    acc += s.src_end - s.src_start;
  }
  return acc;
}

/** Saída → fonte (para posicionar o vídeo e a régua). */
export function outToSrc(segs: EdlSegment[], t: number): number {
  let acc = 0;
  for (const s of segs) {
    const d = s.src_end - s.src_start;
    if (t < acc + d) return s.src_start + (t - acc);
    acc += d;
  }
  return segs[segs.length - 1]?.src_end ?? 0;
}

/** Timecode relativo m:ss.d — o relógio principal do Editor começa em 0:00. */
export function fmtT(t: number): string {
  const m = Math.floor(Math.max(0, t) / 60);
  const s = Math.max(0, t) - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

/** Timecode de ORIGEM h:mm:ss.mmm (só informativo — tooltip/inspector). */
export function fmtSrc(t: number): string {
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  const mm = `${m}`.padStart(2, "0");
  const ss = s.toFixed(3).padStart(6, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

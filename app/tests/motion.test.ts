/**
 * v4 FASE B — paridade do Motion Engine (Entrega 60).
 *
 * `shared/motion-cases.json` foi GERADO pelo motor (Python). Este teste prova
 * que o avaliador TS chega EXATAMENTE aos mesmos valores — easings, keyframes
 * e ruído determinístico — então o que o canvas mostra é o que o render fará.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  EASINGS, TEXT_NEUTRAL, VIDEO_NEUTRAL, ease, effectsAt, evalKeyframes, hash32,
  intensityK, manifestVazio, progresso, rng01, seedDe, shakeOffset, textPropsAt,
  videoFxAt, videoPropsAt,
  type EffectInstance, type Keyframe, type TextPreset, type VideoPreset,
} from "../src/editor/motion";

const CASES = JSON.parse(
  readFileSync(join(__dirname, "..", "..", "shared", "motion-cases.json"), "utf8"),
) as {
  us: number[];
  easings: Record<string, number[]>;
  keyframes: { track: Keyframe[]; us: number[]; vals: number[] }[];
  rng: { seed: number; i: number; hash32: number; v: number }[];
  shake: { amp_x: number; amp_y: number; rot_deg: number; freq: number;
    cases: { seed: number; t: number; dx: number; dy: number; rot: number }[] };
};

describe("paridade preview ↔ render (contrato gerado pelo motor)", () => {
  it("todas as curvas de easing batem com o motor", () => {
    for (const [nome, esperados] of Object.entries(CASES.easings)) {
      CASES.us.forEach((u, i) => {
        expect(ease(nome, u), `${nome}@${u}`).toBeCloseTo(esperados[i], 12);
      });
    }
    expect(Object.keys(EASINGS).sort()).toEqual(Object.keys(CASES.easings).sort());
  });

  it("keyframes (trilha de 3 fases, clamps, trilha vazia) batem com o motor", () => {
    for (const caso of CASES.keyframes) {
      caso.us.forEach((u, i) => {
        expect(evalKeyframes(caso.track, u)).toBeCloseTo(caso.vals[i], 12);
      });
    }
  });

  it("hash32/rng01 são bit-idênticos ao motor (mesma seed → mesmo número)", () => {
    for (const r of CASES.rng) {
      expect(hash32(((r.seed >>> 0) ^ hash32((r.i + 0x9e3779b9) >>> 0)) >>> 0))
        .toBe(r.hash32);
      expect(rng01(r.seed, r.i)).toBe(r.v);
    }
  });

  it("shake procedural bate com o motor em todos os instantes amostrados", () => {
    const s = CASES.shake;
    for (const c of s.cases) {
      const got = shakeOffset(c.t, c.seed, s.amp_x, s.amp_y, s.rot_deg, s.freq);
      expect(got.dx).toBeCloseTo(c.dx, 12);
      expect(got.dy).toBeCloseTo(c.dy, 12);
      expect(got.rot).toBeCloseTo(c.rot, 12);
    }
  });
});

describe("helpers do manifest", () => {
  const fx = (o: Partial<EffectInstance>): EffectInstance => ({
    id: "e1", type: "video_fx", preset: "punch_zoom", target: { kind: "video" },
    start: 1, end: 2, ...o,
  });

  it("effectsAt respeita janela [start,end) e enabled=false", () => {
    const m = { ...manifestVazio(), effects: [
      fx({ id: "a" }), fx({ id: "b", start: 1.5, end: 3, enabled: false }),
    ] };
    expect(effectsAt(m, 1.6).map((e) => e.id)).toEqual(["a"]);
    expect(effectsAt(m, 2)).toEqual([]); // end exclusivo
    expect(effectsAt(null, 1)).toEqual([]);
  });

  it("progresso normaliza e clampa; intensidade nomeada vira fator", () => {
    const e = fx({ start: 2, end: 4 });
    expect(progresso(e, 1)).toBe(0);
    expect(progresso(e, 3)).toBe(0.5);
    expect(progresso(e, 9)).toBe(1);
    expect(intensityK("suave")).toBe(0.6);
    expect(intensityK("forte")).toBe(1.5);
    expect(intensityK(undefined)).toBe(1);
    expect(intensityK(1.8)).toBe(1.8);
    expect(intensityK(9)).toBe(2); // custom clampado em 0..2
  });

  it("seedDe é estável (mesma derivação do motor)", () => {
    expect(seedDe("fx1")).toBe(seedDe("fx1"));
    expect(seedDe("fx1")).not.toBe(seedDe("fx2"));
    expect(seedDe("")).toBe(1); // nunca 0
  });
});

describe("Text Motion Core — paridade das 3 fases (FASE C)", () => {
  interface TPCase {
    preset: string;
    effect: EffectInstance;
    t: number;
    props: Record<string, number>;
  }
  const TP = (CASES as unknown as {
    text_props: { presets: Record<string, TextPreset>; cases: TPCase[] };
  }).text_props;

  it("textPropsAt bate com o motor em ENTER, HOLD, EXIT e fora da janela", () => {
    for (const c of TP.cases) {
      const got = textPropsAt(c.effect, TP.presets[c.preset], c.t);
      for (const [prop, v] of Object.entries(c.props)) {
        expect(got[prop as keyof typeof got], `${c.preset}@${c.t}s ${prop}`)
          .toBeCloseTo(v, 12);
      }
    }
  });

  it("fora da janela e desabilitado → neutro absoluto", () => {
    const preset = TP.presets.punch;
    const e = TP.cases[0].effect;
    expect(textPropsAt(e, preset, 0)).toEqual(TEXT_NEUTRAL);
    expect(textPropsAt({ ...e, enabled: false }, preset, 2.3)).toEqual(TEXT_NEUTRAL);
  });
});

describe("Video FX — paridade das fórmulas do filtergraph (FASE F)", () => {
  interface VPCase {
    preset: string;
    effect: EffectInstance;
    t: number;
    props: Record<string, number>;
  }
  const VP = (CASES as unknown as {
    video_props: { presets: Record<string, VideoPreset>; cases: VPCase[] };
  }).video_props;

  it("videoPropsAt bate com o motor em todos os presets e instantes", () => {
    for (const c of VP.cases) {
      const got = videoPropsAt(c.effect, VP.presets[c.preset], c.t);
      for (const [prop, v] of Object.entries(c.props)) {
        expect(got[prop as keyof typeof got], `${c.preset}@${c.t}s ${prop}`)
          .toBeCloseTo(v, 12);
      }
    }
  });

  it("videoFxAt combina efeitos simultâneos (zoom multiplica, darken soma)", () => {
    const presets = Object.values(VP.presets);
    const m = {
      version: 1,
      effects: [
        { id: "a", type: "video_fx", preset: "darken", target: { kind: "video" },
          start: 1, end: 2, intensity: "normal", enabled: true, seed: 1 },
        { id: "b", type: "video_fx", preset: "grayscale_hit", target: { kind: "video" },
          start: 1.5, end: 2.5, intensity: "normal", enabled: true, seed: 1 },
      ] as EffectInstance[],
    };
    const dentro = videoFxAt(m, presets, 1.7);
    expect(dentro.darken).toBeCloseTo(0.22, 6);
    expect(dentro.gray).toBe(1);
    const fora = videoFxAt(m, presets, 3);
    expect(fora).toEqual(VIDEO_NEUTRAL);
    expect(videoFxAt(null, presets, 1.7)).toEqual(VIDEO_NEUTRAL);
  });
});

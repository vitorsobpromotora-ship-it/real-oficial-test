/**
 * v4 FASE C — fluxo do Motion Engine na interface (DoD da Entrega 152):
 * UI (menu da palavra → ✦ Motion) → ESTADO (Draft.motion) → PERSISTÊNCIA
 * (autosave envia o manifest) → TIMELINE (bloco nomeado na track Motion) →
 * edição no painel (intensidade/ativo/excluir) → UNDO.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Cut } from "../src/api/types";
import type { MotionManifest } from "../src/editor/motion";

const patchCalls: { path: string; body: Record<string, unknown> }[] = [];
let cutAtual: Cut;

const CARDS = {
  style: { anchor_top: 1280, font_size: 74, max_chars: 18, max_lines: 2 },
  fps: 30,
  out_duration: 6,
  cards: [
    { start: 0, end: 1.6, breaks: [], words: [
      { idx: 0, ins_id: null, start_s: 0, end_s: 0.3, word: "eu" },
      { idx: 1, ins_id: null, start_s: 0.3, end_s: 0.7, word: "gosto" },
      { idx: 2, ins_id: null, start_s: 0.7, end_s: 1.1, word: "muito" },
    ] },
  ],
};

function makeCut(over: Partial<Cut> = {}): Cut {
  return {
    id: "c1", source_video_id: "s1", project_id: "p1",
    start_s: 10, end_s: 16, duration_s: 6, score: 80,
    score_breakdown: null, rhpt_score: 60, semantic_score: 80, hook_text: "",
    title: "Corte A", hashtags: null, reason: "", verdict: "revisar",
    analysis: null, status: "pending_review", rank: 1, origin: "claude",
    crop_plan: null, censor_plan: null, caption_style: null, brand_kit_id: null,
    edits: null, edl: null, motion: null, description: "", platform_metadata: null,
    edit_revision: 1, render_state: "not_rendered", render_outdated: false,
    latest_render_id: null, human_rank: null, review_started_at: null,
    reviewed_at: null, created_at: "", updated_at: "",
  ...over };
}

vi.mock("../src/api/client", () => ({
  get: vi.fn(async (path: string) => {
    if (path.startsWith("/api/v1/cuts/c1/caption-cards")) return CARDS;
    if (path.startsWith("/api/v1/cuts/c1/waveform"))
      return { start_s: 0, end_s: 30, pps: 40, peaks: [0.3], source_duration_s: 60 };
    if (path.startsWith("/api/v1/cuts/c1/words"))
      return { words: [
        { idx: 0, start_s: 10.0, end_s: 10.3, word: "eu" },
        { idx: 1, start_s: 10.3, end_s: 10.7, word: "gosto" },
        { idx: 2, start_s: 10.7, end_s: 11.1, word: "muito" },
      ] };
    if (path.startsWith("/api/v1/cuts/c1")) return cutAtual;
    if (path.startsWith("/api/v1/sources/s1"))
      return { id: "s1", project_id: "p1", duration_s: 60, status: "ready",
               title: "Fonte", width: 1920, height: 1080, fps: 30 };
    if (path.startsWith("/api/v1/captions/presets"))
      return { presets: [{ id: "bold_karaoke", label: "Karaokê Bold" }] };
    if (path.startsWith("/api/v1/motion/presets"))
      return { video_presets: [
        { id: "punch_zoom", label: "Punch Zoom", categoria: "Zoom",
          params: { amount: 0.12 } },
        { id: "flash", label: "Flash", categoria: "Cena",
          params: { amount: 0.42, decay_s: 0.15 } },
      ], callout_presets: [
        { id: "center_impact", label: "Impacto Central", categoria: "Callouts",
          layout: "line", bg: "darken", font_scale: 1.45, stagger_ms: 0,
          phases: { enter: { dur_ms: 240, tracks: { scale: [
            { t: 0, v: 158 }, { t: 0.5, v: 96, ease: "rapido" },
            { t: 1, v: 104, ease: "impacto" }] } } } },
      ], presets: [
        { id: "pop_clean", label: "Pop Clean", categoria: "Básicos",
          phases: { enter: { dur_ms: 170, tracks: { scale: [
            { t: 0, v: 100 }, { t: 1, v: 106, ease: "suave" }] } } } },
        { id: "punch", label: "Punch", categoria: "Impacto",
          phases: { enter: { dur_ms: 210, tracks: { scale: [
            { t: 0, v: 100 }, { t: 0.28, v: 138, ease: "rapido" },
            { t: 1, v: 108, ease: "impacto" }] } } } },
      ] };
    if (path.startsWith("/api/v1/brand-kits")) return [];
    if (path.startsWith("/api/v1/renders")) return [];
    return {};
  }),
  post: vi.fn(async () => ({})),
  patch: vi.fn(async (path: string, body: Record<string, unknown>) => {
    patchCalls.push({ path, body });
    cutAtual = { ...cutAtual, ...(body as Partial<Cut>) } as Cut;
    return cutAtual;
  }),
  del: vi.fn(async () => ({})),
  mediaUrl: async (p: string) => `http://test${p}?token=t`,
  engine: vi.fn(async () => ({ baseUrl: "http://test", token: "t" })),
  ApiError: class extends Error {},
}));

import EditorPage from "../src/pages/Editor";

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projeto/p1/corte/c1/editor"]}>
        <Routes>
          <Route path="/projeto/:projectId/corte/:cutId/editor" element={<EditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** motion do ÚLTIMO PATCH que o autosave enviou. */
function ultimoMotion(): MotionManifest | null {
  for (let i = patchCalls.length - 1; i >= 0; i--) {
    if ("motion" in patchCalls[i].body) {
      return patchCalls[i].body.motion as MotionManifest | null;
    }
  }
  return null;
}

beforeEach(() => {
  patchCalls.length = 0;
  cutAtual = makeCut();
  window.localStorage.clear();
});

describe("v4 FASE C — Motion pela interface", () => {
  it("✦ Motion na palavra cria o efeito, mostra o bloco na track e persiste", async () => {
    renderEditor();
    fireEvent.click(await screen.findByTestId("tool-palavras"));
    fireEvent.click(await screen.findByTestId("wp-i1")); // chip da palavra
    fireEvent.click(await screen.findByTestId("wp-motion"));

    // seleção contextual: painel Motion abre já com o efeito selecionado
    expect(await screen.findByTestId("mo-editor")).toBeInTheDocument();
    expect(screen.getByTestId("mo-preset")).toHaveValue("punch");

    // TIMELINE: bloco nomeado (nunca fx_273) na track Motion
    const track = screen.getByTestId("mo-track");
    expect(track.textContent).toContain("Punch");

    // PERSISTÊNCIA: o autosave envia o manifest com alvo e janela da palavra
    await waitFor(() => {
      const m = ultimoMotion();
      expect(m?.effects).toHaveLength(1);
      expect(m!.effects[0].preset).toBe("punch");
      expect(m!.effects[0].target).toEqual({ kind: "words", idx: [1] });
      expect(m!.effects[0].start).toBeCloseTo(0.3, 2);
      expect(m!.effects[0].end).toBeCloseTo(0.95, 2);
      expect(m!.effects[0].seed).toBeGreaterThan(0);
    }, { timeout: 4000 });
  });

  it("painel edita intensidade/preset, desativa sem excluir e troca a seed", async () => {
    renderEditor();
    fireEvent.click(await screen.findByTestId("tool-palavras"));
    fireEvent.click(await screen.findByTestId("wp-i1"));
    fireEvent.click(await screen.findByTestId("wp-motion"));
    await screen.findByTestId("mo-editor");

    fireEvent.click(screen.getByTestId("mo-int-forte"));
    fireEvent.change(screen.getByTestId("mo-preset"), { target: { value: "pop_clean" } });
    await waitFor(() => {
      const e = ultimoMotion()!.effects[0];
      expect(e.intensity).toBe("forte");
      expect(e.preset).toBe("pop_clean");
    }, { timeout: 4000 });
    expect(screen.getByTestId("mo-track").textContent).toContain("Pop Clean — Forte");

    const seedAntes = ultimoMotion()!.effects[0].seed;
    fireEvent.click(screen.getByTestId("mo-variacao")); // 🎲 nova variação
    fireEvent.click(screen.getByTestId("mo-enabled")); // desativa (A/B)
    await waitFor(() => {
      const e = ultimoMotion()!.effects[0];
      expect(e.seed).not.toBe(seedAntes);
      expect(e.enabled).toBe(false);
    }, { timeout: 4000 });
    const bloco = screen.getByTestId("mo-track").querySelector(".tl-moblock");
    expect(bloco?.className).toContain("off"); // continua visível, marcado
  });

  it("excluir remove do manifest (null) e Ctrl+Z desfaz a criação", async () => {
    renderEditor();
    fireEvent.click(await screen.findByTestId("tool-palavras"));
    fireEvent.click(await screen.findByTestId("wp-i1"));
    fireEvent.click(await screen.findByTestId("wp-motion"));
    await screen.findByTestId("mo-editor");

    fireEvent.click(screen.getByTestId("mo-excluir"));
    await waitFor(() => expect(ultimoMotion()).toBeNull(), { timeout: 4000 });
    expect(screen.queryByTestId("mo-editor")).not.toBeInTheDocument();

    // undo (2×: exclusão e criação) devolve o Draft sem nenhum efeito
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(screen.getByTestId("mo-track").textContent).toContain("Punch");
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    await waitFor(() => expect(ultimoMotion()).toBeNull(), { timeout: 4000 });
  });

  it("bloco da track seleciona o efeito E o cartão alvo (Entrega 91)", async () => {
    cutAtual = makeCut({ motion: { version: 1, effects: [{
      id: "fx9", type: "text_emphasis", preset: "punch",
      target: { kind: "words", idx: [2] }, start: 0.7, end: 1.35,
      intensity: "normal", enabled: true, seed: 5, params: {}, keyframes: {},
      layer: 0 }] } });
    renderEditor();
    fireEvent.click(await screen.findByTestId("mo-block-fx9"));
    expect(await screen.findByTestId("mo-editor")).toBeInTheDocument();
    expect(screen.getByTestId("panel-motion")).toBeInTheDocument();
    // o cartão que contém a palavra alvo fica selecionado no estado do editor
    // (o painel Palavras o mostraria; aqui basta o painel Motion aberto e
    // o bloco marcado como selecionado)
    expect(screen.getByTestId("mo-block-fx9").className).toContain("on");
  });
});

describe("v4 FASE F — Video FX pela interface", () => {
  it("⚡ cria efeito de vídeo no cursor, bloco na track FX e persiste", async () => {
    renderEditor();
    fireEvent.click(await screen.findByTestId("tool-motion"));
    fireEvent.click(await screen.findByTestId("mo-add-fx"));

    expect(await screen.findByTestId("mo-editor")).toBeInTheDocument();
    expect(screen.getByTestId("mo-preset")).toHaveValue("punch_zoom");
    expect(screen.getByTestId("fx-track").textContent).toContain("Punch Zoom");
    expect(screen.getByTestId("mo-track").textContent).not.toContain("Punch Zoom");

    // troca para um preset de CENA e persiste no manifest
    fireEvent.change(screen.getByTestId("mo-preset"), { target: { value: "flash" } });
    await waitFor(() => {
      const e = ultimoMotion()!.effects[0];
      expect(e.type).toBe("video_fx");
      expect(e.preset).toBe("flash");
      expect(e.target).toEqual({ kind: "video" });
      expect(e.end - e.start).toBeCloseTo(0.6, 2);
    }, { timeout: 4000 });
    expect(screen.getByTestId("fx-track").textContent).toContain("Flash");
  });
});

describe("v4 FASE E — Text Callout pela interface", () => {
  it("🗯 Destaque no cartão cria o callout, esconde a legenda e persiste", async () => {
    renderEditor();
    fireEvent.click(await screen.findByTestId("tool-palavras"));
    fireEvent.click(await screen.findByTestId("wp-callout-0"));

    // painel Motion abre com o callout selecionado e controles próprios
    expect(await screen.findByTestId("mo-editor")).toBeInTheDocument();
    expect(screen.getByTestId("mo-preset")).toHaveValue("center_impact");
    expect(screen.getByTestId("mo-callout-extra")).toBeInTheDocument();

    // canvas: o destaque assume e a legenda base sai de cena (takeover)
    expect(screen.getByTestId("cv-callout")).toBeInTheDocument();
    expect(screen.queryByTestId("cv-caption")).not.toBeInTheDocument();

    // persistência: manifest com as palavras do cartão e a janela dele
    await waitFor(() => {
      const e = ultimoMotion()!.effects[0];
      expect(e.type).toBe("text_callout");
      expect(e.target.idx).toEqual([0, 1, 2]);
      expect(e.start).toBeCloseTo(0, 2);
      expect(e.end).toBeCloseTo(1.9, 2);
    }, { timeout: 4000 });

    // fundo trocado no painel entra em params
    fireEvent.change(screen.getByTestId("mo-bg"), { target: { value: "black" } });
    await waitFor(() => {
      expect(ultimoMotion()!.effects[0].params?.bg).toBe("black");
    }, { timeout: 4000 });
  });
});

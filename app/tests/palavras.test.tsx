/**
 * Etapa F na interface (Pontos 13, 27, 28): as quatro operações do editor de
 * palavras, a track de Legendas como objeto temporal e o sincronismo
 * cartão ↔ playhead ↔ painel.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Cut } from "../src/api/types";

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
      { idx: 3, ins_id: null, start_s: 1.1, end_s: 1.5, word: "disso" },
    ] },
    { start: 2.0, end: 3.4, breaks: [], words: [
      { idx: 4, ins_id: null, start_s: 2.0, end_s: 2.5, word: "sério" },
      { idx: 5, ins_id: null, start_s: 2.5, end_s: 3.3, word: "mesmo" },
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
    edits: null, edl: null, description: "", platform_metadata: null,
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
        { idx: 3, start_s: 11.1, end_s: 11.5, word: "disso" },
        { idx: 4, start_s: 12.0, end_s: 12.5, word: "sério" },
        { idx: 5, start_s: 12.5, end_s: 13.3, word: "mesmo" },
      ] };
    if (path.startsWith("/api/v1/cuts/c1")) return cutAtual;
    if (path.startsWith("/api/v1/sources/s1"))
      return { id: "s1", project_id: "p1", duration_s: 60, status: "ready",
               title: "Fonte", width: 1920, height: 1080, fps: 30 };
    if (path.startsWith("/api/v1/captions/presets"))
      return { presets: [{ id: "bold_karaoke", label: "Karaokê Bold" }] };
    if (path.startsWith("/api/v1/brand-kits")) return [];
    if (path.startsWith("/api/v1/renders")) return [];
    if (path === "/health") return { version: "test" };
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

/** Edits do ÚLTIMO PATCH (o autosave envia o Draft inteiro; null = sem edits). */
function ultimosEdits(): Record<string, unknown> {
  for (let i = patchCalls.length - 1; i >= 0; i--) {
    if ("edits" in patchCalls[i].body) {
      return (patchCalls[i].body.edits as Record<string, unknown> | null) ?? {};
    }
  }
  return {};
}

beforeEach(() => {
  patchCalls.length = 0;
  cutAtual = makeCut();
  vi.useRealTimers();
});

describe("Ponto 13 — quatro operações no editor de palavras", () => {
  it("substituir grava word_overrides sem tocar a transcrição", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));

    await waitFor(() => expect(screen.getByTestId("wp-i1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("wp-i1")); // palavra "gosto"
    fireEvent.click(screen.getByText("✏ Substituir"));
    const input = document.querySelector(".ed-word-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "gostei" } });
    fireEvent.blur(input);

    await waitFor(() => expect(ultimosEdits().word_overrides).toEqual({ "1": "gostei" }),
      { timeout: 4000 });
  });

  it("excluir move a palavra para a lista de restauráveis e volta ao clicar", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));
    await waitFor(() => expect(screen.getByTestId("wp-i3")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("wp-i3")); // "disso"
    fireEvent.click(screen.getByText("Excluir"));
    await waitFor(() => expect(ultimosEdits().word_deleted).toEqual([3]), { timeout: 4000 });
    expect(screen.queryByTestId("wp-i3")).toBeNull();

    // restaurar
    fireEvent.click(screen.getByTestId("wp-del-3"));
    await waitFor(() => expect(ultimosEdits().word_deleted).toBeUndefined(), { timeout: 6000 });
  }, 20000);

  it("inserir antes e depois ancora na palavra vizinha", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));
    await waitFor(() => expect(screen.getByTestId("wp-i2")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("wp-i2")); // "muito"
    fireEvent.click(screen.getByText("+ antes"));
    let input = document.querySelector(".ed-word-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "realmente" } });
    fireEvent.blur(input);

    await waitFor(() => {
      const ins = ultimosEdits().word_inserted as { anchor_idx: number;
        placement: string; text: string }[];
      expect(ins).toHaveLength(1);
      expect(ins[0]).toMatchObject({ anchor_idx: 2, placement: "before", text: "realmente" });
    }, { timeout: 4000 });

    fireEvent.click(screen.getByTestId("wp-i0")); // "eu"
    fireEvent.click(screen.getByText("+ depois"));
    input = document.querySelector(".ed-word-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sim" } });
    fireEvent.blur(input);

    await waitFor(() => {
      const ins = ultimosEdits().word_inserted as { anchor_idx: number;
        placement: string; text: string }[];
      expect(ins).toHaveLength(2);
      expect(ins[1]).toMatchObject({ anchor_idx: 0, placement: "after", text: "sim" });
    }, { timeout: 4000 });
  });
});

describe("Pontos 27–28 — legendas na timeline e sincronismo", () => {
  it("cartões viram blocos clicáveis que selecionam o cartão no editor de palavras", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("cap-card-0")).toBeInTheDocument());
    expect(screen.getByTestId("cap-card-1").textContent).toBe("sério mesmo");

    fireEvent.click(screen.getByTestId("cap-card-1"));
    // clicar no cartão abre a ferramenta Palavras já naquele cartão
    await waitFor(() => expect(screen.getByTestId("panel-palavras")).toBeInTheDocument());
    expect(screen.getByTestId("wp-card-1").className).toContain("sel");
  });

  it("palavras inseridas aparecem no painel com marcação própria", async () => {
    cutAtual = makeCut({
      edits: { word_inserted: [{ id: "w1", anchor_idx: 2, placement: "before",
                                text: "realmente" }] },
    });
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));
    await waitFor(() => expect(screen.getByTestId("wp-sw1")).toBeInTheDocument());
    expect(screen.getByTestId("wp-sw1").textContent).toBe("realmente");
    expect(screen.getByTestId("wp-sw1").className).toContain("ins");
  });
});

describe("Pontos 21–25 — posição livre, safe area e cores da legenda", () => {
  it("ajustar X/Y grava coordenadas NORMALIZADAS no estilo do corte", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-legenda")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-legenda"));

    await waitFor(() => expect(screen.getByTestId("cap-y")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("cap-y"), { target: { value: "0.25" } });
    fireEvent.change(screen.getByTestId("cap-x"), { target: { value: "0.3" } });

    await waitFor(() => {
      const cs = patchCalls[patchCalls.length - 1].body.caption_style as
        Record<string, number>;
      expect(cs.pos_y).toBeCloseTo(0.25, 3);
      expect(cs.pos_x).toBeCloseTo(0.3, 3);
    }, { timeout: 4000 });
  });

  it("cores do corte são gravadas e o botão restaura o padrão", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-legenda")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-legenda"));

    await waitFor(() => expect(screen.getByTestId("cor-highlight_color")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("cor-highlight_color"),
      { target: { value: "#00ff00" } });
    await waitFor(() => {
      const cs = patchCalls[patchCalls.length - 1].body.caption_style as
        Record<string, string>;
      expect(cs.highlight_color).toBe("#00FF00");
    }, { timeout: 4000 });

    fireEvent.click(screen.getByTestId("cor-reset"));
    await waitFor(() => {
      const cs = (patchCalls[patchCalls.length - 1].body.caption_style ?? {}) as
        Record<string, string>;
      expect(cs.highlight_color).toBeUndefined();
    }, { timeout: 4000 });
  }, 20000);

  it("safe area aparece no canvas quando ligada", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-legenda")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-legenda"));
    await waitFor(() => expect(screen.getByTestId("cap-safe")).toBeInTheDocument());
    expect(screen.queryByTestId("cv-safe")).toBeNull();
    fireEvent.click(screen.getByTestId("cap-safe"));
    await waitFor(() => expect(screen.getByTestId("cv-safe")).toBeInTheDocument());
  });
});

describe("Pontos 15–17 — ênfase por palavra", () => {
  it("aplica Fatality na palavra, ajusta intensidade e depois troca por Soft Lift", async () => {
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));
    await waitFor(() => expect(screen.getByTestId("wp-i2")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("wp-i2")); // "muito"
    fireEvent.click(screen.getByTestId("wp-enfase"));
    fireEvent.click(screen.getByTestId("enf-fatality"));

    await waitFor(() => {
      const e = ultimosEdits().word_emphasis as Record<string, unknown>[];
      expect(e).toHaveLength(1);
      expect(e[0]).toMatchObject({ effect: "fatality", intensity: "normal", idx: [2] });
    }, { timeout: 4000 });

    fireEvent.click(screen.getByTestId("enf-int-forte"));
    await waitFor(() => {
      const e = ultimosEdits().word_emphasis as Record<string, unknown>[];
      expect(e[0]).toMatchObject({ effect: "fatality", intensity: "forte" });
    }, { timeout: 4000 });

    // Ponto 45: trocar o efeito muda SÓ o override daquela palavra
    fireEvent.click(screen.getByTestId("enf-soft_lift"));
    await waitFor(() => {
      const e = ultimosEdits().word_emphasis as Record<string, unknown>[];
      expect(e).toHaveLength(1);
      expect(e[0]).toMatchObject({ effect: "soft_lift", idx: [2], intensity: "forte" });
    }, { timeout: 4000 });
  }, 25000);

  it("palavra com ênfase fica marcada e o efeito pode ser removido", async () => {
    cutAtual = makeCut({
      edits: { word_emphasis: [{ idx: [1], effect: "impact", intensity: "normal" }] },
    });
    renderEditor();
    await waitFor(() => expect(screen.getByTestId("tool-palavras")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("tool-palavras"));
    await waitFor(() => expect(screen.getByTestId("wp-i1")).toBeInTheDocument());
    expect(screen.getByTestId("wp-i1").className).toContain("enf");

    fireEvent.click(screen.getByTestId("wp-i1"));
    fireEvent.click(screen.getByTestId("wp-enfase"));
    fireEvent.click(screen.getByTestId("enf-remover"));
    await waitFor(() => {
      expect(ultimosEdits().word_emphasis).toBeUndefined();
    }, { timeout: 4000 });
  }, 20000);
});

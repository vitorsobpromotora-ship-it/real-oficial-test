/**
 * Pontos 40/41 — tela de análise editorial e navegação Corte ↔ Editor.
 *
 * Regras testadas: rotas explícitas (nunca history.back), Voltar/Salvar e
 * fechar retornam SEMPRE à análise do MESMO corte, aprovar mantém a tela
 * aberta com ✓ Aprovado + Renderizar, rejeitar oferece Desfazer, e as abas
 * Para revisar / Aprovados / Rejeitados separam os estados editoriais.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Cut } from "../src/api/types";

const patchCalls: { path: string; body: Record<string, unknown> }[] = [];
let cutAtual: Cut;

function makeCut(over: Partial<Cut> = {}): Cut {
  return {
    id: "c1", source_video_id: "s1", project_id: "p1",
    start_s: 380, end_s: 425, duration_s: 45, score: 82.5,
    score_breakdown: { hook_strength: 9 }, rhpt_score: 70, semantic_score: 88,
    hook_text: "Você não vai acreditar", title: "Corte A", hashtags: null,
    reason: "", verdict: "postar",
    analysis: { gancho: "Pergunta forte", desenvolvimento: "História", conclusao: "Payoff" },
    status: "pending_review", rank: 1, origin: "claude",
    crop_plan: null, censor_plan: null, caption_style: null, brand_kit_id: null,
    edits: null, edl: null, description: "", platform_metadata: null,
    edit_revision: 1, render_state: "not_rendered", render_outdated: false,
    latest_render_id: null, human_rank: null, review_started_at: null,
    reviewed_at: null, created_at: "", updated_at: "",
  ...over };
}

vi.mock("../src/api/client", () => ({
  get: vi.fn(async (path: string) => {
    if (path.startsWith("/api/v1/cuts/c1/waveform"))
      return { start_s: 360, end_s: 440, pps: 40, peaks: [0.2, 0.4], source_duration_s: 600 };
    if (path.startsWith("/api/v1/cuts/c1/words")) return { words: [] };
    if (path.startsWith("/api/v1/cuts/c1")) return cutAtual;
    if (path.startsWith("/api/v1/sources/s1"))
      return { id: "s1", project_id: "p1", duration_s: 600, status: "ready",
               title: "Fonte", width: 1920, height: 1080, fps: 30 };
    if (path.startsWith("/api/v1/renders")) return [];
    if (path.startsWith("/api/v1/projects/p1/cuts?status=reserve")) return [];
    if (path.startsWith("/api/v1/projects/p1/cuts"))
      return [cutAtual, makeCut({ id: "c2", title: "Corte B", status: "approved",
                                  render_state: "rendered", latest_render_id: "r9" })];
    if (path.startsWith("/api/v1/projects/p1/sources")) return [];
    if (path.startsWith("/api/v1/projects/p1")) return { id: "p1", name: "Meu projeto" };
    if (path.startsWith("/api/v1/brand-kits")) return [];
    if (path.startsWith("/api/v1/jobs")) return [];
    if (path.startsWith("/api/v1/settings")) return {};
    if (path === "/health") return { version: "test" };
    return {};
  }),
  post: vi.fn(async () => ({})),
  patch: vi.fn(async (path: string, body: Record<string, unknown>) => {
    patchCalls.push({ path, body });
    if (body.status || body.title !== undefined || body.description !== undefined) {
      cutAtual = { ...cutAtual, ...(body as Partial<Cut>) } as Cut;
    }
    return cutAtual;
  }),
  del: vi.fn(async () => ({})),
  mediaUrl: async (p: string) => `http://test${p}?token=t`,
  engine: vi.fn(async () => ({ baseUrl: "http://test", token: "t" })),
  ApiError: class extends Error {},
}));

import App from "../src/App";

function LocationProbe() {
  return <div data-testid="loc">{useLocation().pathname}</div>;
}

function renderApp(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  patchCalls.length = 0;
  cutAtual = makeCut();
});

describe("Ponto 41 — navegação Corte ↔ Editor", () => {
  it("Corte A → Editor → Voltar → o MESMO Corte A", async () => {
    renderApp("/projeto/p1/corte/c1");
    await waitFor(() =>
      expect(screen.getByTestId("cut-title")).toHaveValue("Corte A"));

    fireEvent.click(screen.getByTestId("btn-editor"));
    expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1/editor");

    await waitFor(() => expect(screen.getByTestId("btn-back")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("btn-back"));
    await waitFor(() =>
      expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1"));
    await waitFor(() =>
      expect(screen.getByTestId("cut-title")).toHaveValue("Corte A"));
  });

  it("Salvar e fechar também retorna à análise do mesmo corte", async () => {
    renderApp("/projeto/p1/corte/c1/editor");
    await waitFor(() => expect(screen.getByTestId("btn-save-close")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("btn-save-close"));
    await waitFor(() =>
      expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1"));
  });

  it("deep link direto do Editor funciona (reload)", async () => {
    renderApp("/projeto/p1/corte/c1/editor");
    await waitFor(() => expect(screen.getByTestId("btn-back")).toBeInTheDocument());
    expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1/editor");
  });

  it("rota legada /editor/:cutId redireciona para a rota canônica", async () => {
    renderApp("/editor/c1");
    await waitFor(() =>
      expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1/editor"));
  });
});

describe("Ponto 40 — tela de análise editorial", () => {
  it("aprovar mantém a tela aberta com ✓ Aprovado e botão Renderizar", async () => {
    renderApp("/projeto/p1/corte/c1");
    await waitFor(() => expect(screen.getByTestId("btn-approve")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("btn-approve"));

    await waitFor(() => {
      const chamada = patchCalls.find((c) => c.body.status === "approved");
      expect(chamada).toBeTruthy();
    });
    await waitFor(() => expect(screen.getByTestId("btn-render")).toBeInTheDocument());
    expect(screen.getByTestId("loc").textContent).toBe("/projeto/p1/corte/c1");
    expect(screen.getAllByText("✓ Aprovado").length).toBeGreaterThan(0);
  });

  it("rejeitar mostra feedback com Desfazer, que restaura para revisão", async () => {
    renderApp("/projeto/p1/corte/c1");
    await waitFor(() => expect(screen.getByTestId("btn-reject")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("btn-reject"));

    await waitFor(() =>
      expect(screen.getByTestId("toast-rejected")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Desfazer"));
    await waitFor(() => {
      const restaurou = patchCalls.find((c) => c.body.status === "pending_review");
      expect(restaurou).toBeTruthy();
    });
  });

  it("título e descrição persistem via PATCH (publishing metadata)", async () => {
    renderApp("/projeto/p1/corte/c1");
    await waitFor(() => expect(screen.getByTestId("cut-title")).toHaveValue("Corte A"));

    fireEvent.change(screen.getByTestId("cut-title"), { target: { value: "Novo título" } });
    fireEvent.blur(screen.getByTestId("cut-title"));
    fireEvent.change(screen.getByTestId("cut-description"),
      { target: { value: "Descrição para publicar" } });
    fireEvent.blur(screen.getByTestId("cut-description"));

    await waitFor(() => {
      expect(patchCalls.some((c) => c.body.title === "Novo título")).toBe(true);
      expect(patchCalls.some((c) => c.body.description === "Descrição para publicar")).toBe(true);
    });
  });

  it("não há controles técnicos na tela de análise (só o Editor altera o vídeo)", async () => {
    renderApp("/projeto/p1/corte/c1");
    await waitFor(() => expect(screen.getByTestId("cut-title")).toHaveValue("Corte A"));
    for (const proibido of ["Enquadramento", "Punch-in", "Estilo de legenda",
                            "Kit de marca", "Início", "Fim", "Remover pausas"]) {
      expect(screen.queryByText(proibido)).toBeNull();
    }
  });
});

describe("Ponto 2 — abas por estado editorial", () => {
  it("Para revisar é a aba padrão e só contém pendentes; Aprovados tem o resto", async () => {
    renderApp("/projeto/p1");
    await waitFor(() => expect(screen.getByText("Corte A")).toBeInTheDocument());
    expect(screen.getByTestId("tab-pending_review").textContent).toContain("Para revisar (1)");
    expect(screen.queryByText("Corte B")).toBeNull();

    fireEvent.click(screen.getByTestId("tab-approved"));
    await waitFor(() => expect(screen.getByText("Corte B")).toBeInTheDocument());
    expect(screen.queryByText("Corte A")).toBeNull();

    fireEvent.click(screen.getByTestId("tab-rejected"));
    await waitFor(() =>
      expect(screen.getByText(/Nenhum corte em Rejeitados/)).toBeInTheDocument());
  });
});

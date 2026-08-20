import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CutCard, { fmtDur, fmtRange, scoreClass } from "../src/components/CutCard";
import ScoreBreakdown from "../src/components/ScoreBreakdown";
import type { Cut } from "../src/api/types";

const cut: Cut = {
  id: "c1", source_video_id: "s1", project_id: "p1",
  start_s: 65, end_s: 100, duration_s: 35, score: 82.5,
  score_breakdown: { hook_strength: 9, humor: 3.5 },
  rhpt_score: 70, semantic_score: 88, hook_text: "Eu nunca contei isso",
  title: "O segredo revelado", hashtags: ["#x"], reason: "",
  verdict: "postar", analysis: null, status: "pending_review",
  rank: 1, origin: "claude", crop_plan: { mode: "crop", segments: [] },
  censor_plan: null, caption_style: null, brand_kit_id: null, edits: null, edl: null,
  description: "", platform_metadata: null, edit_revision: 1,
  render_state: "not_rendered", render_outdated: false, latest_render_id: null,
  human_rank: null, review_started_at: null, reviewed_at: null,
  created_at: "", updated_at: "",
};

describe("helpers de formatação", () => {
  it("fmtDur e fmtRange", () => {
    expect(fmtDur(35)).toBe("35s");
    expect(fmtDur(95)).toBe("1m35s");
    expect(fmtRange(65, 100)).toBe("01:05 → 01:40");
    expect(fmtRange(3700, 3765)).toBe("1:01:40 → 1:02:45");
  });
  it("scoreClass por faixa", () => {
    expect(scoreClass(80)).toBe("hi");
    expect(scoreClass(60)).toBe("mid");
    expect(scoreClass(40)).toBe("lo");
  });
});

describe("CutCard", () => {
  it("mostra título, score, rank e chips em PT-BR", () => {
    render(<CutCard cut={cut} selected={false} onToggle={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByText("O segredo revelado")).toBeInTheDocument();
    expect(screen.getByText("83")).toBeInTheDocument();
    expect(screen.getByText("para revisar")).toBeInTheDocument();
    expect(screen.getByText("IA Claude")).toBeInTheDocument();
    expect(screen.getByText("reenquadrado")).toBeInTheDocument();
  });
});

describe("ScoreBreakdown", () => {
  it("renderiza rótulos PT-BR ordenados por nota", () => {
    render(<ScoreBreakdown breakdown={{ hook_strength: 9, humor: 3.5 }} />);
    expect(screen.getByText("Força do gancho")).toBeInTheDocument();
    expect(screen.getByText("Humor")).toBeInTheDocument();
    expect(screen.getByText("9.0")).toBeInTheDocument();
  });
});

import type { Cut } from "../api/types";
import Thumb from "./Thumb";

export function fmtDur(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

export function fmtRange(a: number, b: number): string {
  const f = (t: number) => {
    const h = Math.floor(t / 3600);
    const m = Math.floor((t % 3600) / 60);
    const s = Math.floor(t % 60);
    return (h > 0 ? `${h}:` : "") + `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };
  return `${f(a)} → ${f(b)}`;
}

export function scoreClass(score: number): string {
  return score >= 75 ? "hi" : score >= 55 ? "mid" : "lo";
}

interface Props {
  cut: Cut;
  selected: boolean;
  onToggle(): void;
  onOpen(): void;
}

export default function CutCard({ cut, selected, onToggle, onOpen }: Props) {
  return (
    <div className="card cutcard click" onClick={onOpen} data-testid="cut-card">
      <div className={`score ${scoreClass(cut.score)}`}>{cut.score.toFixed(0)}</div>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <input
          type="checkbox"
          checked={selected}
          onClick={(e) => e.stopPropagation()}
          onChange={onToggle}
          style={{ width: 16, marginTop: 3 }}
        />
        <Thumb cutId={cut.id} className="card-thumb" />
        <div style={{ minWidth: 0 }}>
          <h3 style={{ paddingRight: 48 }}>{cut.title || "(sem título)"}</h3>
          <div className="sub">
            #{cut.rank ?? "—"} · {fmtDur(cut.duration_s)} · {fmtRange(cut.start_s, cut.end_s)}
          </div>
        </div>
      </div>
      {cut.hook_text ? (
        <div className="sub" style={{ marginTop: 8, fontStyle: "italic" }}>
          “{cut.hook_text.slice(0, 110)}{cut.hook_text.length > 110 ? "…" : ""}”
        </div>
      ) : null}
      <div className="chips">
        <span className={`chip verdict-${cut.verdict}`}>
          {cut.verdict === "postar" ? "✓ postar" : cut.verdict === "descartar" ? "✗ descartar" : "− revisar"}
        </span>
        <span className={`chip ${cut.status}`}>
          {cut.status === "approved" ? "aprovado" : cut.status === "rejected" ? "rejeitado" : "para revisar"}
        </span>
        {cut.status === "approved" && cut.render_state === "rendered" ? (
          <span className="chip approved">{cut.render_outdated ? "render desatualizado" : "renderizado"}</span>
        ) : null}
        {cut.render_state === "rendering" || cut.render_state === "queued" ? (
          <span className="chip">renderizando…</span>
        ) : null}
        <span className={`chip ${cut.origin !== "heuristic" ? "claude" : ""}`}>
          {cut.origin === "claude" ? "IA Claude" : cut.origin === "gpt" ? "IA GPT" : "análise local"}
        </span>
        {cut.crop_plan ? (
          <span className="chip">
            {cut.crop_plan.mode === "blur_pad" ? "fundo desfocado" : "reenquadrado"}
          </span>
        ) : null}
        {cut.edl ? <span className="chip warnc">✂ editado</span> : null}
      </div>
    </div>
  );
}

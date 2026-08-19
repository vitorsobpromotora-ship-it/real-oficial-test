import { PARAM_LABELS } from "../api/types";

export default function ScoreBreakdown({ breakdown }: { breakdown: Record<string, number> | null }) {
  if (!breakdown) return <div className="sub">Sem detalhamento de score.</div>;
  const entries = Object.entries(PARAM_LABELS)
    .filter(([key]) => key in breakdown)
    .map(([key, label]) => ({ key, label, value: breakdown[key] }))
    .sort((a, b) => b.value - a.value);
  return (
    <div className="params">
      {entries.map(({ key, label, value }) => (
        <div className="param" key={key}>
          <div className="row">
            <span>{label}</span>
            <span>{value.toFixed(1)}</span>
          </div>
          <div className="bar"><i style={{ width: `${Math.min(100, value * 10)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

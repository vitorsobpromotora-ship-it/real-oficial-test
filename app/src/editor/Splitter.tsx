/**
 * Splitter (v4 FASE A) — divisor arrastável entre painéis do Editor.
 *
 * Hitbox generosa (8px), cursor certo por orientação, duplo clique restaura o
 * padrão da dimensão e um botão embutido colapsa/expande o painel vizinho.
 * O Splitter só reporta DELTAS de arraste — quem clampa e persiste é o
 * useWorkspace (as regras de limite ficam num lugar só).
 */
import { useRef } from "react";

interface Props {
  dir: "v" | "h"; // v = barra vertical (redimensiona largura) · h = horizontal (altura)
  /** delta em px desde o início do arraste (dx p/ "v", dy p/ "h") */
  onDrag(delta: number, fase: "start" | "move" | "end"): void;
  onReset(): void; // duplo clique
  collapsed: boolean;
  onToggleCollapse(): void;
  testid: string;
  label: string; // acessibilidade/tooltip
}

export default function Splitter(p: Props) {
  const origem = useRef<{ x: number; y: number } | null>(null);

  function down(e: React.PointerEvent) {
    if (p.collapsed) return; // colapsado não arrasta — só o botão expande
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    origem.current = { x: e.clientX, y: e.clientY };
    p.onDrag(0, "start");
  }
  function move(e: React.PointerEvent) {
    const o = origem.current;
    if (!o) return;
    p.onDrag(p.dir === "v" ? e.clientX - o.x : e.clientY - o.y, "move");
  }
  function up(e: React.PointerEvent) {
    const o = origem.current;
    if (!o) return;
    origem.current = null;
    p.onDrag(p.dir === "v" ? e.clientX - o.x : e.clientY - o.y, "end");
  }

  return (
    <div
      className={`split split-${p.dir}${p.collapsed ? " collapsed" : ""}`}
      role="separator"
      aria-label={p.label}
      aria-orientation={p.dir === "v" ? "vertical" : "horizontal"}
      title={`${p.label} — arraste para redimensionar · duplo clique restaura`}
      data-testid={p.testid}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onDoubleClick={p.onReset}
    >
      <button
        className="split-toggle"
        data-testid={`${p.testid}-toggle`}
        title={p.collapsed ? "Mostrar painel" : "Ocultar painel"}
        onPointerDown={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          p.onToggleCollapse();
        }}
      >
        {p.dir === "v" ? (p.collapsed ? "⟨" : "⟩") : p.collapsed ? "⌃" : "⌄"}
      </button>
    </div>
  );
}

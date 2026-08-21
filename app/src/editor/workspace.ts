/**
 * Workspace do Editor (v4 FASE A) — dimensões dos painéis são PREFERÊNCIA DA
 * INSTALAÇÃO, não estado do projeto: persistem em localStorage, nunca entram
 * no Draft (e portanto nunca passam pelo undo/redo editorial nem pelo PATCH).
 *
 * Invariantes:
 *  - o player 9:16 nunca distorce — o canvas encaixa por "contain" no espaço
 *    que sobrar (a área central é sempre o resto do grid);
 *  - Inspector: 260–550px (padrão 340);
 *  - Timeline: 140px até 55% da janela (padrão 280);
 *  - duplo clique num splitter restaura o padrão daquela dimensão.
 */
import { useCallback, useEffect, useState } from "react";

export type CanvasZoom = "fit" | 50 | 75 | 100;

export interface Workspace {
  inspector_w: number;
  timeline_h: number;
  inspector_collapsed: boolean;
  timeline_collapsed: boolean;
  canvas_zoom: CanvasZoom;
  tracks: "normal" | "compacta"; // altura das tracks da timeline
  preset: string; // último preset aplicado (informativo; "personalizado" ao arrastar)
}

export const WS_KEY = "ro.workspace.v1";
export const INSP_MIN = 260;
export const INSP_MAX = 550;
export const TL_MIN = 140;
export const TL_MAX_PCT = 0.55;

export const INSP_PADRAO = 340;
export const TL_PADRAO = 280;

export function tlMax(alturaJanela: number): number {
  return Math.max(TL_MIN, Math.round(alturaJanela * TL_MAX_PCT));
}

export function wsPadrao(): Workspace {
  return {
    inspector_w: INSP_PADRAO,
    timeline_h: TL_PADRAO,
    inspector_collapsed: false,
    timeline_collapsed: false,
    canvas_zoom: "fit",
    tracks: "normal",
    preset: "padrao",
  };
}

/** Presets de área de trabalho (Entrega 14) — arranjos, não estilos. */
export const WORKSPACE_PRESETS: Record<string, { label: string; ws: Partial<Workspace> }> = {
  padrao: { label: "Padrão", ws: {} }, // = wsPadrao()
  video: {
    label: "Foco no vídeo",
    ws: { inspector_w: 280, timeline_h: TL_MIN, tracks: "compacta" },
  },
  timeline: {
    label: "Foco na timeline",
    ws: { inspector_w: 300, timeline_h: 430, tracks: "normal" },
  },
  legendas: {
    label: "Legendas",
    ws: { inspector_w: 480, timeline_h: 240, tracks: "compacta" },
  },
  motion: {
    label: "Motion",
    ws: { inspector_w: 420, timeline_h: 360, tracks: "normal" },
  },
};

const ZOOMS: CanvasZoom[] = ["fit", 50, 75, 100];

export function clampWorkspace(ws: Workspace, alturaJanela: number): Workspace {
  return {
    ...ws,
    inspector_w: Math.round(Math.min(INSP_MAX, Math.max(INSP_MIN, ws.inspector_w))),
    timeline_h: Math.round(Math.min(tlMax(alturaJanela), Math.max(TL_MIN, ws.timeline_h))),
    canvas_zoom: ZOOMS.includes(ws.canvas_zoom) ? ws.canvas_zoom : "fit",
    tracks: ws.tracks === "compacta" ? "compacta" : "normal",
  };
}

function alturaJanela(): number {
  return typeof window !== "undefined" && window.innerHeight ? window.innerHeight : 800;
}

export function carregarWorkspace(): Workspace {
  const base = wsPadrao();
  try {
    const raw = window.localStorage.getItem(WS_KEY);
    if (!raw) return base;
    const dado = JSON.parse(raw) as Partial<Workspace>;
    return clampWorkspace({ ...base, ...dado }, alturaJanela());
  } catch {
    return base; // JSON corrompido/localStorage indisponível → padrão, sem quebrar
  }
}

function guardarWorkspace(ws: Workspace) {
  try {
    window.localStorage.setItem(WS_KEY, JSON.stringify(ws));
  } catch {
    /* modo privado/sem quota — o Editor continua funcionando sem persistir */
  }
}

export interface WorkspaceApi {
  ws: Workspace;
  /** Ajuste com clamp; marca o arranjo como "personalizado". */
  mudar(patch: Partial<Workspace>): void;
  aplicarPreset(id: string): void;
  resetInspector(): void;
  resetTimeline(): void;
}

export function useWorkspace(): WorkspaceApi {
  const [ws, setWs] = useState<Workspace>(carregarWorkspace);

  useEffect(() => {
    guardarWorkspace(ws);
  }, [ws]);

  // janela menor que antes → o clamp de 55% precisa reagir
  useEffect(() => {
    const h = () => setWs((w) => clampWorkspace(w, alturaJanela()));
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);

  const mudar = useCallback((patch: Partial<Workspace>) => {
    setWs((w) => {
      const muda_tamanho = patch.inspector_w != null || patch.timeline_h != null
        || patch.tracks != null;
      return clampWorkspace(
        { ...w, ...patch, preset: muda_tamanho ? "personalizado" : (patch.preset ?? w.preset) },
        alturaJanela(),
      );
    });
  }, []);

  const aplicarPreset = useCallback((id: string) => {
    const p = WORKSPACE_PRESETS[id];
    if (!p) return;
    setWs(clampWorkspace({ ...wsPadrao(), ...p.ws, preset: id }, alturaJanela()));
  }, []);

  const resetInspector = useCallback(
    () => setWs((w) => ({ ...w, inspector_w: INSP_PADRAO, inspector_collapsed: false })),
    [],
  );
  const resetTimeline = useCallback(
    () => setWs((w) => ({ ...w, timeline_h: TL_PADRAO, timeline_collapsed: false })),
    [],
  );

  return { ws, mudar, aplicarPreset, resetInspector, resetTimeline };
}

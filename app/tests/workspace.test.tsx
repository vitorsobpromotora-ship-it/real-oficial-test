/**
 * v4 FASE A — workspace redimensionável (Entregas 8–16, 117).
 *
 * O arranjo dos painéis é preferência da INSTALAÇÃO: persiste em localStorage,
 * respeita limites (Inspector 260–550, timeline 140–55% da janela), tem
 * presets nomeados e nunca entra no undo/redo editorial.
 */
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Splitter from "../src/editor/Splitter";
import {
  INSP_MAX, INSP_MIN, INSP_PADRAO, TL_MIN, TL_PADRAO, WORKSPACE_PRESETS, WS_KEY,
  carregarWorkspace, clampWorkspace, tlMax, useWorkspace, wsPadrao,
} from "../src/editor/workspace";

beforeEach(() => window.localStorage.clear());

describe("useWorkspace — limites e persistência (Entrega 117)", () => {
  it("nasce com o padrão: inspector 340, timeline 280, zoom fit, nada colapsado", () => {
    const { result } = renderHook(() => useWorkspace());
    expect(result.current.ws.inspector_w).toBe(INSP_PADRAO);
    expect(result.current.ws.timeline_h).toBe(TL_PADRAO);
    expect(result.current.ws.canvas_zoom).toBe("fit");
    expect(result.current.ws.inspector_collapsed).toBe(false);
    expect(result.current.ws.timeline_collapsed).toBe(false);
    expect(result.current.ws.tracks).toBe("normal");
  });

  it("clampa: inspector nunca sai de 260–550 e a timeline de 140–55% da janela", () => {
    const { result } = renderHook(() => useWorkspace());
    act(() => result.current.mudar({ inspector_w: 9999, timeline_h: 9999 }));
    expect(result.current.ws.inspector_w).toBe(INSP_MAX);
    expect(result.current.ws.timeline_h).toBe(tlMax(window.innerHeight));
    act(() => result.current.mudar({ inspector_w: 10, timeline_h: 10 }));
    expect(result.current.ws.inspector_w).toBe(INSP_MIN);
    expect(result.current.ws.timeline_h).toBe(TL_MIN);
  });

  it("persistência: fechar e reabrir o Editor mantém o arranjo", () => {
    const a = renderHook(() => useWorkspace());
    act(() => a.result.current.mudar({ inspector_w: 500, timeline_h: 200 }));
    act(() => a.result.current.mudar({ canvas_zoom: 75, tracks: "compacta" }));
    a.unmount(); // "fecha o Editor"

    const b = renderHook(() => useWorkspace()); // "reabre"
    expect(b.result.current.ws.inspector_w).toBe(500);
    expect(b.result.current.ws.timeline_h).toBe(200);
    expect(b.result.current.ws.canvas_zoom).toBe(75);
    expect(b.result.current.ws.tracks).toBe("compacta");
  });

  it("localStorage corrompido não derruba o Editor — volta ao padrão", () => {
    window.localStorage.setItem(WS_KEY, "{isso não é json");
    expect(carregarWorkspace()).toEqual(wsPadrao());
    window.localStorage.setItem(WS_KEY, JSON.stringify({ canvas_zoom: 999, tracks: "x" }));
    const ws = carregarWorkspace();
    expect(ws.canvas_zoom).toBe("fit");
    expect(ws.tracks).toBe("normal");
  });

  it("presets de área de trabalho aplicam arranjos completos e o padrão restaura", () => {
    const { result } = renderHook(() => useWorkspace());
    act(() => result.current.aplicarPreset("legendas"));
    expect(result.current.ws.inspector_w).toBe(480);
    expect(result.current.ws.preset).toBe("legendas");
    act(() => result.current.mudar({ inspector_w: 300 }));
    expect(result.current.ws.preset).toBe("personalizado"); // arrastar sai do preset
    act(() => result.current.aplicarPreset("padrao"));
    expect(result.current.ws).toEqual(wsPadrao());
    expect(Object.keys(WORKSPACE_PRESETS)).toContain("video");
    expect(Object.keys(WORKSPACE_PRESETS)).toContain("timeline");
    expect(Object.keys(WORKSPACE_PRESETS)).toContain("motion");
  });

  it("colapsar e reabrir preserva o tamanho anterior do painel", () => {
    const { result } = renderHook(() => useWorkspace());
    act(() => result.current.mudar({ inspector_w: 420 }));
    act(() => result.current.mudar({ inspector_collapsed: true }));
    expect(result.current.ws.inspector_w).toBe(420); // tamanho não se perde
    act(() => result.current.mudar({ inspector_collapsed: false }));
    expect(result.current.ws.inspector_w).toBe(420);
  });

  it("reset devolve só a dimensão do splitter clicado", () => {
    const { result } = renderHook(() => useWorkspace());
    act(() => result.current.mudar({ inspector_w: 520, timeline_h: 180 }));
    act(() => result.current.resetInspector());
    expect(result.current.ws.inspector_w).toBe(INSP_PADRAO);
    expect(result.current.ws.timeline_h).toBe(180); // a outra dimensão fica
    act(() => result.current.resetTimeline());
    expect(result.current.ws.timeline_h).toBe(TL_PADRAO);
  });

  it("clamp reage ao tamanho da janela (55% de 768 ≠ 55% de 1080)", () => {
    expect(clampWorkspace({ ...wsPadrao(), timeline_h: 600 }, 768).timeline_h)
      .toBe(Math.round(768 * 0.55));
    expect(clampWorkspace({ ...wsPadrao(), timeline_h: 500 }, 1080).timeline_h).toBe(500);
  });
});

describe("Splitter — arraste, duplo clique e colapso", () => {
  it("reporta deltas do arraste e o duplo clique restaura o padrão", () => {
    const onDrag = vi.fn();
    const onReset = vi.fn();
    render(<Splitter dir="v" testid="sp" label="Largura" collapsed={false}
                     onDrag={onDrag} onReset={onReset} onToggleCollapse={() => {}} />);
    const el = screen.getByTestId("sp");
    fireEvent.pointerDown(el, { clientX: 500, clientY: 100 });
    expect(onDrag).toHaveBeenCalledWith(0, "start");
    fireEvent.pointerMove(el, { clientX: 460, clientY: 100 });
    expect(onDrag).toHaveBeenCalledWith(-40, "move"); // 40px para a esquerda
    fireEvent.pointerUp(el, { clientX: 460, clientY: 100 });
    expect(onDrag).toHaveBeenCalledWith(-40, "end");
    fireEvent.doubleClick(el);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("no sentido horizontal o delta é vertical (altura da timeline)", () => {
    const onDrag = vi.fn();
    render(<Splitter dir="h" testid="sp" label="Altura" collapsed={false}
                     onDrag={onDrag} onReset={() => {}} onToggleCollapse={() => {}} />);
    const el = screen.getByTestId("sp");
    fireEvent.pointerDown(el, { clientX: 100, clientY: 600 });
    fireEvent.pointerMove(el, { clientX: 100, clientY: 560 });
    expect(onDrag).toHaveBeenCalledWith(-40, "move"); // 40px para cima = mais alto
  });

  it("botão do splitter colapsa sem iniciar arraste; colapsado não arrasta", () => {
    const onDrag = vi.fn();
    const onToggle = vi.fn();
    const { rerender } = render(
      <Splitter dir="v" testid="sp" label="L" collapsed={false}
                onDrag={onDrag} onReset={() => {}} onToggleCollapse={onToggle} />);
    fireEvent.click(screen.getByTestId("sp-toggle"));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onDrag).not.toHaveBeenCalled();
    rerender(<Splitter dir="v" testid="sp" label="L" collapsed={true}
                       onDrag={onDrag} onReset={() => {}} onToggleCollapse={onToggle} />);
    fireEvent.pointerDown(screen.getByTestId("sp"), { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(screen.getByTestId("sp"), { clientX: 60, clientY: 10 });
    expect(onDrag).not.toHaveBeenCalled();
  });
});

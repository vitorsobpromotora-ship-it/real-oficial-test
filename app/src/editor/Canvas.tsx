/**
 * Canvas 9:16 do Editor — preview interativo WYSIWYG (Ponto 7).
 *
 * O usuário edita o que está vendo: corte (EDL), enquadramento, punch-in,
 * legendas (cartões resolvidos pelo MOTOR via /caption-cards) e Kit de Marca
 * aparecem aqui em tempo real. A "prévia real" renderizada pelo motor continua
 * disponível — este canvas é a camada interativa da mesma composição.
 * Controles de reprodução ficam DENTRO do vídeo (Ponto 6).
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { mediaUrl } from "../api/client";
import type { BrandKit, CaptionCards, Cut, KitLayer, Source } from "../api/types";
import { captionBox, fmtSrc, fmtT, outDur, srcToOut, type Draft } from "./model";
import { textPropsAt, type EffectInstance, type TextPreset } from "./motion";
import type { CanvasZoom } from "./workspace";

const CW = 1080;
const CH = 1920;

interface CropSeg { start: number; end: number; x0: number; x1: number }

interface Props {
  cut: Cut;
  source: Source;
  draft: Draft;
  title: string;
  videoUrl: string | null;
  kit: BrandKit | null;
  captions: CaptionCards | null;
  playhead: number; // tempo da FONTE
  playing: boolean;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  videoErro: boolean;
  onVideoErro(): void;
  onTogglePlay(): void;
  onSeekOut(tOut: number): void;
  onSelectCaption(): void;
  capSelecionada: boolean; // ferramenta Legenda ativa → mostra a caixa e permite arrastar
  safeArea: boolean;
  onCaptionMove(pos: { pos_x: number; pos_y: number }): void;
  // zoom do CANVAS (v4 FASE A) — separado do zoom da timeline; "fit" = encaixa
  zoom: CanvasZoom;
  onZoom(z: CanvasZoom): void;
  motionPresets: TextPreset[]; // catálogo do motor — preview avalia AS MESMAS trilhas
}

const MODO_POR_FRAMING: Record<string, string> = {
  left: "crop", right: "crop", center: "crop", blur: "blur_pad",
  fit: "fit_pad", two: "two_person", split: "split_screen",
};

export default function Canvas(p: Props) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [fitW, setFitW] = useState(300); // largura CSS do canvas no modo "fit"
  const [vol, setVol] = useState(1);
  const [muted, setMuted] = useState(false);
  const [assets, setAssets] = useState<Record<string, string>>({});

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const mede = () => {
      const h = el.clientHeight || 480;
      const w = el.clientWidth || 300;
      // "contain" 9:16 — o player cresce/encolhe com o workspace e NUNCA distorce
      setFitW(Math.max(180, Math.min(w - 20, ((h - 20) * 9) / 16)));
    };
    mede();
    if (typeof ResizeObserver === "undefined") return; // jsdom/testes
    const ro = new ResizeObserver(mede);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // zoom do canvas: 100% = pixels reais da composição 1080×1920
  const cw = p.zoom === "fit" ? fitW : Math.round(CW * (p.zoom / 100));

  // pan: com zoom além do encaixe, arrastar o fundo rola a área (scroll = pan)
  function panStart(e: React.PointerEvent) {
    const el = wrapRef.current;
    if (p.zoom === "fit" || !el || e.target !== el) return;
    const sx = el.scrollLeft + e.clientX;
    const sy = el.scrollTop + e.clientY;
    const move = (ev: PointerEvent) => {
      el.scrollLeft = sx - ev.clientX;
      el.scrollTop = sy - ev.clientY;
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  // resolve os arquivos do kit (imagens/vídeos decorativos) para URLs de mídia
  const layout = p.kit?.layout ?? null;
  useEffect(() => {
    const paths = new Set<string>();
    for (const l of layout?.layers ?? []) if (l.path) paths.add(l.path);
    if (layout?.background?.path) paths.add(layout.background.path);
    if (!layout && p.kit?.logo_path) paths.add(p.kit.logo_path);
    let vivo = true;
    for (const path of paths) {
      if (assets[path]) continue;
      const base = path.split(/[\\/]/).pop() ?? path;
      mediaUrl(`/api/v1/media/brand/${base}`).then((u) => {
        if (vivo) setAssets((m) => ({ ...m, [path]: u }));
      });
    }
    return () => { vivo = false; };
  }, [layout, p.kit?.logo_path]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const v = p.videoRef.current;
    if (v) {
      v.volume = vol;
      if (!p.draft.audio.mute) v.muted = muted;
    }
  }, [vol, muted, p.videoRef, p.draft.audio.mute]);

  const SC = cw / CW;
  const ch = (cw * 16) / 9;
  const srcW = p.source.width || 1920;
  const srcH = p.source.height || 1080;
  const segs = p.draft.segments;
  const outNow = srcToOut(segs, p.playhead);
  const outTotal = outDur(segs);

  // ----- geometria do vídeo (enquadramento efetivo no instante atual) -----
  const plan = p.cut.crop_plan;
  const planSegs = ((plan?.segments as CropSeg[] | undefined) ?? []);
  const clusters = ((plan as { clusters?: number[] } | null)?.clusters ?? []);
  const modo = p.draft.framing !== "auto"
    ? MODO_POR_FRAMING[p.draft.framing] ?? "crop"
    : plan?.mode ?? "crop";
  const cropW = ((plan as { crop_w?: number } | null)?.crop_w)
    ?? Math.floor((srcH * 9) / 16 / 2) * 2;

  function clusterX(m: string): number {
    const cx = m === "left"
      ? (clusters.length ? Math.min(...clusters) : srcW * 0.28)
      : m === "right"
        ? (clusters.length ? Math.max(...clusters) : srcW * 0.72)
        : srcW / 2;
    return Math.min(Math.max(cx - cropW / 2, 0), Math.max(0, srcW - cropW));
  }

  function cropXAt(t: number): number {
    const ov = p.draft.framing_segments.find((s) => t >= s.start_s && t <= s.end_s);
    if (ov) return clusterX(ov.mode);
    if (["left", "right", "center"].includes(p.draft.framing)) return clusterX(p.draft.framing);
    const seg = planSegs.find((s) => t >= s.start && t <= s.end)
      ?? planSegs[planSegs.length - 1];
    if (!seg) return clusterX("center");
    const d = Math.max(0.001, seg.end - seg.start);
    const f = Math.min(1, Math.max(0, (t - seg.start) / d));
    return seg.x0 + (seg.x1 - seg.x0) * f;
  }

  const idxSeg = Math.max(0, segs.findIndex((s) => p.playhead < s.src_end));
  const punchZ = p.draft.punch_in === "leve" ? 1.05
    : p.draft.punch_in === "dinamico" && idxSeg % 2 === 1 ? 1.1 : 1;

  // caixa do vídeo: camada "source" do layout do kit, ou o canvas inteiro
  const srcLayer = layout?.layers.find((l) => l.type === "source" && !l.hidden);
  const box = srcLayer
    ? { x: srcLayer.x, y: srcLayer.y, w: srcLayer.w, h: srcLayer.h ?? (srcLayer.w * 16) / 9,
        radius: srcLayer.radius ?? 0, border_w: srcLayer.border_w ?? 0,
        border_color: srcLayer.border_color ?? "#fff", shadow: !!srcLayer.shadow }
    : { x: 0, y: 0, w: CW, h: CH, radius: 0, border_w: 0, border_color: "", shadow: false };

  let videoStyle: React.CSSProperties;
  if (modo === "crop") {
    const x = cropXAt(p.playhead);
    const sc2 = ((box.w * SC) / cropW) * punchZ;
    const dx = (cropW - cropW / punchZ) / 2;
    const dy = (srcH - srcH / punchZ) / 2;
    videoStyle = {
      position: "absolute",
      left: -(x + dx) * sc2,
      top: -dy * sc2 + ((box.h - (box.w * 16) / 9) * SC) / 2,
      width: srcW * sc2,
      height: srcH * sc2,
      maxWidth: "none",
    };
  } else {
    // fit/blur/two/split: aproximação "contain" — a prévia real mostra o modo exato
    videoStyle = { position: "absolute", inset: 0, width: "100%", height: "100%",
                   objectFit: "contain" };
  }

  // ----- legenda ativa (cartões do MOTOR + estilo ao vivo do draft) -----
  const st = { ...(p.captions?.style ?? {}), ...(p.draft.caption_style ?? {}) } as
    Record<string, unknown>;
  const card = (p.captions?.cards ?? []).find((c) => outNow >= c.start && outNow <= c.end) ?? null;
  // geometria da legenda pela MESMA regra do motor (impede divergência)
  const { ml, mr, anchor_top: anchor } = captionBox(st, [CW, CH]);
  const fontPx = Number(st.font_size ?? 74) * SC;
  const outlinePx = Math.max(1, Number(st.outline ?? 3) * SC);
  const oc = String(st.outline_color ?? "#000");
  const karaoke = Boolean(st.karaoke) || st.anim_word === "color";
  const boxBg = Number(st.border_style ?? 1) === 3 ? String(st.back_color ?? "#000") : null;

  /** Ênfase efetiva da palavra: a do rascunho vence a que veio do motor. */
  function motionDe(w: { idx: number | null; ins_id?: string | null }):
      EffectInstance | undefined {
    return (p.draft.motion?.effects ?? []).find((e) =>
      e.type === "text_emphasis" && e.enabled !== false
      && e.target.kind === "words"
      && ((w.idx != null && (e.target.idx ?? []).includes(w.idx))
        || (w.ins_id != null && (e.target.ins_ids ?? []).includes(w.ins_id))));
  }

  function enfDe(w: { idx: number | null; ins_id?: string | null;
                      emphasis?: { effect: string; intensity?: string; color?: string } | null }) {
    const local = p.draft.word_emphasis.find((e) =>
      (w.idx != null && (e.idx ?? []).includes(w.idx))
      || (w.ins_id && (e.ins_ids ?? []).includes(w.ins_id)));
    return local ?? w.emphasis ?? undefined;
  }

  function textoDe(w: { idx: number | null; word: string }): string {
    const t = (w.idx != null && p.draft.word_overrides[String(w.idx)]) || w.word;
    return st.uppercase ? t.toUpperCase() : t;
  }

  const outline = `${-outlinePx}px ${-outlinePx}px 0 ${oc}, ${outlinePx}px ${-outlinePx}px 0 ${oc}, `
    + `${-outlinePx}px ${outlinePx}px 0 ${oc}, ${outlinePx}px ${outlinePx}px 0 ${oc}`;

  // arrastar a legenda direto no vídeo (Ponto 21) — grava X/Y NORMALIZADOS
  function arrastarLegenda(e: React.PointerEvent) {
    e.stopPropagation();
    if (!p.capSelecionada) {
      p.onSelectCaption(); // 1º clique seleciona a ferramenta (Ponto 25)
      return;
    }
    const alvo = e.currentTarget as HTMLElement;
    alvo.setPointerCapture?.(e.pointerId);
    const caixa = boxRef.current?.getBoundingClientRect();
    if (!caixa) return;
    const mover = (ev: PointerEvent | React.PointerEvent) => {
      const px = Math.min(1, Math.max(0, (ev.clientX - caixa.left) / caixa.width));
      const py = Math.min(1, Math.max(0, (ev.clientY - caixa.top) / caixa.height));
      p.onCaptionMove({ pos_x: Math.round(px * 1000) / 1000,
                        pos_y: Math.round(py * 1000) / 1000 });
    };
    mover(e);
    const up = () => {
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", up);
  }

  return (
    <div className="cv-area">
      <div className="cv-zoomctl" data-testid="cv-zoomctl">
        {(["fit", 50, 75, 100] as CanvasZoom[]).map((z) => (
          <button key={z} className={p.zoom === z ? "on" : ""}
                  data-testid={`cv-zoom-${z}`}
                  title={z === "fit" ? "Encaixar no espaço" : `${z}% do tamanho real`}
                  onClick={() => p.onZoom(z)}>
            {z === "fit" ? "Fit" : `${z}%`}
          </button>
        ))}
      </div>
      <div className={`cv-wrap${p.zoom !== "fit" ? " zoomed" : ""}`} ref={wrapRef}
           onPointerDown={panStart}>
      <div className="cv-canvas" ref={boxRef} style={{ width: cw, height: ch }}>
        {/* fundo do layout do kit */}
        <div className="cv-bg" style={bgStyle(layout, assets)} />

        {/* caixa do vídeo (camada source do kit ou tela cheia) */}
        <div
          className="cv-vbox"
          style={{
            left: box.x * SC, top: box.y * SC, width: box.w * SC, height: box.h * SC,
            borderRadius: box.radius * SC,
            border: box.border_w ? `${Math.max(1, box.border_w * SC)}px solid ${box.border_color}` : "none",
            boxShadow: box.shadow ? "0 18px 42px rgba(0,0,0,.55)" : "none",
          }}
          onClick={p.onTogglePlay}
        >
          {p.videoUrl ? (
            <video
              ref={p.videoRef as React.RefObject<HTMLVideoElement>}
              src={p.videoUrl}
              style={videoStyle}
              onError={p.onVideoErro}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = segs[0]?.src_start ?? 0;
              }}
            />
          ) : (
            <div className="ed-loading">Abrindo vídeo…</div>
          )}
        </div>

        {/* camadas do kit acima do vídeo (imagens, textos, formas, vídeo deco) */}
        {(layout?.layers ?? []).map((l, i) =>
          l.hidden || l.type === "source" || l.type === "captions" ? null : (
            <KitLayerView key={l.id || i} l={l} sc={SC} titulo={p.title} assets={assets} />
          ))}
        {!layout && p.kit?.logo_path && assets[p.kit.logo_path] ? (
          <img
            src={assets[p.kit.logo_path]} alt="" className="cv-logo"
            style={{
              width: cw * 0.18, opacity: p.kit.logo_opacity,
              ...({ tl: { left: 16, top: 32 }, tr: { right: 16, top: 32 },
                    bl: { left: 16, bottom: 46 }, br: { right: 16, bottom: 46 } }[
                      p.kit.logo_position] ?? { right: 16, top: 32 }),
            }}
          />
        ) : null}

        {/* legenda ativa — cartão calculado pelo motor, estilo ao vivo */}
        {p.safeArea ? (
          <div className="cv-safe" data-testid="cv-safe">
            <span>área segura</span>
          </div>
        ) : null}

        {card ? (
          <div
            className={`cv-caption${p.capSelecionada ? " sel" : ""}`}
            data-testid="cv-caption"
            onPointerDown={arrastarLegenda}
            style={{
              top: anchor * (ch / CH),
              left: ml * SC,
              right: mr * SC,
              textAlign: (st.align as React.CSSProperties["textAlign"]) ?? "center",
              fontFamily: `${st.font_family ?? "Montserrat"}, Inter, sans-serif`,
              fontSize: fontPx,
              fontWeight: st.bold === false ? 600 : 800,
              letterSpacing: Number(st.letter_spacing ?? 0) * SC,
              lineHeight: 1.18,
            }}
          >
            {card.words.map((w, i) => {
              const falada = outNow >= w.start_s;
              const cor = karaoke
                ? (falada ? String(st.highlight_color ?? "#FFD400") : String(st.text_color ?? "#FFF"))
                : String(st.text_color ?? "#FFF");
              // ênfase (Pontos 15–18): aproximação viva do que o ASS vai queimar —
              // só escala/cor, jamais tamanho de fonte (a linha não pode pular)
              const enf = enfDe(w);
              const dentro = enf && outNow >= w.start_s
                && outNow < w.start_s + Math.max(0.25, (w.end_s - w.start_s) * 0.55);
              const k = enf?.intensity === "forte" ? 1.5
                : enf?.intensity === "suave" ? 0.6 : 1;
              const escalas: Record<string, number> = {
                pop: 118, punch: 136, impact: 128, fatality: 142, bounce: 124,
                soft_lift: 108, shake: 100, color_hit: 100, flash: 100,
                glow: 100, outline_burst: 100, highlight_box: 100,
              };
              const esc = dentro
                ? 1 + (((escalas[enf!.effect] ?? 100) - 100) * k) / 100 : 1;
              const corEnf = enf?.color
                ?? (dentro && enf?.effect === "fatality" ? "#FF2D2D" : undefined);
              const caixaEnf = dentro && enf?.effect === "highlight_box";
              // Motion Engine (v4): avalia AS MESMAS trilhas do render — a
              // paridade vem de textPropsAt (contrato shared/motion-cases)
              const fxMo = motionDe(w);
              const presetMo = fxMo
                ? p.motionPresets.find((pr) => pr.id === fxMo.preset) : undefined;
              const mo = fxMo && presetMo
                ? textPropsAt(fxMo, presetMo, outNow) : null;
              const moAtivo = !!mo && (mo.scale !== 100 || mo.scale_x !== 100
                || mo.scale_y !== 100 || mo.blur > 0
                || mo.rot !== 0 || mo.alpha > 0 || mo.bord !== 0);
              const moSx = mo ? (mo.scale_x !== 100 ? mo.scale_x : mo.scale) / 100 : 1;
              const moSy = mo ? (mo.scale_y !== 100 ? mo.scale_y : mo.scale) / 100 : 1;
              return (
                <span key={i}>
                  <span
                    className={`cv-word${enf ? " enf" : ""}`}
                    style={{
                      color: moAtivo
                        ? ((fxMo?.params?.color as string | undefined)
                          ?? presetMo?.color ?? corEnf ?? cor)
                        : corEnf ?? cor,
                      textShadow: boxBg ? "none" : outline,
                      background: caixaEnf ? String(st.highlight_color ?? "#FFD400")
                        : boxBg ?? "transparent",
                      padding: boxBg || caixaEnf ? `${2 * SC}px ${10 * SC}px` : 0,
                      borderRadius: boxBg || caixaEnf ? 6 * SC : 0,
                      transform: moAtivo
                        ? `scale(${moSx.toFixed(3)}, ${moSy.toFixed(3)})`
                          + (mo!.rot ? ` rotate(${mo!.rot.toFixed(2)}deg)` : "")
                        : esc !== 1 ? `scale(${esc.toFixed(3)})` : undefined,
                      filter: moAtivo && mo!.blur > 0
                        ? `blur(${(mo!.blur * SC).toFixed(1)}px)` : undefined,
                      opacity: moAtivo ? 1 - mo!.alpha : undefined,
                      transformOrigin: "center bottom",
                      transition: moAtivo ? "none"
                        : "transform .09s ease-out, color .09s linear",
                    }}
                  >
                    {textoDe(w)}
                  </span>
                  {card.breaks.includes(i + 1) ? <br /> : " "}
                </span>
              );
            })}
          </div>
        ) : null}

        {(modo === "two_person" || modo === "split_screen" || modo === "blur_pad") ? (
          <div className="cv-note">
            {modo === "blur_pad" ? "fundo desfocado" : modo === "two_person" ? "duas pessoas" : "split screen"}
            {" "}— confira o resultado exato na prévia real
          </div>
        ) : null}

        {p.videoErro ? (
          <div className="ed-loading" style={{ position: "absolute", inset: 0 }}>
            O player não decodifica este formato. A edição continua funcionando —
            use “Gerar prévia real” para assistir.
          </div>
        ) : null}

        {/* controles DENTRO do vídeo (Ponto 6) */}
        <div className="cv-controls" onClick={(e) => e.stopPropagation()}>
          <button onClick={p.onTogglePlay} title="Espaço" data-testid="cv-play">
            {p.playing ? "⏸" : "▶"}
          </button>
          <span className="cv-tc" title={`Origem: ${fmtSrc(p.playhead)}`}>
            {fmtT(outNow)} / {fmtT(outTotal)}
          </span>
          <input
            className="cv-seek" type="range" min={0} max={Math.max(0.1, outTotal)}
            step={0.05} value={Math.min(outNow, outTotal)}
            onChange={(e) => p.onSeekOut(Number(e.target.value))}
          />
          <button onClick={() => setMuted(!muted)} title="Som do player">
            {muted || p.draft.audio.mute ? "🔇" : "🔊"}
          </button>
          <input
            type="range" min={0} max={1} step={0.05} value={vol} style={{ width: 64 }}
            onChange={(e) => setVol(Number(e.target.value))}
          />
          <button
            title="Tela cheia"
            onClick={() => {
              const el = boxRef.current;
              if (!el) return;
              if (document.fullscreenElement) void document.exitFullscreen();
              else void el.requestFullscreen?.();
            }}
          >
            ⛶
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}

function bgStyle(layout: BrandKit["layout"], assets: Record<string, string>): React.CSSProperties {
  const bg = layout?.background;
  if (!bg) return { background: "#000" };
  if (bg.type === "color") return { background: bg.color ?? "#000" };
  if (bg.type === "gradient") {
    const dir = bg.direction === "horizontal" ? "90deg"
      : bg.direction === "diagonal" ? "135deg" : "180deg";
    return { background: `linear-gradient(${dir}, ${bg.color ?? "#000"}, ${bg.color2 ?? "#222"})` };
  }
  if (bg.type === "image" && bg.path && assets[bg.path]) {
    return { background: `url(${assets[bg.path]}) center / cover` };
  }
  return { background: "#0a0a10" }; // vídeo/blur de fundo: exato só na prévia real
}

function KitLayerView({ l, sc, titulo, assets }:
  { l: KitLayer; sc: number; titulo: string; assets: Record<string, string> }) {
  const pos: React.CSSProperties = {
    position: "absolute", left: l.x * sc, top: l.y * sc, width: l.w * sc,
    height: l.h != null ? l.h * sc : undefined, opacity: l.opacity ?? 1,
    pointerEvents: "none",
  };
  if (l.type === "image" && l.path && assets[l.path]) {
    return <img src={assets[l.path]} alt="" style={{ ...pos, objectFit: "contain" }} />;
  }
  if (l.type === "video" && l.path && assets[l.path]) {
    return <video src={assets[l.path]} muted loop autoPlay playsInline
                  style={{ ...pos, objectFit: "cover", borderRadius: (l.radius ?? 0) * sc }} />;
  }
  if (l.type === "text") {
    return (
      <div style={{
        ...pos, color: l.color ?? "#fff", fontFamily: `${l.font ?? "Inter"}, sans-serif`,
        fontSize: (l.size ?? 60) * sc, fontWeight: l.bold === false ? 500 : 800,
        textAlign: l.align ?? "center", background: l.bg ?? "transparent",
        padding: l.bg ? `${6 * sc}px ${14 * sc}px` : 0, borderRadius: 10 * sc,
        lineHeight: 1.2,
      }}>
        {(l.text ?? "").replace("{titulo}", titulo)}
      </div>
    );
  }
  if (l.type === "shape") {
    return <div style={{ ...pos, background: l.fill ?? "#fff",
                         borderRadius: (l.radius ?? 0) * sc }} />;
  }
  return null;
}

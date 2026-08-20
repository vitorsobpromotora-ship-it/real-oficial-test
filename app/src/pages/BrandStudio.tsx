// Brand Studio (F3): editor visual do layout do kit — canvas 9:16 com camadas.
// Arraste para mover, alças para redimensionar, snapping em centro/bordas/área
// segura. O que se vê aqui é o que o render compõe (mesmo layout JSON).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, get, mediaUrl, patch } from "../api/client";
import type { BrandKit, KitLayer, KitLayout, KitTemplate } from "../api/types";

const S = 0.36; // escala de exibição do canvas 1080×1920
const CW = 1080;
const CH = 1920;
const SAFE = { l: 60, r: 60, t: 220, b: 320 }; // área segura (UI do TikTok/Reels)

const LAYER_LABEL: Record<string, string> = {
  source: "Vídeo do corte", image: "Imagem", text: "Texto", shape: "Forma",
  video: "Vídeo decorativo", captions: "Área das legendas",
};
const ANIMS: { id: string; label: string }[] = [
  { id: "none", label: "Sem animação" }, { id: "fade", label: "Fade" },
  { id: "slide_up", label: "Deslizar de baixo" }, { id: "slide_down", label: "Deslizar de cima" },
  { id: "slide_left", label: "Deslizar da direita" }, { id: "slide_right", label: "Deslizar da esquerda" },
];
const TEXT_ANIMS = [...ANIMS.slice(0, 3),
  { id: "scale", label: "Crescer" }, { id: "bounce", label: "Bounce" }];

function novoId() {
  return Math.random().toString(36).slice(2, 8);
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

const fname = (p?: string) => (p ?? "").split(/[\\/]/).pop() ?? "";

export default function BrandStudio() {
  const { kitId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();

  const kitsQ = useQuery({ queryKey: ["brand-kits"], queryFn: () => get<BrandKit[]>("/api/v1/brand-kits") });
  const kit = kitsQ.data?.find((k) => k.id === kitId);
  const effQ = useQuery({
    queryKey: ["kit-layout", kitId],
    queryFn: () => get<{ layout: KitLayout; persisted: boolean }>(
      `/api/v1/brand-kits/${kitId}/layout/effective`),
  });
  const tplQ = useQuery({
    queryKey: ["kit-templates"],
    queryFn: () => get<{ templates: KitTemplate[] }>("/api/v1/brand-kits/templates"),
    staleTime: Infinity,
  });

  const [draft, setDraft] = useState<KitLayout | null>(null);
  const [saved, setSaved] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [guides, setGuides] = useState(true);
  const [snapLines, setSnapLines] = useState<{ v: number[]; h: number[] }>({ v: [], h: [] });
  const [toast, setToast] = useState("");
  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{
    i: number; mode: string; sx: number; sy: number; orig: KitLayer; moved: boolean;
  } | null>(null);

  function flash(m: string, ms = 3000) {
    setToast(m);
    window.setTimeout(() => setToast(""), ms);
  }

  useEffect(() => {
    if (!effQ.data || draft) return;
    setDraft(clone(effQ.data.layout));
    setSaved(effQ.data.persisted ? JSON.stringify(effQ.data.layout) : "__legado__");
  }, [effQ.data, draft]);

  // resolve URLs de mídia (logo/assets) para o canvas
  useEffect(() => {
    if (!draft) return;
    const paths = new Set<string>();
    if (draft.background.path) paths.add(draft.background.path);
    for (const l of draft.layers) if (l.path) paths.add(l.path);
    paths.forEach((p) => {
      const n = fname(p);
      if (!n || assetUrls[p]) return;
      mediaUrl(`/api/v1/media/brand/${encodeURIComponent(n)}`)
        .then((u) => setAssetUrls((m) => ({ ...m, [p]: u })));
    });
  }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = !!draft && JSON.stringify(draft) !== saved;

  const salvar = useMutation({
    mutationFn: () => patch<BrandKit>(`/api/v1/brand-kits/${kitId}`, { layout: draft }),
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ["brand-kits"] });
      setSaved(JSON.stringify(novo.layout));
      flash("Layout salvo — os próximos renders e prévias usam esta composição.");
    },
    onError: (e: Error) => flash(`Falha ao salvar: ${e.message}`, 5200),
  });

  function upd(fn: (d: KitLayout) => void) {
    if (!draft) return;
    const d = clone(draft);
    fn(d);
    setDraft(d);
  }

  const updLayer = (i: number, patchL: Partial<KitLayer>) =>
    upd((d) => Object.assign(d.layers[i], patchL));

  // ---------------- interação no canvas (mover/redimensionar + snap) ----------------
  function snap(v: number, cands: number[], lines: number[], tol = 14): number {
    for (const c of cands) {
      if (Math.abs(v - c) < tol) {
        lines.push(c);
        return c;
      }
    }
    return v;
  }

  function beginDrag(e: React.PointerEvent, i: number, mode: string) {
    if (!draft) return;
    const l = draft.layers[i];
    if (l.locked) {
      setSel(i);
      return;
    }
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = { i, mode, sx: e.clientX, sy: e.clientY, orig: clone(l), moved: false };
    setSel(i);
  }

  function onDragMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d || !draft) return;
    const dx = (e.clientX - d.sx) / S;
    const dy = (e.clientY - d.sy) / S;
    if (Math.abs(dx) + Math.abs(dy) < 2) return;
    d.moved = true;
    const l = clone(d.orig);
    const h = l.h ?? (l.type === "captions" ? 200 : 200);
    const vLines: number[] = [];
    const hLines: number[] = [];
    if (d.mode === "move") {
      const vx: number[] = [];
      const vy: number[] = [];
      l.x = Math.round(snap(snap(d.orig.x + dx,
        [0, SAFE.l, (CW - l.w) / 2, CW - l.w - SAFE.r, CW - l.w], vx), [], []));
      l.y = Math.round(snap(snap(d.orig.y + dy,
        [0, SAFE.t, (CH - h) / 2, CH - h - SAFE.b, CH - h], vy), [], []));
      vx.forEach((c) => vLines.push(c === (CW - l.w) / 2 ? CW / 2 : c + (c < CW / 2 ? 0 : l.w)));
      vy.forEach((c) => hLines.push(c === (CH - h) / 2 ? CH / 2 : c + (c < CH / 2 ? 0 : h)));
    } else {
      const min = 60;
      if (d.mode.includes("e")) l.w = Math.max(min, Math.round(d.orig.w + dx));
      if (d.mode.includes("s") && l.h !== undefined) l.h = Math.max(min, Math.round((d.orig.h ?? min) + dy));
      if (d.mode.includes("w")) {
        const nw = Math.max(min, Math.round(d.orig.w - dx));
        l.x = d.orig.x + (d.orig.w - nw);
        l.w = nw;
      }
      if (d.mode.includes("n") && l.h !== undefined) {
        const nh = Math.max(min, Math.round((d.orig.h ?? min) - dy));
        l.y = d.orig.y + ((d.orig.h ?? min) - nh);
        l.h = nh;
      }
    }
    setSnapLines({ v: vLines, h: hLines });
    upd((dd) => Object.assign(dd.layers[d.i], l));
  }

  function endDrag() {
    dragRef.current = null;
    setSnapLines({ v: [], h: [] });
  }

  // ---------------- operações de camada ----------------
  function addLayer(l: KitLayer) {
    upd((d) => {
      d.layers.push(l);
    });
    setSel((draft?.layers.length ?? 0));
  }

  function addTexto() {
    addLayer({ id: novoId(), type: "text", text: "{titulo}", x: 60, y: 120, w: 960,
               font: "Montserrat", size: 60, color: "#FFFFFF", bg: null, align: "center",
               bold: true, anim: "fade", start_s: 0, end_s: null });
  }
  function addForma() {
    addLayer({ id: novoId(), type: "shape", x: 90, y: 1700, w: 900, h: 110,
               fill: "#FF4757CC", radius: 24, opacity: 1, anim: "none", start_s: 0, end_s: null });
  }
  function addCaptions() {
    if (draft?.layers.some((l) => l.type === "captions")) {
      flash("Já existe uma área de legendas — mova/redimensione a existente.");
      return;
    }
    addLayer({ id: novoId(), type: "captions", x: 65, y: 1280, w: 950 });
  }

  async function uploadAsset(file: File): Promise<string> {
    const fd = new FormData();
    fd.append("file", file);
    const r = await api<{ path: string }>(`/api/v1/brand-kits/${kitId}/assets`,
      { method: "POST", body: fd });
    return r.path;
  }

  async function addImagem(file: File) {
    try {
      const p = await uploadAsset(file);
      addLayer({ id: novoId(), type: "image", path: p, x: 390, y: 640, w: 300, h: 300,
                 opacity: 1, anim: "fade", start_s: 0, end_s: null });
    } catch (e) {
      flash(`Falha no upload: ${(e as Error).message}`, 5000);
    }
  }
  async function addVideoDeco(file: File) {
    try {
      const p = await uploadAsset(file);
      addLayer({ id: novoId(), type: "video", path: p, x: 60, y: 1440, w: 420, h: 240,
                 loop: true, start_s: 0, end_s: null });
    } catch (e) {
      flash(`Falha no upload: ${(e as Error).message}`, 5000);
    }
  }

  function removeLayer(i: number) {
    if (!draft) return;
    if (draft.layers[i].type === "source") {
      flash("A camada do vídeo do corte não pode ser removida.");
      return;
    }
    upd((d) => {
      d.layers.splice(i, 1);
    });
    setSel(null);
  }

  function moveLayer(i: number, dir: -1 | 1) {
    if (!draft) return;
    const j = i + dir;
    if (j < 0 || j >= draft.layers.length) return;
    upd((d) => {
      const [l] = d.layers.splice(i, 1);
      d.layers.splice(j, 0, l);
    });
    setSel(j);
  }

  function aplicarTemplate(t: KitTemplate) {
    const lay = clone(t.layout);
    // preserva o logo do kit como camada, se existir e o template não tiver imagem
    if (kit?.logo_path && !lay.layers.some((l) => l.type === "image")) {
      lay.layers.splice(lay.layers.length - 1, 0,
        { id: novoId(), type: "image", path: kit.logo_path, x: CW - 194 - 48, y: 96,
          w: 194, h: 194, opacity: kit.logo_opacity ?? 1, anim: "none",
          start_s: 0, end_s: null });
    }
    setDraft(lay);
    setSel(null);
    flash(`Template “${t.name}” aplicado — ajuste e salve.`);
  }

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.key === "Delete" || e.key === "Backspace") && sel != null) removeLayer(sel);
      if (e.key.startsWith("Arrow") && sel != null && draft) {
        e.preventDefault();
        const passo = e.shiftKey ? 1 : 10;
        const l = draft.layers[sel];
        if (l.locked) return;
        updLayer(sel, {
          x: l.x + (e.key === "ArrowRight" ? passo : e.key === "ArrowLeft" ? -passo : 0),
          y: l.y + (e.key === "ArrowDown" ? passo : e.key === "ArrowUp" ? -passo : 0),
        });
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  if (effQ.isError) return <div className="err">Kit não encontrado.</div>;
  if (!draft || !kit) return <div className="empty">Abrindo o Estúdio…</div>;

  const bg = draft.background;
  const bgCss: React.CSSProperties =
    bg.type === "gradient"
      ? { background: `linear-gradient(${bg.direction === "horizontal" ? "90deg"
          : bg.direction === "diagonal" ? "135deg" : "180deg"},
          ${bg.color ?? "#101418"}, ${bg.color2 ?? "#000"})` }
      : bg.type === "image" && bg.path && assetUrls[bg.path]
        ? { backgroundImage: `url(${assetUrls[bg.path]})`, backgroundSize: "cover",
            backgroundPosition: "center" }
        : bg.type === "blur"
          ? { background: "linear-gradient(180deg,#26303f,#0c1017)" }
          : { background: bg.color ?? "#000" };

  const selLayer = sel != null ? draft.layers[sel] : null;

  return (
    <div className="studio">
      <div className="pagehead">
        <div className="row">
          <button onClick={() => nav("/kits")}>← Kits</button>
          <h1 style={{ margin: 0 }}>Estúdio · {kit.name}</h1>
          {!effQ.data?.persisted && saved === "__legado__" ? (
            <span className="chip">kit clássico — salve para ativar o layout</span>
          ) : null}
        </div>
        <div className="row">
          {toast ? <span className="sub">{toast}</span> : null}
          <label className="ed-check" style={{ margin: 0 }}>
            <input type="checkbox" checked={guides} onChange={(e) => setGuides(e.target.checked)} />
            Guias
          </label>
          <button className="primary" disabled={!dirty || salvar.isPending}
                  onClick={() => salvar.mutate()}>
            {salvar.isPending ? "Salvando…" : dirty ? "Salvar layout" : "Salvo"}
          </button>
        </div>
      </div>

      <div className="st-main">
        <div className="st-canvas-wrap card">
          <div
            className="st-canvas"
            ref={canvasRef}
            style={{ width: CW * S, height: CH * S, ...bgCss }}
            onPointerDown={() => setSel(null)}
          >
            {bg.type === "blur" ? <div className="st-bglabel">fundo: vídeo desfocado</div> : null}
            {bg.type === "video" ? <div className="st-bglabel">fundo: vídeo</div> : null}
            {draft.layers.map((l, i) => {
              if (l.hidden) return null;
              const h = (l.h ?? (l.type === "captions" ? 200 : l.type === "text"
                ? (l.size ?? 60) * 1.7 : 200)) * S;
              const style: React.CSSProperties = {
                left: l.x * S, top: l.y * S, width: l.w * S, height: h,
                opacity: l.opacity ?? 1,
              };
              return (
                <div
                  key={l.id}
                  className={`st-layer st-${l.type}${sel === i ? " on" : ""}${l.locked ? " locked" : ""}`}
                  style={style}
                  onPointerDown={(e) => beginDrag(e, i, "move")}
                  onPointerMove={onDragMove}
                  onPointerUp={endDrag}
                >
                  {l.type === "source" ? (
                    <div className="st-source"
                         style={{ borderRadius: (l.radius ?? 0) * S,
                                  border: l.border_w ? `${Math.max(1, l.border_w * S)}px solid ${l.border_color ?? "#fff"}` : undefined,
                                  boxShadow: l.shadow ? "0 14px 34px #000c" : undefined }}>
                      🎬 Vídeo do corte
                    </div>
                  ) : l.type === "image" ? (
                    l.path && assetUrls[l.path]
                      ? <img src={assetUrls[l.path]} draggable={false} alt="" />
                      : <div className="st-ph">🖼 {fname(l.path) || "imagem"}</div>
                  ) : l.type === "text" ? (
                    <div className="st-text"
                         style={{ fontFamily: l.font, fontSize: (l.size ?? 60) * S,
                                  color: l.color, fontWeight: l.bold ? 800 : 500,
                                  textAlign: l.align ?? "center",
                                  background: l.bg ?? "transparent" }}>
                      {(l.text ?? "").replace("{titulo}", "Título do corte")}
                    </div>
                  ) : l.type === "shape" ? (
                    <div className="st-shape"
                         style={{ background: l.fill ?? "#FF4757",
                                  borderRadius: (l.radius ?? 0) * S }} />
                  ) : l.type === "video" ? (
                    <div className="st-ph">🎞 {fname(l.path) || "vídeo"} (mudo)</div>
                  ) : (
                    <div className="st-cap">Aa Legendas aqui</div>
                  )}
                  {sel === i && !l.locked ? (
                    <>
                      {["nw", "ne", "sw", "se"].map((m) => (
                        <i key={m} className={`st-h ${m}`}
                           onPointerDown={(e) => beginDrag(e, i, m)}
                           onPointerMove={onDragMove} onPointerUp={endDrag} />
                      ))}
                      <i className="st-h e" onPointerDown={(e) => beginDrag(e, i, "e")}
                         onPointerMove={onDragMove} onPointerUp={endDrag} />
                      {l.h !== undefined ? (
                        <i className="st-h s" onPointerDown={(e) => beginDrag(e, i, "s")}
                           onPointerMove={onDragMove} onPointerUp={endDrag} />
                      ) : null}
                    </>
                  ) : null}
                </div>
              );
            })}
            {guides ? (
              <div className="st-safe"
                   style={{ left: SAFE.l * S, top: SAFE.t * S,
                            width: (CW - SAFE.l - SAFE.r) * S,
                            height: (CH - SAFE.t - SAFE.b) * S }} />
            ) : null}
            {snapLines.v.map((x) => (
              <div key={`v${x}`} className="st-snap v" style={{ left: x * S }} />
            ))}
            {snapLines.h.map((y) => (
              <div key={`h${y}`} className="st-snap h" style={{ top: y * S }} />
            ))}
          </div>
          <div className="sub" style={{ marginTop: 8, textAlign: "center" }}>
            Arraste para mover · alças para redimensionar · setas ajustam (Shift = fino) ·
            a linha tracejada é a área segura (fora dela a interface do TikTok/Reels cobre)
          </div>
        </div>

        <div className="st-side">
          <div className="card">
            <h3>Templates prontos</h3>
            <div className="st-tpls">
              {tplQ.data?.templates.map((t) => (
                <button key={t.id} onClick={() => aplicarTemplate(t)} title={t.description}>
                  {t.name}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>Fundo</h3>
            <select value={bg.type}
                    onChange={(e) => upd((d) => {
                      d.background = { ...d.background, type: e.target.value as never };
                    })}>
              <option value="color">Cor sólida</option>
              <option value="gradient">Degradê</option>
              <option value="blur">Vídeo desfocado</option>
              <option value="image">Imagem</option>
              <option value="video">Vídeo</option>
            </select>
            {bg.type === "color" || bg.type === "gradient" ? (
              <div className="row" style={{ marginTop: 8 }}>
                <input type="color" value={bg.color ?? "#101418"}
                       onChange={(e) => upd((d) => { d.background.color = e.target.value; })} />
                {bg.type === "gradient" ? (
                  <>
                    <input type="color" value={bg.color2 ?? "#000000"}
                           onChange={(e) => upd((d) => { d.background.color2 = e.target.value; })} />
                    <select value={bg.direction ?? "vertical"}
                            onChange={(e) => upd((d) => {
                              d.background.direction = e.target.value as never;
                            })}>
                      <option value="vertical">Vertical</option>
                      <option value="horizontal">Horizontal</option>
                      <option value="diagonal">Diagonal</option>
                    </select>
                  </>
                ) : null}
              </div>
            ) : null}
            {bg.type === "blur" ? (
              <>
                <label>Intensidade do desfoque ({bg.blur_sigma ?? 28})</label>
                <input type="range" min={8} max={60} value={bg.blur_sigma ?? 28}
                       onChange={(e) => upd((d) => {
                         d.background.blur_sigma = Number(e.target.value);
                       })} />
              </>
            ) : null}
            {bg.type === "image" || bg.type === "video" ? (
              <label style={{ marginTop: 8 }}>
                <input type="file" style={{ display: "none" }}
                       accept={bg.type === "image" ? "image/*" : "video/mp4,video/webm"}
                       onChange={async (e) => {
                         const f = e.target.files?.[0];
                         if (!f) return;
                         try {
                           const p = await uploadAsset(f);
                           upd((d) => { d.background.path = p; });
                         } catch (err) {
                           flash(`Upload falhou: ${(err as Error).message}`, 5000);
                         }
                       }} />
                <span className="chip" style={{ cursor: "pointer" }}>
                  {bg.path ? `Trocar arquivo (${fname(bg.path)})` : "Enviar arquivo…"}
                </span>
              </label>
            ) : null}
          </div>

          <div className="card">
            <h3>Camadas</h3>
            <div className="row wrap" style={{ marginBottom: 8 }}>
              <button onClick={addTexto}>+ Texto</button>
              <label style={{ margin: 0 }}>
                <input type="file" accept="image/*" style={{ display: "none" }}
                       onChange={(e) => e.target.files?.[0] && addImagem(e.target.files[0])} />
                <span className="chip" style={{ cursor: "pointer" }}>+ Imagem</span>
              </label>
              <button onClick={addForma}>+ Forma</button>
              <label style={{ margin: 0 }}>
                <input type="file" accept="video/mp4,video/webm" style={{ display: "none" }}
                       onChange={(e) => e.target.files?.[0] && addVideoDeco(e.target.files[0])} />
                <span className="chip" style={{ cursor: "pointer" }}>+ Vídeo</span>
              </label>
              <button onClick={addCaptions}>+ Legendas</button>
            </div>
            <div className="st-layers">
              {[...draft.layers].map((_, idx) => idx).reverse().map((i) => {
                const l = draft.layers[i];
                return (
                  <div key={l.id} className={`st-lrow${sel === i ? " on" : ""}`}
                       onClick={() => setSel(i)}>
                    <span className="st-lname">
                      {LAYER_LABEL[l.type]}
                      {l.type === "text" ? ` · “${(l.text ?? "").slice(0, 14)}”` : ""}
                    </span>
                    <button title="Subir na pilha" onClick={(e) => { e.stopPropagation(); moveLayer(i, 1); }}>↑</button>
                    <button title="Descer na pilha" onClick={(e) => { e.stopPropagation(); moveLayer(i, -1); }}>↓</button>
                    <button title={l.hidden ? "Mostrar" : "Ocultar"}
                            onClick={(e) => { e.stopPropagation(); updLayer(i, { hidden: !l.hidden }); }}>
                      {l.hidden ? "🚫" : "👁"}
                    </button>
                    <button title={l.locked ? "Destravar" : "Travar"}
                            onClick={(e) => { e.stopPropagation(); updLayer(i, { locked: !l.locked }); }}>
                      {l.locked ? "🔒" : "🔓"}
                    </button>
                    <button className="danger" title="Excluir"
                            disabled={l.type === "source"}
                            onClick={(e) => { e.stopPropagation(); removeLayer(i); }}>×</button>
                  </div>
                );
              })}
            </div>
          </div>

          {selLayer ? (
            <div className="card">
              <h3>{LAYER_LABEL[selLayer.type]} — propriedades</h3>
              <div className="row">
                {(["x", "y", "w"] as const).map((k) => (
                  <div key={k} style={{ flex: 1 }}>
                    <label>{k.toUpperCase()}</label>
                    <input type="number" value={Math.round(selLayer[k] ?? 0)}
                           onChange={(e) => updLayer(sel!, { [k]: Number(e.target.value) })} />
                  </div>
                ))}
                {selLayer.h !== undefined ? (
                  <div style={{ flex: 1 }}>
                    <label>H</label>
                    <input type="number" value={Math.round(selLayer.h)}
                           onChange={(e) => updLayer(sel!, { h: Number(e.target.value) })} />
                  </div>
                ) : null}
              </div>
              {selLayer.type === "source" ? (
                <>
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <label>Cantos arredondados ({selLayer.radius ?? 0}px)</label>
                      <input type="range" min={0} max={80} value={selLayer.radius ?? 0}
                             onChange={(e) => updLayer(sel!, { radius: Number(e.target.value) })} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label>Borda ({selLayer.border_w ?? 0}px)</label>
                      <input type="range" min={0} max={20} value={selLayer.border_w ?? 0}
                             onChange={(e) => updLayer(sel!, { border_w: Number(e.target.value) })} />
                    </div>
                  </div>
                  <div className="row">
                    <div>
                      <label>Cor da borda</label>
                      <input type="color" value={selLayer.border_color ?? "#FFFFFF"}
                             onChange={(e) => updLayer(sel!, { border_color: e.target.value })} />
                    </div>
                    <label className="ed-check" style={{ marginTop: 26 }}>
                      <input type="checkbox" checked={!!selLayer.shadow}
                             onChange={(e) => updLayer(sel!, { shadow: e.target.checked })} />
                      Sombra
                    </label>
                  </div>
                </>
              ) : null}
              {selLayer.type === "text" ? (
                <>
                  <label>Texto ({"{titulo}"} = título do corte)</label>
                  <input value={selLayer.text ?? ""}
                         onChange={(e) => updLayer(sel!, { text: e.target.value })} />
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <label>Fonte</label>
                      <select value={selLayer.font ?? "Montserrat"}
                              onChange={(e) => updLayer(sel!, { font: e.target.value })}>
                        <option>Montserrat</option>
                        <option>Inter</option>
                      </select>
                    </div>
                    <div style={{ width: 90 }}>
                      <label>Tamanho</label>
                      <input type="number" value={selLayer.size ?? 60}
                             onChange={(e) => updLayer(sel!, { size: Number(e.target.value) })} />
                    </div>
                    <div>
                      <label>Cor</label>
                      <input type="color" value={selLayer.color ?? "#FFFFFF"}
                             onChange={(e) => updLayer(sel!, { color: e.target.value })} />
                    </div>
                  </div>
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <label>Alinhamento</label>
                      <select value={selLayer.align ?? "center"}
                              onChange={(e) => updLayer(sel!, { align: e.target.value as never })}>
                        <option value="left">Esquerda</option>
                        <option value="center">Centro</option>
                        <option value="right">Direita</option>
                      </select>
                    </div>
                    <label className="ed-check" style={{ marginTop: 26 }}>
                      <input type="checkbox" checked={selLayer.bold ?? true}
                             onChange={(e) => updLayer(sel!, { bold: e.target.checked })} />
                      Negrito
                    </label>
                    <label className="ed-check" style={{ marginTop: 26 }}>
                      <input type="checkbox" checked={!!selLayer.bg}
                             onChange={(e) => updLayer(sel!, { bg: e.target.checked ? "#000000AA" : null })} />
                      Fundo no texto
                    </label>
                  </div>
                </>
              ) : null}
              {selLayer.type === "shape" ? (
                <div className="row">
                  <div>
                    <label>Cor</label>
                    <input type="color" value={(selLayer.fill ?? "#FF4757").slice(0, 7)}
                           onChange={(e) => updLayer(sel!, {
                             fill: e.target.value + ((selLayer.fill ?? "").slice(7) || ""),
                           })} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>Cantos ({selLayer.radius ?? 0}px)</label>
                    <input type="range" min={0} max={80} value={selLayer.radius ?? 0}
                           onChange={(e) => updLayer(sel!, { radius: Number(e.target.value) })} />
                  </div>
                </div>
              ) : null}
              {selLayer.type !== "captions" && selLayer.type !== "source" ? (
                <>
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <label>Opacidade ({Math.round((selLayer.opacity ?? 1) * 100)}%)</label>
                      <input type="range" min={0.1} max={1} step={0.05}
                             value={selLayer.opacity ?? 1}
                             onChange={(e) => updLayer(sel!, { opacity: Number(e.target.value) })} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label>Animação de entrada</label>
                      <select value={selLayer.anim ?? "none"}
                              onChange={(e) => updLayer(sel!, { anim: e.target.value })}>
                        {(selLayer.type === "text" ? TEXT_ANIMS : ANIMS).map((a) => (
                          <option key={a.id} value={a.id}>{a.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="row">
                    <div style={{ flex: 1 }}>
                      <label>Aparece em (s)</label>
                      <input type="number" min={0} step={0.5} value={selLayer.start_s ?? 0}
                             onChange={(e) => updLayer(sel!, { start_s: Number(e.target.value) })} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label>Some em (s; vazio = fim)</label>
                      <input type="number" min={0} step={0.5}
                             value={selLayer.end_s ?? ""}
                             placeholder="até o fim"
                             onChange={(e) => updLayer(sel!, {
                               end_s: e.target.value === "" ? null : Number(e.target.value),
                             })} />
                    </div>
                  </div>
                </>
              ) : null}
              {selLayer.type === "captions" ? (
                <div className="sub">
                  Esta caixa define ONDE os cartões de legenda aparecem (âncora e largura).
                  O estilo continua vindo do preset escolhido na revisão do corte.
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  );
}

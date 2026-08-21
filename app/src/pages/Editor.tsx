// Editor de Corte v3 — shell "canvas em cima, inspector ao lado, timeline embaixo"
// (Pontos 5, 32): o preview 9:16 é WYSIWYG (mesma composição do render), o
// inspector é contextual por ferramenta e a timeline é a fonte da verdade
// temporal, com relógio RELATIVO ao corte (00:00 → duração; Pontos 11–12).
// A edição continua 100% não destrutiva: tudo vira a MESMA EDL/edits que o
// motor usa na prévia real e no render final.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { get, mediaUrl, patch, post } from "../api/client";
import type {
  BrandKit, CaptionCards, CaptionPreset, Cut, Edl, Render, Source,
  TranscriptWord, Waveform,
} from "../api/types";
import Canvas from "../editor/Canvas";
import Inspector, { type Tool } from "../editor/Inspector";
import {
  PAD_S, draftFromCut, envelope, fmtT, outDur, outToSrc, patchFromDraft,
  srcToOut, type Draft,
} from "../editor/model";
import { rotuloDoEfeito } from "../editor/MotionPanel";
import type { TextPreset } from "../editor/motion";
import Splitter from "../editor/Splitter";
import { WORKSPACE_PRESETS, useWorkspace } from "../editor/workspace";

export default function EditorPage() {
  const { projectId = "", cutId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();

  const cutQ = useQuery({
    queryKey: ["cuts", "detail", cutId],
    queryFn: () => get<Cut>(`/api/v1/cuts/${cutId}`),
  });
  const cut = cutQ.data;
  // rota canônica: Voltar/Salvar e fechar retornam SEMPRE à análise deste corte
  const rotaCorte = `/projeto/${projectId || cut?.project_id || ""}/corte/${cutId}`;
  const srcQ = useQuery({
    enabled: !!cut,
    queryKey: ["sources", "detail", cut?.source_video_id],
    queryFn: () => get<Source>(`/api/v1/sources/${cut!.source_video_id}`),
  });
  const source = srcQ.data;
  const kitsQ = useQuery({
    queryKey: ["brand-kits"],
    queryFn: () => get<BrandKit[]>("/api/v1/brand-kits"),
  });
  const presetsQ = useQuery({
    queryKey: ["caption-presets"],
    queryFn: () => get<{ presets: CaptionPreset[] }>("/api/v1/captions/presets"),
    staleTime: Infinity,
  });
  const capsQ = useQuery({
    enabled: !!cut,
    queryKey: ["caption-cards", cutId],
    queryFn: () => get<CaptionCards>(`/api/v1/cuts/${cutId}/caption-cards`),
  });
  const motionQ = useQuery({
    queryKey: ["motion-presets"],
    queryFn: () => get<{ presets: TextPreset[] }>("/api/v1/motion/presets"),
    staleTime: Infinity,
  });

  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState("");
  const [history, setHistory] = useState<Draft[]>([]);
  const [future, setFuture] = useState<Draft[]>([]);
  const [win, setWin] = useState<{ a: number; b: number } | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [selFr, setSelFr] = useState<number | null>(null); // bloco de enquadramento
  const [tool, setTool] = useState<Tool>("corte");
  const [zoom, setZoom] = useState(18); // pixels por segundo
  const [playhead, setPlayhead] = useState(0); // tempo da FONTE (interno)
  const [playing, setPlaying] = useState(false);
  const [title, setTitle] = useState("");
  const [selCard, setSelCard] = useState<number | null>(null); // cartão de legenda
  const [selFx, setSelFx] = useState<string | null>(null); // efeito de motion
  const [safeArea, setSafeArea] = useState(false); // guias das plataformas
  const [toast, setToast] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoErro, setVideoErro] = useState(false);
  const [stripUrl, setStripUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // workspace redimensionável (v4 FASE A) — preferência da instalação, fora do Draft
  const { ws, mudar: wsMudar, aplicarPreset, resetInspector, resetTimeline } = useWorkspace();
  const wsBaseRef = useRef(0);
  function arrastaInspector(delta: number, fase: "start" | "move" | "end") {
    if (fase === "start") { wsBaseRef.current = ws.inspector_w; return; }
    wsMudar({ inspector_w: wsBaseRef.current - delta }); // p/ a esquerda = mais largo
  }
  function arrastaTimeline(delta: number, fase: "start" | "move" | "end") {
    if (fase === "start") { wsBaseRef.current = ws.timeline_h; return; }
    wsMudar({ timeline_h: wsBaseRef.current - delta }); // p/ cima = mais alto
  }

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<{ idx: number; side: "l" | "r"; base: Draft } | null>(null);
  const frDragRef = useRef<{ i: number; kind: "l" | "r" | "move"; base: Draft;
    grabDt: number } | null>(null);
  const lastTRef = useRef(0);

  function flash(msg: string, ms = 2800) {
    setToast(msg);
    window.setTimeout(() => setToast(""), ms);
  }

  // inicialização (uma vez, com corte + fonte carregados)
  useEffect(() => {
    if (!cut || !source || draft) return;
    const d = draftFromCut(cut);
    const [env0, env1] = envelope(d.segments);
    const dur = source.duration_s ?? env1 + PAD_S;
    setDraft(d);
    setSaved(JSON.stringify(d));
    setTitle(cut.title);
    setWin({ a: Math.max(0, env0 - PAD_S), b: Math.min(dur, env1 + PAD_S) });
    setPlayhead(env0);
  }, [cut, source, draft]);

  // zoom inicial: janela inteira visível
  useEffect(() => {
    if (!win || !scrollRef.current) return;
    const fit = Math.floor((scrollRef.current.clientWidth - 8) / (win.b - win.a));
    setZoom(Math.min(40, Math.max(6, fit)));
  }, [win]);

  useEffect(() => {
    if (!cut) return;
    mediaUrl(`/api/v1/media/sources/${cut.source_video_id}/file`).then(setVideoUrl);
  }, [cut?.source_video_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!cut || !win) return;
    mediaUrl(`/api/v1/media/cuts/${cut.id}/filmstrip?t0=${win.a.toFixed(2)}&t1=${win.b.toFixed(2)}&frames=16`)
      .then(setStripUrl);
  }, [cut?.id, win]); // eslint-disable-line react-hooks/exhaustive-deps

  const waveQ = useQuery({
    enabled: !!cut,
    queryKey: ["waveform", cutId],
    queryFn: () => get<Waveform>(`/api/v1/cuts/${cutId}/waveform?pps=40&pad_s=${PAD_S}`),
    staleTime: Infinity,
    retry: false,
  });
  const wordsQ = useQuery({
    enabled: !!cut,
    queryKey: ["cutwords", cutId],
    queryFn: () => get<{ words: TranscriptWord[] }>(`/api/v1/cuts/${cutId}/words?pad_s=${PAD_S}`),
    staleTime: Infinity,
  });

  // pontos de snap: início/fim de palavra, meio das pausas e segundos inteiros
  const snaps = useMemo(() => {
    const pts: number[] = [];
    const ws = wordsQ.data?.words ?? [];
    for (const w of ws) pts.push(w.start_s, w.end_s);
    for (let i = 1; i < ws.length; i++) {
      const gap = ws[i].start_s - ws[i - 1].end_s;
      if (gap > 0.35) pts.push(ws[i - 1].end_s + gap / 2);
    }
    if (win) for (let t = Math.ceil(win.a); t <= win.b; t++) pts.push(t);
    return pts.sort((x, y) => x - y);
  }, [wordsQ.data, win]);

  const snapTo = useCallback(
    (t: number) => {
      const tol = 8 / zoom;
      let best = t;
      let bd = tol;
      for (const p of snaps) {
        const d = Math.abs(p - t);
        if (d < bd) {
          bd = d;
          best = p;
        }
      }
      return Math.round(best * 100) / 100;
    },
    [snaps, zoom],
  );

  // waveform no canvas
  useEffect(() => {
    const cv = canvasRef.current;
    const wave = waveQ.data;
    if (!cv || !wave || !win) return;
    const w = Math.max(1, Math.round((win.b - win.a) * zoom));
    cv.width = w;
    cv.height = 44;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, 44);
    ctx.fillStyle = "#60a5fa99";
    wave.peaks.forEach((p, i) => {
      const t = wave.start_s + i / wave.pps;
      if (t < win.a || t > win.b) return;
      const h = Math.max(1, p * 42);
      ctx.fillRect((t - win.a) * zoom, (44 - h) / 2, Math.max(1, zoom / wave.pps), h);
    });
  }, [waveQ.data, zoom, win]);

  // reprodução com jump cuts: a MESMA lógica da EDL que o render aplica
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !draft) return;
    let raf = 0;
    const tick = () => {
      const t = v.currentTime;
      setPlayhead(t);
      if (!v.paused) {
        const segs = draft.segments;
        const env1 = segs[segs.length - 1].src_end;
        const inSeg = segs.some((s) => t >= s.src_start - 0.03 && t < s.src_end);
        if (!inSeg && t >= segs[0].src_start && t < env1) {
          const next = segs.find((s) => s.src_start > t - 0.03);
          if (next) v.currentTime = next.src_start;
        } else if (t >= env1 && lastTRef.current < env1) {
          v.pause();
          setPlaying(false);
        }
      }
      lastTRef.current = v.currentTime;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [draft]);

  // sincronismo texto ↔ tempo (Ponto 28): durante a reprodução, o cartão atual
  // acompanha o playhead — o editor de palavras sempre mostra o que se ouve
  useEffect(() => {
    if (!playing || !draft) return;
    const lista = capsQ.data?.cards ?? [];
    if (!lista.length) return;
    const t = srcToOut(draft.segments, playhead);
    const i = lista.findIndex((c) => t >= c.start && t <= c.end);
    if (i >= 0) setSelCard((atual) => (atual === i ? atual : i));
  }, [playhead, playing, capsQ.data, draft]);

  // mute/ganho refletidos no player (ganho >0 não amplifica no navegador —
  // a prévia real renderiza com o valor exato)
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !draft) return;
    v.muted = draft.audio.mute;
    v.volume = Math.min(1, Math.pow(10, Math.min(0, draft.audio.gain_db) / 20));
  }, [draft?.audio.mute, draft?.audio.gain_db]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = !!draft && (JSON.stringify(draft) !== saved || title !== (cut?.title ?? ""));

  const salvar = useMutation({
    mutationFn: async () => {
      const enviado = draft!;
      const novo = await patch<Cut>(`/api/v1/cuts/${cutId}`,
        patchFromDraft(enviado, title, cut?.edits ?? null));
      return { novo, enviado };
    },
    onSuccess: ({ novo, enviado }) => {
      // NÃO recria o draft: o usuário pode já estar editando por cima do
      // autosave — só registra o que foi persistido e atualiza o cache.
      qc.setQueryData(["cuts", "detail", cutId], novo);
      qc.invalidateQueries({ queryKey: ["cuts", novo.project_id] });
      qc.invalidateQueries({ queryKey: ["caption-cards", cutId] });
      setSaved(JSON.stringify(enviado));
    },
    onError: (e: Error) => flash(`Falha ao salvar: ${e.message}`, 5200),
  });

  // autosave: persiste sozinho ~1.2s após a última alteração (header: Salvando…/Salvo)
  useEffect(() => {
    if (!dirty || salvar.isPending) return;
    const t = window.setTimeout(() => salvar.mutate(), 1200);
    return () => window.clearTimeout(t);
  }, [dirty, draft, title, salvar.isPending]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- operações de edição (com histórico p/ desfazer) ----------
  function commit(next: Draft) {
    if (!draft) return;
    setHistory((h) => [...h, draft]);
    setFuture([]);
    setDraft(next);
  }
  const upd = (patchDraft: Partial<Draft>) => draft && commit({ ...draft, ...patchDraft });
  function undo() {
    if (!history.length || !draft) return;
    setFuture([draft, ...future]);
    setDraft(history[history.length - 1]);
    setHistory(history.slice(0, -1));
    setSel(null);
  }
  function redo() {
    if (!future.length || !draft) return;
    setHistory([...history, draft]);
    setDraft(future[0]);
    setFuture(future.slice(1));
    setSel(null);
  }

  function splitAt() {
    if (!draft) return;
    const t = Math.round(playhead * 100) / 100;
    const i = draft.segments.findIndex(
      (s) => t > s.src_start + 0.2 && t < s.src_end - 0.2,
    );
    if (i < 0) {
      flash("Posicione o cursor dentro de um trecho para dividir.");
      return;
    }
    const s = draft.segments[i];
    const segs = [...draft.segments];
    segs.splice(i, 1, { src_start: s.src_start, src_end: t }, { src_start: t, src_end: s.src_end });
    commit({ ...draft, segments: segs });
    setSel(i + 1);
    setTool("corte");
  }

  function removeSeg(i: number) {
    if (!draft) return;
    if (draft.segments.length <= 1) {
      flash("O corte precisa manter pelo menos um trecho.");
      return;
    }
    commit({ ...draft, segments: draft.segments.filter((_, j) => j !== i) });
    setSel(null);
  }

  function restoreGap(i: number) {
    // restaura o buraco entre o segmento i e o i+1, fundindo vizinhos contíguos
    if (!draft) return;
    const segs = [...draft.segments.map((s) => ({ ...s }))];
    segs.splice(i + 1, 0, { src_start: segs[i].src_end, src_end: segs[i + 1].src_start });
    const merged: typeof segs = [];
    for (const s of segs) {
      const last = merged[merged.length - 1];
      if (last && Math.abs(last.src_end - s.src_start) < 0.02) last.src_end = s.src_end;
      else merged.push({ ...s });
    }
    commit({ ...draft, segments: merged });
    setSel(null);
  }

  async function aplicarPausas(nivel: "leve" | "normal" | "agressivo") {
    if (!draft) return;
    try {
      const r = await post<{ edl: Edl; removidas: number; tempo_removido_s: number }>(
        `/api/v1/cuts/${cutId}/pauses-preview`, { nivel });
      const segsNovos = (r.edl.segments ?? []).map((s) => ({ ...s }));
      if (!segsNovos.length) return;
      commit({ ...draft, segments: segsNovos });
      setSel(null);
      flash(r.removidas
        ? `${r.removidas} pausa(s) removida(s) · −${r.tempo_removido_s.toFixed(1)}s. `
          + "Revise na timeline (Ctrl+Z desfaz)."
        : "Nenhuma pausa acima do limite deste nível.", 4500);
    } catch (e) {
      flash(`Não deu: ${(e as Error).message}`, 5000);
    }
  }

  // ---------- interação com a timeline ----------
  const timeAt = useCallback(
    (clientX: number) => {
      const rect = contentRef.current?.getBoundingClientRect();
      if (!rect || !win) return 0;
      return Math.min(win.b, Math.max(win.a, win.a + (clientX - rect.left) / zoom));
    },
    [win, zoom],
  );

  function seekSrc(t: number) {
    setPlayhead(t);
    if (videoRef.current) videoRef.current.currentTime = t;
  }

  function scrubStart(e: React.PointerEvent) {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    seekSrc(timeAt(e.clientX));
    const onMove = (ev: PointerEvent) => seekSrc(timeAt(ev.clientX));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function beginTrim(e: React.PointerEvent, idx: number, side: "l" | "r") {
    if (!draft) return;
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    dragRef.current = { idx, side, base: draft };
    setSel(idx);
    setTool("corte");
  }
  function onTrimMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d || !draft || !win) return;
    const t = snapTo(timeAt(e.clientX));
    const segs = draft.segments.map((s) => ({ ...s }));
    const s = segs[d.idx];
    if (d.side === "l") {
      const lo = d.idx > 0 ? segs[d.idx - 1].src_end : win.a;
      s.src_start = Math.min(Math.max(t, lo), s.src_end - 0.2);
    } else {
      const hi = d.idx < segs.length - 1 ? segs[d.idx + 1].src_start : win.b;
      s.src_end = Math.max(Math.min(t, hi), s.src_start + 0.2);
    }
    setDraft({ ...draft, segments: segs });
    seekSrc(d.side === "l" ? s.src_start : s.src_end);
  }
  function endTrim() {
    const d = dragRef.current;
    if (!d || !draft) return;
    dragRef.current = null;
    if (JSON.stringify(d.base) !== JSON.stringify(draft)) {
      setHistory((h) => [...h, d.base]);
      setFuture([]);
    }
  }

  // ---------- track de Enquadramento (Ponto 10): blocos na timeline ----------
  function frBegin(e: React.PointerEvent, i: number, kind: "l" | "r" | "move") {
    if (!draft) return;
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    frDragRef.current = { i, kind, base: draft,
      grabDt: timeAt(e.clientX) - draft.framing_segments[i].start_s };
    setSelFr(i);
    setSel(null);
    setTool("enquadramento"); // seleção contextual: bloco → ferramenta Enquadramento
  }
  function frMove(e: React.PointerEvent) {
    const d = frDragRef.current;
    if (!d || !draft || !win) return;
    const list = draft.framing_segments.map((s) => ({ ...s }));
    const s = list[d.i];
    if (d.kind === "l") {
      s.start_s = Math.min(snapTo(timeAt(e.clientX)), s.end_s - 0.2);
    } else if (d.kind === "r") {
      s.end_s = Math.max(snapTo(timeAt(e.clientX)), s.start_s + 0.2);
    } else {
      const w = s.end_s - s.start_s;
      const ns = snapTo(timeAt(e.clientX) - d.grabDt);
      s.start_s = Math.max(win.a, Math.min(ns, win.b - w));
      s.end_s = s.start_s + w;
    }
    setDraft({ ...draft, framing_segments: list });
  }
  function frEnd() {
    const d = frDragRef.current;
    if (!d || !draft) return;
    frDragRef.current = null;
    if (JSON.stringify(d.base) !== JSON.stringify(draft)) {
      setHistory((h) => [...h, d.base]);
      setFuture([]);
    }
  }
  function frSplit() {
    if (selFr == null || !draft) return;
    const s = draft.framing_segments[selFr];
    const t = Math.round(playhead * 100) / 100;
    if (!s || t <= s.start_s + 0.2 || t >= s.end_s - 0.2) {
      flash("Posicione o cursor dentro do bloco selecionado para dividir.");
      return;
    }
    const list = [...draft.framing_segments];
    list.splice(selFr, 1, { ...s, end_s: t }, { ...s, start_s: t });
    commit({ ...draft, framing_segments: list });
  }

  function togglePlay() {
    const v = videoRef.current;
    if (!v || !draft) return;
    if (v.paused) {
      const segs = draft.segments;
      const env1 = segs[segs.length - 1].src_end;
      if (playhead >= env1 - 0.05 || playhead < segs[0].src_start - PAD_S) {
        v.currentTime = segs[0].src_start;
      }
      v.play().then(() => setPlaying(true)).catch(() => setVideoErro(true));
    } else {
      v.pause();
      setPlaying(false);
    }
  }

  // atalhos de teclado
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "s" || e.key === "S") {
        splitAt();
      } else if ((e.key === "Delete" || e.key === "Backspace") && sel != null) {
        removeSeg(sel);
      } else if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      } else if (
        (e.ctrlKey || e.metaKey) &&
        (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))
      ) {
        e.preventDefault();
        redo();
      } else if (e.key === "+" || e.key === "=") {
        setZoom((z) => Math.min(60, z + 4)); // zoom da TIMELINE (o do canvas é à parte)
      } else if (e.key === "-" || e.key === "_") {
        setZoom((z) => Math.max(6, z - 4));
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  // ---------- prévia real (mesma EDL, mesmo pipeline do render final) ----------
  const rendersQ = useQuery({
    enabled: previewOpen,
    queryKey: ["renders", "cut", cutId],
    queryFn: () => get<Render[]>(`/api/v1/renders?cut_id=${cutId}`),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "queued" || r.status === "running")
        ? 1200
        : false,
  });
  useEffect(() => {
    if (!previewOpen) return;
    const pronto = (rendersQ.data ?? []).find(
      (r) => r.kind === "preview" && r.status === "done",
    );
    if (pronto) {
      mediaUrl(`/api/v1/media/cuts/${cutId}/preview`).then((u) =>
        setPreviewUrl(`${u}&v=${pronto.id}`));
    } else {
      setPreviewUrl(null);
    }
  }, [rendersQ.data, previewOpen, cutId]);

  async function gerarPrevia() {
    try {
      if (dirty) await salvar.mutateAsync();
      await post(`/api/v1/cuts/${cutId}/preview`);
      setPreviewOpen(true);
      qc.invalidateQueries({ queryKey: ["renders", "cut", cutId] });
    } catch (e) {
      flash(`Não foi possível gerar a prévia: ${(e as Error).message}`, 5200);
    }
  }

  async function salvarEFechar() {
    if (dirty) {
      try {
        await salvar.mutateAsync();
      } catch {
        return; // o toast do onError explica; não fecha perdendo trabalho
      }
    }
    nav(rotaCorte); // sempre de volta à análise do MESMO corte
  }

  async function voltar() {
    // Voltar também preserva alterações; só abandona a tela com aval explícito
    if (dirty) {
      try {
        await salvar.mutateAsync();
      } catch {
        const sair = window.confirm(
          "Não foi possível salvar as alterações. Sair mesmo assim e perdê-las?");
        if (!sair) return;
      }
    }
    nav(rotaCorte);
  }

  // ---------- derivados de exibição ----------
  if (cutQ.isError) return <div className="err">Corte não encontrado.</div>;
  if (!cut || !source || !draft || !win) {
    return <div className="empty">Carregando o Editor…</div>;
  }
  const winW = Math.round((win.b - win.a) * zoom);
  const segs = draft.segments;
  const [env0, env1] = envelope(segs);
  const outTotal = outDur(segs);
  const outNow = srcToOut(segs, playhead); // relógio de saída (sincronismo texto ↔ tempo)
  const cards = capsQ.data?.cards ?? [];
  const kit = (kitsQ.data ?? []).find((k) => k.id === draft.brand_kit_id) ?? null;
  // régua RELATIVA (Ponto 11): ticks em tempo de SAÍDA, posicionados na fonte
  const tickStep = zoom >= 40 ? 1 : zoom >= 16 ? 5 : 10;
  const outTicks: number[] = [];
  for (let t = 0; t < outTotal; t += tickStep) outTicks.push(t);
  const wordsVisiveis = (wordsQ.data?.words ?? []).filter((w) =>
    segs.some((s) => w.end_s > s.src_start && w.start_s < s.src_end));
  const x = (t: number) => (t - win.a) * zoom;
  const antesDisp = env0 - win.a;
  const depoisDisp = win.b - env1;

  return (
    <div className="editor ed3">
      <div className="pagehead">
        <div className="row" style={{ flex: 1, minWidth: 0 }}>
          <button onClick={voltar} data-testid="btn-back">← Voltar</button>
          <input
            className="ed-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Título do corte"
          />
        </div>
        <div className="row">
          <select
            className="ws-preset"
            title="Área de trabalho — arranjo dos painéis (só desta instalação)"
            data-testid="ws-preset"
            value={ws.preset in WORKSPACE_PRESETS ? ws.preset : "personalizado"}
            onChange={(e) => aplicarPreset(e.target.value)}
          >
            {Object.entries(WORKSPACE_PRESETS).map(([id, p]) => (
              <option key={id} value={id}>{p.label}</option>
            ))}
            {!(ws.preset in WORKSPACE_PRESETS) ? (
              <option value="personalizado" disabled>Personalizado</option>
            ) : null}
          </select>
          <span className={`ed-savestate${salvar.isPending ? " saving" : dirty ? " dirty" : ""}`}
                data-testid="save-state">
            {salvar.isPending ? "Salvando…" : dirty ? "Alterações pendentes…" : "Salvo"}
          </span>
          <button onClick={undo} disabled={!history.length} title="Ctrl+Z">↶</button>
          <button onClick={redo} disabled={!future.length} title="Ctrl+Shift+Z">↷</button>
          <button onClick={gerarPrevia}>Gerar prévia real</button>
          <button className="ok" onClick={salvarEFechar} data-testid="btn-save-close">
            Salvar e fechar
          </button>
        </div>
      </div>

      <div
        className="ed3-mid"
        data-testid="ed3-mid"
        style={{ gridTemplateColumns:
          `minmax(0, 1fr) 8px ${ws.inspector_collapsed ? 0 : ws.inspector_w}px` }}
      >
        <Canvas
          cut={cut}
          source={source}
          draft={draft}
          title={title}
          videoUrl={videoUrl}
          kit={kit}
          captions={capsQ.data ?? null}
          playhead={playhead}
          playing={playing}
          videoRef={videoRef}
          videoErro={videoErro}
          onVideoErro={() => setVideoErro(true)}
          onTogglePlay={togglePlay}
          onSeekOut={(tOut) => seekSrc(outToSrc(segs, tOut))}
          onSelectCaption={() => setTool("legenda")}
          capSelecionada={tool === "legenda"}
          safeArea={safeArea}
          onCaptionMove={(pos) => upd({ caption_style:
            { ...(draft.caption_style ?? {}), ...pos } })}
          zoom={ws.canvas_zoom}
          onZoom={(z) => wsMudar({ canvas_zoom: z })}
          motionPresets={motionQ.data?.presets ?? []}
        />
        <Splitter
          dir="v"
          testid="split-inspector"
          label="Largura do Inspector"
          collapsed={ws.inspector_collapsed}
          onDrag={arrastaInspector}
          onReset={resetInspector}
          onToggleCollapse={() => wsMudar({ inspector_collapsed: !ws.inspector_collapsed })}
        />
        <div className="card ed3-side"
             style={ws.inspector_collapsed ? { display: "none" } : undefined}>
          <Inspector
            tool={tool}
            setTool={setTool}
            cut={cut}
            draft={draft}
            upd={upd}
            title={title}
            kits={kitsQ.data ?? []}
            presets={presetsQ.data?.presets ?? []}
            words={wordsVisiveis}
            captions={capsQ.data ?? null}
            outNow={outNow}
            selCard={selCard}
            onSeekOut={(tOut) => seekSrc(outToSrc(segs, tOut))}
            sel={sel}
            selFr={selFr}
            motionPresets={motionQ.data?.presets ?? []}
            selFx={selFx}
            setSelFx={setSelFx}
            playhead={playhead}
            onPauses={aplicarPausas}
            onFrSplit={frSplit}
            safeArea={safeArea}
            setSafeArea={setSafeArea}
            onOpenStudio={(kid) => nav(`/estudio/${kid}`)}
          />
        </div>
      </div>

      <Splitter
        dir="h"
        testid="split-timeline"
        label="Altura da timeline"
        collapsed={ws.timeline_collapsed}
        onDrag={arrastaTimeline}
        onReset={resetTimeline}
        onToggleCollapse={() => wsMudar({ timeline_collapsed: !ws.timeline_collapsed })}
      />
      <div className="card ed-tl-card">
        <div className="row" style={{ marginBottom: ws.timeline_collapsed ? 0 : 10 }}>
          <button onClick={splitAt} title="Tecla S">✂ Dividir no cursor</button>
          <button
            className="danger"
            disabled={sel == null || segs.length <= 1}
            onClick={() => sel != null && removeSeg(sel)}
            title="Tecla Delete"
          >
            Excluir trecho
          </button>
          <span className="tc" data-testid="tl-clock">
            <b>{fmtT(srcToOut(segs, playhead))}</b> / {fmtT(outTotal)}
          </span>
          <span className="sub">
            {segs.length} trecho{segs.length > 1 ? "s" : ""} · arraste as bordas para
            aparar (snap em palavra/pausa/segundo) · sombras entre trechos = removido
            (clique para restaurar)
          </span>
          <button
            className="right"
            data-testid="tl-density"
            title="Altura das tracks da timeline"
            onClick={() => wsMudar({ tracks: ws.tracks === "compacta" ? "normal" : "compacta" })}
          >
            {ws.tracks === "compacta" ? "▤ Compactas" : "▦ Normais"}
          </button>
          <span className="sub">Zoom</span>
          <input
            type="range"
            min={6}
            max={60}
            value={zoom}
            style={{ width: 130 }}
            title="Zoom da timeline (+/−)"
            onChange={(e) => setZoom(Number(e.target.value))}
          />
        </div>
        <div className="tl-scroll" ref={scrollRef}
             style={ws.timeline_collapsed ? { display: "none" }
               : { height: ws.timeline_h }}
             data-testid="tl-scroll">
          <div className={`tl-content${ws.tracks === "compacta" ? " tl-compact" : ""}`}
               ref={contentRef} style={{ width: winW }}>
            <div className="tl-ruler" onPointerDown={scrubStart}>
              {/* relógio RELATIVO: 0:00 no início do corte, recalculado a cada trim */}
              {outTicks.map((t) => (
                <div key={t} className="tl-tick" style={{ left: x(outToSrc(segs, t)) }}>
                  <span>{fmtT(t).replace(/\.\d$/, "")}</span>
                </div>
              ))}
            </div>
            <div className="tl-strip" onPointerDown={scrubStart}>
              {stripUrl ? <img src={stripUrl} draggable={false} alt="" /> : null}
            </div>
            <canvas className="tl-wave" ref={canvasRef} onPointerDown={scrubStart} />
            <div className="tl-segrow" onPointerDown={scrubStart}>
              {segs.map((s, i) => (
                <div
                  key={i}
                  className={`tl-seg${sel === i ? " on" : ""}`}
                  style={{ left: x(s.src_start), width: (s.src_end - s.src_start) * zoom }}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    setSel(i);
                    setSelFr(null);
                    setTool("corte"); // seleção contextual: trecho → ferramenta Corte
                  }}
                >
                  <i className="h l" onPointerDown={(e) => beginTrim(e, i, "l")}
                     onPointerMove={onTrimMove} onPointerUp={endTrim}
                     title={i === 0 && antesDisp > 0.3
                       ? `${antesDisp.toFixed(1)}s disponíveis antes` : undefined} />
                  <span className="tl-seglabel">{(s.src_end - s.src_start).toFixed(1)}s</span>
                  <i className="h r" onPointerDown={(e) => beginTrim(e, i, "r")}
                     onPointerMove={onTrimMove} onPointerUp={endTrim}
                     title={i === segs.length - 1 && depoisDisp > 0.3
                       ? `${depoisDisp.toFixed(1)}s disponíveis depois` : undefined} />
                </div>
              ))}
            </div>
            {/* sombras: margens disponíveis fora do corte + buracos removidos */}
            <div className="tl-shade" style={{ left: 0, width: x(env0) }}>
              {antesDisp > 0.3 ? (
                <span className="tl-margem">{antesDisp.toFixed(1)}s antes</span>
              ) : null}
            </div>
            {segs.slice(0, -1).map((s, i) => (
              <div
                key={`g${i}`}
                className="tl-shade gap"
                title="Trecho removido — clique para restaurar"
                style={{ left: x(s.src_end), width: (segs[i + 1].src_start - s.src_end) * zoom }}
                onClick={() => restoreGap(i)}
              >
                <span>+</span>
              </div>
            ))}
            <div className="tl-shade" style={{ left: x(env1), width: Math.max(0, x(win.b) - x(env1)) }}>
              {depoisDisp > 0.3 ? (
                <span className="tl-margem">{depoisDisp.toFixed(1)}s depois</span>
              ) : null}
            </div>

            {/* track ENQUADRAMENTO (Ponto 10): mesma régua, mesmo playhead */}
            <div className="tl-track tl-track-fr">
              <span className="tl-tracklabel">Enquadr.</span>
              <div className="tl-frbase"
                   style={{ left: x(env0), width: Math.max(0, (env1 - env0) * zoom) }}
                   title="Modo do corte inteiro — os blocos azuis sobrescrevem por trecho"
                   onClick={() => { setTool("enquadramento"); setSelFr(null); }}>
                {({ auto: "Auto (falante ativo)", left: "Esquerda", right: "Direita",
                    center: "Centro", blur: "Desfocado", fit: "Fit", two: "Duas pessoas",
                    split: "Split" } as Record<string, string>)[draft.framing] ?? "Auto"}
              </div>
              {draft.framing_segments.map((s, i) => (
                <div key={i} data-testid={`fr-seg-${i}`}
                     className={`tl-frseg${selFr === i ? " on" : ""}`}
                     style={{ left: x(s.start_s), width: Math.max(8, (s.end_s - s.start_s) * zoom) }}
                     onPointerDown={(e) => frBegin(e, i, "move")}
                     onPointerMove={frMove} onPointerUp={frEnd}>
                  <i className="h l" onPointerDown={(e) => frBegin(e, i, "l")}
                     onPointerMove={frMove} onPointerUp={frEnd} />
                  {({ left: "Esquerda", center: "Centro", right: "Direita" } as
                    Record<string, string>)[s.mode] ?? s.mode}
                  <i className="h r" onPointerDown={(e) => frBegin(e, i, "r")}
                     onPointerMove={frMove} onPointerUp={frEnd} />
                </div>
              ))}
            </div>

            {/* track LEGENDAS (Pontos 27–28): cartões como objetos temporais reais.
                Clicar leva o playhead ao cartão e abre o editor de palavras nele. */}
            <div className="tl-track tl-track-cap">
              <span className="tl-tracklabel">Legendas</span>
              {cards.map((c, i) => {
                const a = outToSrc(segs, c.start);
                const b = outToSrc(segs, Math.max(c.start + 0.05, c.end));
                const ativo = outNow >= c.start && outNow <= c.end;
                return (
                  <div key={i} data-testid={`cap-card-${i}`}
                       className={`tl-capcard${selCard === i ? " on" : ""}${ativo ? " cur" : ""}`}
                       style={{ left: x(a), width: Math.max(6, (b - a) * zoom) }}
                       title={c.words.map((w) => w.word).join(" ")}
                       onClick={(e) => {
                         e.stopPropagation();
                         setSelCard(i);
                         setTool("palavras"); // seleção contextual: cartão → Palavras
                         seekSrc(outToSrc(segs, c.start + 0.01));
                       }}>
                    {c.words.map((w) => w.word).join(" ")}
                  </div>
                );
              })}
            </div>

            {/* track PUNCH-IN (Ponto 30): onde o zoom acontece, no mesmo relógio */}
            <div className="tl-track tl-track-pi" data-testid="pi-track"
                 onClick={() => setTool("punchin")}
                 title="Punch-in — clique para ajustar">
              <span className="tl-tracklabel">Punch-in</span>
              {draft.punch_in === "leve" ? (
                <div className="tl-pi-span"
                     style={{ left: x(env0), width: Math.max(0, (env1 - env0) * zoom) }}>
                  zoom 105%
                </div>
              ) : null}
              {draft.punch_in === "dinamico"
                ? segs.filter((_, i) => i % 2 === 1).map((s, i) => (
                    <div key={i} className="tl-pi-span"
                         style={{ left: x(s.src_start),
                                  width: Math.max(8, (s.src_end - s.src_start) * zoom) }}>
                      110%
                    </div>
                  ))
                : null}
            </div>

            {/* track MOTION (v4): cada efeito é um bloco NOMEADO e clicável —
                "Punch — Forte", nunca fx_273 (Entregas 18, 143) */}
            <div className="tl-track tl-track-mo" data-testid="mo-track">
              <span className="tl-tracklabel">Motion</span>
              {(draft.motion?.effects ?? []).map((e) => {
                const a = outToSrc(segs, e.start);
                const b = outToSrc(segs, Math.max(e.start + 0.05, e.end));
                return (
                  <div key={e.id} data-testid={`mo-block-${e.id}`}
                       className={`tl-moblock${selFx === e.id ? " on" : ""}${e.enabled === false ? " off" : ""}`}
                       style={{ left: x(a), width: Math.max(10, (b - a) * zoom) }}
                       title={`${rotuloDoEfeito(e, motionQ.data?.presets ?? [])} · clique para editar`}
                       onClick={(ev) => {
                         ev.stopPropagation();
                         setSelFx(e.id);
                         setTool("motion"); // seleção contextual: bloco → Motion
                         const i = cards.findIndex((c) => e.start >= c.start - 0.01
                           && e.start <= c.end + 0.01);
                         if (i >= 0) setSelCard(i); // bloco → texto alvo (Entrega 91)
                         seekSrc(outToSrc(segs, e.start + 0.01));
                       }}>
                    ✦ {rotuloDoEfeito(e, motionQ.data?.presets ?? [])}
                  </div>
                );
              })}
            </div>

            <div className="tl-playhead" style={{ left: x(playhead) }} />
          </div>
        </div>
      </div>

      {toast ? <div className="toast">{toast}</div> : null}

      {previewOpen ? (
        <div className="modal-backdrop" onClick={() => setPreviewOpen(false)}>
          <div className="modal" style={{ width: "min(460px, 94vw)" }}
               onClick={(e) => e.stopPropagation()}>
            <h2>Prévia real do corte</h2>
            {previewUrl ? (
              <video src={previewUrl} controls autoPlay
                     style={{ width: "100%", aspectRatio: "9/16", background: "#000",
                              borderRadius: 10 }} />
            ) : (
              <div className="ed-loading" style={{ aspectRatio: "9/16" }}>
                {(() => {
                  const ativo = (rendersQ.data ?? []).find(
                    (r) => r.kind === "preview" &&
                      (r.status === "queued" || r.status === "running"));
                  if (ativo) return `Renderizando… ${Math.round(ativo.progress * 100)}%`;
                  const falha = (rendersQ.data ?? []).find(
                    (r) => r.kind === "preview" && r.status === "failed");
                  return falha ? `Falhou: ${falha.error ?? "erro desconhecido"}`
                    : "Preparando prévia…";
                })()}
              </div>
            )}
            <div className="sub" style={{ marginTop: 10 }}>
              Renderizada pelo mesmo pipeline do arquivo final — só muda a resolução.
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="right" onClick={() => setPreviewOpen(false)}>Fechar</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// Editor de Corte (F1): edição NÃO destrutiva sobre o vídeo original.
// A timeline mostra a janela do corte com contexto ao redor; os trechos mantidos
// são blocos com alças de trim (com snap em palavra/pausa/segundo), e os
// removidos ficam sombreados — clique neles para restaurar. A reprodução pula
// os trechos removidos, exatamente como o render fará com a MESMA EDL.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { get, mediaUrl, patch, post } from "../api/client";
import type {
  Cut, Edl, EdlSegment, Render, Source, TranscriptWord, Waveform,
} from "../api/types";

interface Draft {
  segments: EdlSegment[];
  fade_in_s: number;
  fade_out_s: number;
  transition_s: number;
  audio: { gain_db: number; mute: boolean; fade_in_s: number; fade_out_s: number };
}

const PAD_S = 15; // contexto exibido antes/depois do corte na timeline

function draftFromCut(cut: Cut): Draft {
  const e: Edl | null = cut.edl;
  return {
    segments: e?.segments?.length
      ? e.segments.map((s) => ({ ...s }))
      : [{ src_start: cut.start_s, src_end: cut.end_s }],
    fade_in_s: e?.fade_in_s ?? 0,
    fade_out_s: e?.fade_out_s ?? 0,
    transition_s: e?.transition_s ?? 0,
    audio: {
      gain_db: e?.audio?.gain_db ?? 0,
      mute: e?.audio?.mute ?? false,
      fade_in_s: e?.audio?.fade_in_s ?? 0,
      fade_out_s: e?.audio?.fade_out_s ?? 0,
    },
  };
}

const outDur = (d: Draft) =>
  d.segments.reduce((acc, s) => acc + (s.src_end - s.src_start), 0);

function fmtT(t: number): string {
  const m = Math.floor(Math.max(0, t) / 60);
  const s = Math.max(0, t) - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export default function EditorPage() {
  const { cutId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();

  const cutQ = useQuery({
    queryKey: ["cuts", "detail", cutId],
    queryFn: () => get<Cut>(`/api/v1/cuts/${cutId}`),
  });
  const cut = cutQ.data;
  const srcQ = useQuery({
    enabled: !!cut,
    queryKey: ["sources", "detail", cut?.source_video_id],
    queryFn: () => get<Source>(`/api/v1/sources/${cut!.source_video_id}`),
  });
  const source = srcQ.data;

  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState("");
  const [history, setHistory] = useState<Draft[]>([]);
  const [future, setFuture] = useState<Draft[]>([]);
  const [win, setWin] = useState<{ a: number; b: number } | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [zoom, setZoom] = useState(18); // pixels por segundo
  const [playhead, setPlayhead] = useState(0); // tempo da FONTE
  const [playing, setPlaying] = useState(false);
  const [title, setTitle] = useState("");
  const [wordOv, setWordOv] = useState<Record<string, string>>({});
  const [frSegs, setFrSegs] = useState<{ start_s: number; end_s: number; mode: string }[]>([]);
  const [editWord, setEditWord] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoErro, setVideoErro] = useState(false);
  const [stripUrl, setStripUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<{ idx: number; side: "l" | "r"; base: Draft } | null>(null);
  const lastTRef = useRef(0);

  function flash(msg: string, ms = 2800) {
    setToast(msg);
    window.setTimeout(() => setToast(""), ms);
  }

  // inicialização (uma vez, com corte + fonte carregados)
  useEffect(() => {
    if (!cut || !source || draft) return;
    const d = draftFromCut(cut);
    const env0 = Math.min(...d.segments.map((s) => s.src_start));
    const env1 = Math.max(...d.segments.map((s) => s.src_end));
    const dur = source.duration_s ?? env1 + PAD_S;
    setDraft(d);
    setSaved(JSON.stringify(d));
    setTitle(cut.title);
    setWordOv((cut.edits?.word_overrides as Record<string, string>) ?? {});
    setFrSegs(((cut.edits?.framing_segments as never[]) ?? []).map((s) => ({ ...(s as object) })) as never);
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

  // mute/ganho refletidos no player (ganho >0 não é amplificável no navegador —
  // a prévia real renderiza com o valor exato)
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !draft) return;
    v.muted = draft.audio.mute;
    v.volume = Math.min(1, Math.pow(10, Math.min(0, draft.audio.gain_db) / 20));
  }, [draft?.audio.mute, draft?.audio.gain_db]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty =
    !!draft &&
    (JSON.stringify(draft) !== saved ||
      title !== (cut?.title ?? "") ||
      JSON.stringify(wordOv) !==
        JSON.stringify((cut?.edits?.word_overrides as Record<string, string>) ?? {}) ||
      JSON.stringify(frSegs) !==
        JSON.stringify((cut?.edits?.framing_segments as never[]) ?? []));

  const salvar = useMutation({
    mutationFn: async () => {
      const edits = { ...(cut?.edits ?? {}) } as Record<string, unknown>;
      if (Object.keys(wordOv).length) edits.word_overrides = wordOv;
      else delete edits.word_overrides;
      const frOk = frSegs.filter((s) => s.end_s > s.start_s);
      if (frOk.length) edits.framing_segments = frOk;
      else delete edits.framing_segments;
      return patch<Cut>(`/api/v1/cuts/${cutId}`, {
        edl: draft,
        title,
        edits: Object.keys(edits).length ? edits : null,
      });
    },
    onSuccess: (novo) => {
      qc.setQueryData(["cuts", "detail", cutId], novo);
      qc.invalidateQueries({ queryKey: ["cuts"] });
      const d = draftFromCut(novo);
      setDraft(d);
      setSaved(JSON.stringify(d));
      setTitle(novo.title);
      flash("Edição salva — a prévia e o render usarão exatamente esta versão.");
    },
    onError: (e: Error) => flash(`Falha ao salvar: ${e.message}`, 5200),
  });

  // ---------- operações de edição (com histórico p/ desfazer) ----------
  function commit(next: Draft) {
    if (!draft) return;
    setHistory((h) => [...h, draft]);
    setFuture([]);
    setDraft(next);
  }
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
    const merged: EdlSegment[] = [];
    for (const s of segs) {
      const last = merged[merged.length - 1];
      if (last && Math.abs(last.src_end - s.src_start) < 0.02) last.src_end = s.src_end;
      else merged.push({ ...s });
    }
    commit({ ...draft, segments: merged });
    setSel(null);
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

  function scrubStart(e: React.PointerEvent) {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const move = (t: number) => {
      setPlayhead(t);
      if (videoRef.current) videoRef.current.currentTime = t;
    };
    move(timeAt(e.clientX));
    const onMove = (ev: PointerEvent) => move(timeAt(ev.clientX));
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
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = { idx, side, base: draft };
    setSel(idx);
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
    setPlayhead(d.side === "l" ? s.src_start : s.src_end);
    if (videoRef.current) videoRef.current.currentTime = d.side === "l" ? s.src_start : s.src_end;
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
    nav(`/projeto/${cut?.project_id ?? ""}`);
  }

  // ---------- derivados de exibição ----------
  if (cutQ.isError) return <div className="err">Corte não encontrado.</div>;
  if (!cut || !source || !draft || !win) {
    return <div className="empty">Carregando o Editor…</div>;
  }
  const winW = Math.round((win.b - win.a) * zoom);
  const segs = draft.segments;
  const env0 = segs[0].src_start;
  const env1 = segs[segs.length - 1].src_end;
  const outNow = (() => {
    let acc = 0;
    for (const s of segs) {
      if (playhead < s.src_start) break;
      if (playhead < s.src_end) return acc + (playhead - s.src_start);
      acc += s.src_end - s.src_start;
    }
    return acc;
  })();
  const tickStep = zoom >= 40 ? 1 : zoom >= 16 ? 5 : 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(win.a / tickStep) * tickStep; t <= win.b; t += tickStep) ticks.push(t);
  const wordsVisiveis = (wordsQ.data?.words ?? []).filter((w) =>
    segs.some((s) => w.end_s > s.src_start && w.start_s < s.src_end));
  const x = (t: number) => (t - win.a) * zoom;

  return (
    <div className="editor">
      <div className="pagehead">
        <div className="row" style={{ flex: 1, minWidth: 0 }}>
          <button onClick={() => nav(`/projeto/${cut.project_id}`)}>← Voltar</button>
          <input
            className="ed-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Título do corte"
          />
        </div>
        <div className="row">
          <button onClick={undo} disabled={!history.length} title="Ctrl+Z">↶ Desfazer</button>
          <button onClick={redo} disabled={!future.length} title="Ctrl+Shift+Z">↷ Refazer</button>
          <button onClick={gerarPrevia}>Gerar prévia real</button>
          <button className="primary" disabled={!dirty || salvar.isPending}
                  onClick={() => salvar.mutate()}>
            {salvar.isPending ? "Salvando…" : dirty ? "Salvar" : "Salvo"}
          </button>
          <button className="ok" onClick={salvarEFechar}>Salvar e fechar</button>
        </div>
      </div>

      <div className="ed-main">
        <div className="card ed-player">
          {videoUrl ? (
            <div style={{ position: "relative" }}>
              <video
                ref={videoRef}
                src={videoUrl}
                onClick={togglePlay}
                onError={() => setVideoErro(true)}
                onLoadedMetadata={(e) => {
                  setVideoErro(false);
                  e.currentTarget.currentTime = env0;
                }}
              />
              {videoErro ? (
                <div className="ed-loading" style={{ position: "absolute", inset: 0 }}>
                  O player não consegue decodificar este formato de vídeo.
                  A edição na timeline funciona normalmente — use “Gerar prévia real”
                  para assistir ao resultado.
                </div>
              ) : null}
            </div>
          ) : (
            <div className="ed-loading">Abrindo vídeo original…</div>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={togglePlay}>
              {playing ? "⏸ Pausar" : "▶ Reproduzir"}
            </button>
            <span className="tc">
              saída <b>{fmtT(outNow)}</b> / {fmtT(outDur(draft))}
            </span>
            <span className="sub right">fonte {fmtT(playhead)}</span>
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            A reprodução pula os trechos removidos — o render final segue a mesma edição.
          </div>
        </div>

        <div className="card ed-side">
          <h3>Corte</h3>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Fade de entrada (s)</label>
              <input type="number" min={0} max={3} step={0.1} value={draft.fade_in_s}
                     onChange={(e) => commit({ ...draft, fade_in_s: Math.max(0, Number(e.target.value) || 0) })} />
            </div>
            <div style={{ flex: 1 }}>
              <label>Fade de saída (s)</label>
              <input type="number" min={0} max={3} step={0.1} value={draft.fade_out_s}
                     onChange={(e) => commit({ ...draft, fade_out_s: Math.max(0, Number(e.target.value) || 0) })} />
            </div>
          </div>
          <label>Transição nas junções (onde um trecho emenda no outro)</label>
          <select value={String(draft.transition_s)}
                  onChange={(e) => commit({ ...draft, transition_s: Number(e.target.value) })}>
            <option value="0">Corte seco (sem transição)</option>
            <option value="0.12">Suave — 0,12s</option>
            <option value="0.25">Média — 0,25s</option>
            <option value="0.5">Longa — 0,5s</option>
          </select>

          <h3 style={{ marginTop: 18 }}>Remover pausas</h3>
          <div className="sub" style={{ marginBottom: 6 }}>
            Corta silêncios automaticamente (jump cuts visíveis na timeline). Pausas
            dramáticas após “!” ou “?” são preservadas — só o Agressivo corta tudo.
            Nada é aplicado até você salvar; Ctrl+Z desfaz.
          </div>
          <div className="row wrap">
            {(["leve", "normal", "agressivo"] as const).map((n) => (
              <button key={n} onClick={async () => {
                try {
                  const r = await post<{ edl: Edl; removidas: number;
                    tempo_removido_s: number }>(
                    `/api/v1/cuts/${cutId}/pauses-preview`, { nivel: n });
                  const segsNovos = (r.edl.segments ?? []).map((s) => ({ ...s }));
                  if (!segsNovos.length) return;
                  commit({ ...draft, segments: segsNovos });
                  setSel(null);
                  flash(r.removidas
                    ? `${r.removidas} pausa(s) removida(s) · −${r.tempo_removido_s.toFixed(1)}s. `
                      + "Revise na timeline e salve (Ctrl+Z desfaz)."
                    : "Nenhuma pausa acima do limite deste nível.", 4500);
                } catch (e) {
                  flash(`Não deu: ${(e as Error).message}`, 5000);
                }
              }}>
                {n === "leve" ? "Leve" : n === "normal" ? "Normal" : "Agressivo"}
              </button>
            ))}
          </div>

          <h3 style={{ marginTop: 18 }}>Áudio</h3>
          <label>Volume do corte: {draft.audio.gain_db > 0 ? "+" : ""}{draft.audio.gain_db.toFixed(1)} dB</label>
          <input type="range" min={-20} max={10} step={0.5} value={draft.audio.gain_db}
                 onChange={(e) => commit({ ...draft, audio: { ...draft.audio, gain_db: Number(e.target.value) } })} />
          <label className="ed-check">
            <input type="checkbox" checked={draft.audio.mute}
                   onChange={(e) => commit({ ...draft, audio: { ...draft.audio, mute: e.target.checked } })} />
            Sem áudio (mudo)
          </label>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Fade de áudio — entrada (s)</label>
              <input type="number" min={0} max={3} step={0.1} value={draft.audio.fade_in_s}
                     onChange={(e) => commit({ ...draft, audio: { ...draft.audio, fade_in_s: Math.max(0, Number(e.target.value) || 0) } })} />
            </div>
            <div style={{ flex: 1 }}>
              <label>Fade de áudio — saída (s)</label>
              <input type="number" min={0} max={3} step={0.1} value={draft.audio.fade_out_s}
                     onChange={(e) => commit({ ...draft, audio: { ...draft.audio, fade_out_s: Math.max(0, Number(e.target.value) || 0) } })} />
            </div>
          </div>

          <h3 style={{ marginTop: 18 }}>Enquadramento por trecho</h3>
          <div className="sub" style={{ marginBottom: 6 }}>
            Force o foco num intervalo específico (tempos do vídeo original) — o resto
            do corte continua automático. Ex.: 18–24s → foco à esquerda.
          </div>
          {frSegs.map((s, i) => (
            <div key={i} className="row" style={{ marginBottom: 6 }}>
              <input type="number" min={0} step={0.5} value={s.start_s}
                     style={{ width: 74 }}
                     onChange={(e) => setFrSegs(frSegs.map((x, j) =>
                       j === i ? { ...x, start_s: Number(e.target.value) } : x))} />
              <span className="sub">→</span>
              <input type="number" min={0} step={0.5} value={s.end_s}
                     style={{ width: 74 }}
                     onChange={(e) => setFrSegs(frSegs.map((x, j) =>
                       j === i ? { ...x, end_s: Number(e.target.value) } : x))} />
              <select value={s.mode} style={{ flex: 1 }}
                      onChange={(e) => setFrSegs(frSegs.map((x, j) =>
                        j === i ? { ...x, mode: e.target.value } : x))}>
                <option value="left">Foco à esquerda</option>
                <option value="center">Foco no centro</option>
                <option value="right">Foco à direita</option>
              </select>
              <button className="danger" onClick={() =>
                setFrSegs(frSegs.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <button onClick={() => {
            const a = sel != null ? segs[sel].src_start : Math.max(env0, playhead - 3);
            const b = sel != null ? segs[sel].src_end : Math.min(env1, playhead + 3);
            setFrSegs([...frSegs, { start_s: Math.round(a * 10) / 10,
                                    end_s: Math.round(b * 10) / 10, mode: "left" }]);
          }}>
            + Adicionar {sel != null ? "no trecho selecionado" : "ao redor do cursor"}
          </button>

          <h3 style={{ marginTop: 18 }}>Palavras da legenda</h3>
          <div className="sub" style={{ marginBottom: 8 }}>
            Clique numa palavra para corrigir o texto — só neste corte; a transcrição
            original não muda.
          </div>
          <div className="ed-words">
            {wordsVisiveis.length === 0 ? (
              <span className="sub">Sem palavras no trecho mantido.</span>
            ) : (
              wordsVisiveis.map((w) =>
                editWord === w.idx ? (
                  <input
                    key={w.idx}
                    className="ed-word-input"
                    autoFocus
                    defaultValue={wordOv[String(w.idx)] ?? w.word}
                    onBlur={(e) => {
                      const novo = e.target.value.trim();
                      const m = { ...wordOv };
                      if (!novo || novo === w.word) delete m[String(w.idx)];
                      else m[String(w.idx)] = novo;
                      setWordOv(m);
                      setEditWord(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                      if (e.key === "Escape") setEditWord(null);
                    }}
                  />
                ) : (
                  <button
                    key={w.idx}
                    className={`ed-word${wordOv[String(w.idx)] ? " fixed" : ""}`}
                    title={wordOv[String(w.idx)] ? `Original: “${w.word}”` : "Clique para corrigir"}
                    onClick={() => setEditWord(w.idx)}
                  >
                    {wordOv[String(w.idx)] ?? w.word}
                  </button>
                ),
              )
            )}
          </div>
        </div>
      </div>

      <div className="card ed-tl-card">
        <div className="row" style={{ marginBottom: 10 }}>
          <button onClick={splitAt} title="Tecla S">✂ Dividir no cursor</button>
          <button
            className="danger"
            disabled={sel == null || segs.length <= 1}
            onClick={() => sel != null && removeSeg(sel)}
            title="Tecla Delete"
          >
            Excluir trecho
          </button>
          <span className="sub">
            {segs.length} trecho{segs.length > 1 ? "s" : ""} · saída {fmtT(outDur(draft))} ·
            arraste as bordas para aparar (snap em palavras e pausas) · clique numa área
            sombreada entre trechos para restaurá-la
          </span>
          <span className="right sub">Zoom</span>
          <input
            type="range"
            min={6}
            max={60}
            value={zoom}
            style={{ width: 130 }}
            onChange={(e) => setZoom(Number(e.target.value))}
          />
        </div>
        <div className="tl-scroll" ref={scrollRef}>
          <div className="tl-content" ref={contentRef} style={{ width: winW }}>
            <div className="tl-ruler" onPointerDown={scrubStart}>
              {ticks.map((t) => (
                <div key={t} className="tl-tick" style={{ left: x(t) }}>
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
                  }}
                >
                  <i className="h l" onPointerDown={(e) => beginTrim(e, i, "l")}
                     onPointerMove={onTrimMove} onPointerUp={endTrim} />
                  <span className="tl-seglabel">{(s.src_end - s.src_start).toFixed(1)}s</span>
                  <i className="h r" onPointerDown={(e) => beginTrim(e, i, "r")}
                     onPointerMove={onTrimMove} onPointerUp={endTrim} />
                </div>
              ))}
            </div>
            {/* sombras: contexto fora do corte + buracos removidos (clicáveis) */}
            <div className="tl-shade" style={{ left: 0, width: x(env0) }} />
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
            <div className="tl-shade" style={{ left: x(env1), width: Math.max(0, x(win.b) - x(env1)) }} />
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

"""Auto Reframe 16:9 → 9:16.

Pipeline por corte (decodificação SEQUENCIAL — sem seeks):
  1. frames a ~10 fps; detecção facial (YuNet → fallback Haar) a ~2 fps em frame reduzido;
  2. rastreamento online por posição x (tracks ≈ pessoas em um podcast);
  3. movimento de boca por track a 10 fps (diferença temporal do patch da boca);
  4. atribuição do falante com HISTERESE: só troca quando o outro rosto supera o atual
     por margem, em janelas consecutivas — evita focar quem não está falando;
  5. segmentos de crop com mínimo de 2s (jump cut entre falantes).
Sem rosto suficiente → blur_pad. O usuário pode forçar o enquadramento por corte
(auto|left|right|center|blur) via `apply_framing_override`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
from sqlalchemy import select

from .. import config
from ..db.base import session
from ..db.models import CutCandidate, SourceVideo

log = logging.getLogger(__name__)

SAMPLE_FPS = 10.0          # análise de boca (sequencial, barata)
DETECT_EVERY = 5           # detecção facial a cada N amostras (~2 fps)
DETECT_WIDTH = 960         # detecta em frame reduzido (caixas re-escaladas)
SCENE_DIST_THRESHOLD = 0.5
WINDOW_S = 1.0             # granularidade da atribuição
MIN_SEGMENT_S = 2.0        # segmentos menores são fundidos (menos flicker)
MOVEMENT_MIN = 4.0         # movimento médio de boca mínimo p/ confiar no sinal
SWITCH_RATIO = 1.35        # p/ trocar, o desafiante precisa superar o atual em 35%
SWITCH_WINDOWS = 2         # ...por N janelas consecutivas (histerese)
TRACK_TIMEOUT_S = 2.5      # track sem detecção recente não gera sinal de boca
MAX_TRACKS = 4
MIN_TRACK_PRESENCE = 0.10  # tracks vistos em <10% das detecções são espúrios
FACE_HIT_RATE_MIN = 0.6
FRAMING_MODES = ("auto", "left", "right", "center", "blur")


class FaceDetector:
    """YuNet (FaceDetectorYN) quando o ONNX está disponível; senão Haar cascade do OpenCV."""

    def __init__(self, yunet_path: str | None = None):
        import os

        import cv2

        from ..services import model_assets

        self._cv2 = cv2
        self.kind = "haar"
        self._yunet = None
        self._yunet_size = None
        candidates = [yunet_path,
                      str(config.models_dir() / "yunet.onnx"),
                      str(config.ASSETS_DIR / "yunet.onnx")]
        if not any(p and os.path.exists(p) for p in candidates):
            downloaded = model_assets.ensure_yunet()  # best-effort no 1º uso
            if downloaded:
                candidates.insert(0, downloaded)
        for path in candidates:
            if path and os.path.exists(path) and hasattr(cv2, "FaceDetectorYN"):
                try:
                    self._yunet = cv2.FaceDetectorYN.create(path, "", (320, 320), 0.7)
                    self.kind = "yunet"
                    break
                except Exception:  # modelo corrompido → segue para o fallback
                    self._yunet = None
        if self._yunet is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._cascade = cv2.CascadeClassifier(cascade_path)

    def detect(self, frame_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        cv2 = self._cv2
        h, w = frame_bgr.shape[:2]
        if self.kind == "yunet":
            if self._yunet_size != (w, h):
                self._yunet.setInputSize((w, h))
                self._yunet_size = (w, h)
            _, faces = self._yunet.detect(frame_bgr)
            if faces is None:
                return []
            return [(int(f[0]), int(f[1]), int(f[2]), int(f[3])) for f in faces]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                               minSize=(max(24, h // 20), max(24, h // 20)))
        return [tuple(int(v) for v in f) for f in faces]


def sample_frames(video_path: str, start: float, end: float, fps: float = SAMPLE_FPS):
    """Gera (t, frame) por decodificação sequencial: 1 seek inicial + grab/retrieve."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if src_fps <= 0 or src_fps > 240:
            src_fps = 30.0
        step = max(1, round(src_fps / fps))
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000.0)
        idx = 0
        while True:
            if not cap.grab():
                return
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t >= end:
                return
            if idx % step == 0 and t >= start:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    yield t, frame
            idx += 1
    finally:
        cap.release()


def _hist(frame) -> np.ndarray:
    import cv2

    hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h


def _hist_dist(h1, h2) -> float:
    import cv2

    return 1.0 - float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))


def _mouth_patch(frame, face: tuple[int, int, int, int]) -> np.ndarray:
    """Região da boca (terço inferior do rosto), 24×16 em cinza, para medir movimento."""
    import cv2

    x, y, w, h = face
    y0 = y + int(h * 0.62)
    patch = frame[max(0, y0):y + h, max(0, x):x + w]
    if patch.size == 0:
        return np.zeros((16, 24), dtype=np.float32)
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (24, 16)).astype(np.float32)


def attribute_speakers(windows: list[tuple[float, float]], presence: np.ndarray,
                       movement: np.ndarray) -> list[int | None]:
    """Falante ativo por janela, com histerese.

    O ativo só muda quando o desafiante tem movimento de boca confiável
    (≥ MOVEMENT_MIN) E supera o atual por SWITCH_RATIO em SWITCH_WINDOWS
    janelas consecutivas. presence/movement: (n_janelas, n_clusters).
    """
    ativos: list[int | None] = []
    current: int | None = None
    pending: int | None = None
    pending_count = 0
    for i in range(len(windows)):
        if presence.shape[1] == 0 or presence[i].sum() == 0:
            ativos.append(None)
            continue
        if current is None:
            if movement[i].max() >= MOVEMENT_MIN:
                current = int(np.argmax(movement[i]))
            else:
                current = int(np.argmax(presence[i]))
            ativos.append(current)
            continue
        challenger = int(np.argmax(movement[i]))
        strong = (challenger != current
                  and movement[i][challenger] >= MOVEMENT_MIN
                  and movement[i][challenger] >= SWITCH_RATIO * max(movement[i][current], 1e-6))
        if strong:
            if pending == challenger:
                pending_count += 1
            else:
                pending, pending_count = challenger, 1
            if pending_count >= SWITCH_WINDOWS:
                current = challenger
                pending, pending_count = None, 0
        else:
            pending, pending_count = None, 0
        ativos.append(current)
    return ativos


def _merge_segments(raw: list[dict]) -> list[dict]:
    """Funde consecutivos com o mesmo alvo e absorve segmentos curtos no anterior."""
    merged: list[dict] = []
    for seg in raw:
        if merged and merged[-1]["cluster"] == seg["cluster"]:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(dict(seg))
    out: list[dict] = []
    for seg in merged:
        if out and seg["end"] - seg["start"] < MIN_SEGMENT_S:
            out[-1]["end"] = seg["end"]
        else:
            out.append(seg)
    final: list[dict] = []
    for seg in out:
        if final and final[-1]["cluster"] == seg["cluster"]:
            final[-1]["end"] = seg["end"]
        else:
            final.append(seg)
    return final


def plan_crop(video_path: str, start: float, end: float, src_w: int, src_h: int,
              detector: FaceDetector | None = None,
              cancel_check: Callable[[], None] | None = None) -> dict:
    import cv2

    crop_w = int(src_h * 9 / 16) // 2 * 2
    if crop_w >= src_w - 16:  # vídeo já é (quase) vertical: nada útil a enquadrar
        return {"mode": "crop", "crop_w": min(crop_w, src_w // 2 * 2), "crop_h": src_h,
                "face_hit_rate": 1.0, "clusters": [],
                "segments": [{"start": start, "end": end, "x0": 0, "x1": 0}]}
    detector = detector or FaceDetector()

    duration = max(0.1, end - start)
    n_windows = max(1, int(np.ceil(duration / WINDOW_S)))
    windows = [(start + i * WINDOW_S, min(end, start + (i + 1) * WINDOW_S))
               for i in range(n_windows)]

    scale = DETECT_WIDTH / src_w if src_w > DETECT_WIDTH else 1.0
    gap = crop_w * 0.6

    # Tracks online: {cx, box, centers[], last_mouth, last_seen, hits}
    tracks: list[dict] = []
    mov_sum = np.zeros((n_windows, MAX_TRACKS))
    mov_cnt = np.zeros((n_windows, MAX_TRACKS))
    presence = np.zeros((n_windows, MAX_TRACKS))
    detect_turns = 0
    detect_with_face = 0
    prev_hist = None

    for si, (t, frame) in enumerate(sample_frames(video_path, start, end)):
        if cancel_check is not None and si % 20 == 0:
            cancel_check()
        wi = min(n_windows - 1, int((t - start) / WINDOW_S))

        if si % DETECT_EVERY == 0:
            small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1.0 else frame
            h = _hist(small)
            if prev_hist is not None and _hist_dist(prev_hist, h) > SCENE_DIST_THRESHOLD:
                for tr in tracks:  # corte de cena: zera memória de boca (evita pico falso)
                    tr["last_mouth"] = None
                    tr["box"] = None
            prev_hist = h

            boxes = detector.detect(small)
            if scale < 1.0:
                inv = 1.0 / scale
                boxes = [(int(x * inv), int(y * inv), int(w * inv), int(hh * inv))
                         for x, y, w, hh in boxes]
            detect_turns += 1
            if boxes:
                detect_with_face += 1
            for box in boxes:
                cx = box[0] + box[2] / 2
                tr = next((tr for tr in tracks if abs(cx - tr["cx"]) <= gap), None)
                if tr is None:
                    if len(tracks) >= MAX_TRACKS:
                        continue
                    tr = {"cx": cx, "box": None, "centers": [], "last_mouth": None,
                          "last_seen": t, "hits": 0}
                    tracks.append(tr)
                tr["centers"].append(cx)
                tr["cx"] = 0.7 * tr["cx"] + 0.3 * cx
                tr["box"] = box
                tr["last_seen"] = t
                tr["hits"] += 1
                presence[wi, tracks.index(tr)] += 1

        # Movimento de boca a cada amostra, usando a última caixa conhecida do track.
        for ti, tr in enumerate(tracks):
            if tr["box"] is None or t - tr["last_seen"] > TRACK_TIMEOUT_S:
                continue
            mouth = _mouth_patch(frame, tr["box"])
            if tr["last_mouth"] is not None and tr["last_mouth"].shape == mouth.shape:
                mov_sum[wi, ti] += float(np.mean(np.abs(mouth - tr["last_mouth"])))
                mov_cnt[wi, ti] += 1
            tr["last_mouth"] = mouth

    hit_rate = detect_with_face / detect_turns if detect_turns else 0.0

    # Filtra tracks espúrios (vistos em poucas detecções).
    keep = [i for i, tr in enumerate(tracks)
            if detect_turns and tr["hits"] / detect_turns >= MIN_TRACK_PRESENCE]
    if not keep or hit_rate < FACE_HIT_RATE_MIN:
        return {"mode": "blur_pad", "crop_w": crop_w, "crop_h": src_h,
                "face_hit_rate": round(hit_rate, 3), "clusters": [], "segments": []}

    cluster_centers = [float(np.median(tracks[i]["centers"])) for i in keep]
    order = np.argsort(cluster_centers)  # clusters ordenados da esquerda p/ direita
    presence_k = presence[:, keep][:, order]
    with np.errstate(invalid="ignore", divide="ignore"):
        movement_k = np.where(mov_cnt[:, keep][:, order] > 0,
                              mov_sum[:, keep][:, order] / np.maximum(mov_cnt[:, keep][:, order], 1),
                              0.0)
    clusters_sorted = [cluster_centers[i] for i in order]

    ativos = attribute_speakers(windows, presence_k, movement_k)
    for i in range(len(ativos)):
        if ativos[i] is None:
            ativos[i] = ativos[i - 1] if i > 0 and ativos[i - 1] is not None else next(
                (a for a in ativos[i:] if a is not None), 0)

    raw_segments = [{"start": w[0], "end": w[1], "cluster": a}
                    for w, a in zip(windows, ativos, strict=False)]
    segments = _merge_segments(raw_segments)

    out_segments = []
    for seg in segments:
        cx = clusters_sorted[seg["cluster"]]
        x = int(np.clip(cx - crop_w / 2, 0, src_w - crop_w))
        out_segments.append({"start": round(seg["start"], 3), "end": round(seg["end"], 3),
                             "x0": x, "x1": x})
    if out_segments:
        out_segments[0]["start"] = round(start, 3)
        out_segments[-1]["end"] = round(end, 3)
    return {"mode": "crop", "crop_w": crop_w, "crop_h": src_h,
            "face_hit_rate": round(hit_rate, 3),
            "clusters": [round(c, 1) for c in clusters_sorted],
            "segments": out_segments}


def apply_framing_override(plan: dict, framing: str | None, src_w: int, src_h: int,
                           start: float, end: float) -> dict:
    """Força o enquadramento escolhido pelo usuário sobre o plano automático."""
    if not framing or framing == "auto":
        return plan
    crop_w = plan.get("crop_w") or int(src_h * 9 / 16) // 2 * 2
    if framing == "blur":
        return {**plan, "mode": "blur_pad", "segments": []}
    clusters = plan.get("clusters") or []
    if framing == "left":
        cx = min(clusters) if clusters else src_w * 0.28
    elif framing == "right":
        cx = max(clusters) if clusters else src_w * 0.72
    else:  # center
        cx = src_w / 2
    x = int(np.clip(cx - crop_w / 2, 0, max(0, src_w - crop_w)))
    return {**plan, "mode": "crop", "crop_w": crop_w, "crop_h": plan.get("crop_h") or src_h,
            "segments": [{"start": round(start, 3), "end": round(end, 3), "x0": x, "x1": x}]}


def stage_reframe(ctx, source_id: str, report) -> None:
    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None or src.status != "ready":
            raise ValueError("Fonte não está pronta para reframe")
        video_path, src_w, src_h = src.file_path, src.width or 1920, src.height or 1080
        pending = s.execute(
            select(CutCandidate.id, CutCandidate.start_s, CutCandidate.end_s)
            .where(CutCandidate.source_video_id == source_id,
                   CutCandidate.crop_plan.is_(None))).all()
    if not pending:
        report(1.0, "Reframe já calculado")
        return
    detector = FaceDetector()
    for i, (cut_id, start, end) in enumerate(pending):
        ctx.check_cancel()
        report(i / len(pending), f"Enquadrando corte {i + 1}/{len(pending)}…")
        plan = plan_crop(video_path, start, end, src_w, src_h, detector,
                         cancel_check=ctx.check_cancel)
        with session() as s:
            cut = s.get(CutCandidate, cut_id)
            if cut is not None:
                cut.crop_plan = plan
    report(1.0, f"Reframe concluído ({len(pending)} cortes, detector {detector.kind})")

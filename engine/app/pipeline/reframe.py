"""Auto Reframe 16:9 → 9:16: detecção facial (YuNet → fallback Haar), cortes de cena,
atribuição de falante por movimento de boca e plano de crop por segmentos (jump cut
entre falantes, drift suave dentro do segmento). Sem rosto suficiente → blur_pad.
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

SAMPLE_FPS = 3.0
SCENE_DIST_THRESHOLD = 0.5      # 1 - correlação de histograma HSV
MIN_SEGMENT_S = 1.2             # segmentos menores são fundidos ao anterior
WINDOW_S = 2.0                  # granularidade da atribuição de falante
MOVEMENT_MIN = 6.0              # movimento de boca mínimo p/ confiar no sinal
FACE_HIT_RATE_MIN = 0.6


class FaceDetector:
    """YuNet (FaceDetectorYN) quando o ONNX está disponível; senão Haar cascade do OpenCV."""

    def __init__(self, yunet_path: str | None = None):
        import cv2

        self._cv2 = cv2
        self.kind = "haar"
        self._yunet = None
        candidates = [yunet_path,
                      str(config.data_dir() / "models" / "yunet.onnx"),
                      str(config.ASSETS_DIR / "yunet.onnx")]
        for path in candidates:
            if path and __import__("os").path.exists(path) and hasattr(cv2, "FaceDetectorYN"):
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
            self._yunet.setInputSize((w, h))
            _, faces = self._yunet.detect(frame_bgr)
            if faces is None:
                return []
            return [(int(f[0]), int(f[1]), int(f[2]), int(f[3])) for f in faces]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                               minSize=(max(24, h // 20), max(24, h // 20)))
        return [tuple(int(v) for v in f) for f in faces]


def sample_frames(video_path: str, start: float, end: float, fps: float = SAMPLE_FPS):
    """Gera (t, frame) por seek. Cortes têm ≤ 90s → custo de seek aceitável."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    try:
        step = 1.0 / fps
        t = start
        while t < end:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if ok and frame is not None:
                yield t, frame
            t += step
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


def _cluster_positions(centers: list[float], gap: float) -> list[float]:
    """Agrupa centros x por proximidade; retorna a mediana de cada cluster (ordenada)."""
    if not centers:
        return []
    xs = sorted(centers)
    clusters: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > gap:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    return [float(np.median(c)) for c in clusters]


def _assign(cx: float, cluster_centers: list[float]) -> int:
    return int(np.argmin([abs(cx - c) for c in cluster_centers]))


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
    """Por janela: cluster ativo = maior movimento de boca (se confiável), senão maior presença.

    presence/movement: shape (n_windows, n_clusters). Retorna índice do cluster ou None.
    """
    ativos: list[int | None] = []
    for i in range(len(windows)):
        if presence.shape[1] == 0 or presence[i].sum() == 0:
            ativos.append(None)
            continue
        if movement[i].max() >= MOVEMENT_MIN:
            ativos.append(int(np.argmax(movement[i])))
        else:
            ativos.append(int(np.argmax(presence[i])))
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
    # segunda passada de fusão (absorções podem ter igualado vizinhos)
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
    crop_w = int(src_h * 9 / 16) // 2 * 2
    if crop_w >= src_w - 16:  # vídeo já é (quase) vertical: nada útil a enquadrar
        return {"mode": "crop", "crop_w": min(crop_w, src_w // 2 * 2), "crop_h": src_h,
                "face_hit_rate": 1.0,
                "segments": [{"start": start, "end": end, "x0": 0, "x1": 0}]}
    detector = detector or FaceDetector()

    samples: list[dict] = []
    prev_hist = None
    scene_cuts: list[float] = []
    for t, frame in sample_frames(video_path, start, end):
        if cancel_check is not None:
            cancel_check()
        h = _hist(frame)
        if prev_hist is not None and _hist_dist(prev_hist, h) > SCENE_DIST_THRESHOLD:
            scene_cuts.append(t)
        prev_hist = h
        faces = detector.detect(frame)
        samples.append({"t": t, "faces": faces, "frame_shape": frame.shape,
                        "mouths": {i: _mouth_patch(frame, f) for i, f in enumerate(faces)}})

    n_samples = max(1, len(samples))
    with_face = sum(1 for s in samples if s["faces"])
    hit_rate = with_face / n_samples
    centers = [f[0] + f[2] / 2 for s in samples for f in s["faces"]]
    clusters = _cluster_positions(centers, gap=crop_w * 0.6)

    if not clusters or hit_rate < FACE_HIT_RATE_MIN:
        return {"mode": "blur_pad", "crop_w": crop_w, "crop_h": src_h,
                "face_hit_rate": round(hit_rate, 3), "segments": []}

    # Janelas de atribuição: grade de 2s quebrada nos cortes de cena.
    bounds = sorted({start, end, *scene_cuts})
    windows: list[tuple[float, float]] = []
    for b0, b1 in zip(bounds, bounds[1:], strict=False):
        t = b0
        while t < b1:
            windows.append((t, min(t + WINDOW_S, b1)))
            t += WINDOW_S

    n_c = len(clusters)
    presence = np.zeros((len(windows), n_c))
    movement = np.zeros((len(windows), n_c))
    last_mouth: dict[int, np.ndarray] = {}
    for s in samples:
        wi = next((i for i, (w0, w1) in enumerate(windows) if w0 <= s["t"] < w1),
                  len(windows) - 1)
        for fi, f in enumerate(s["faces"]):
            ci = _assign(f[0] + f[2] / 2, clusters)
            presence[wi, ci] += 1
            mouth = s["mouths"][fi]
            if ci in last_mouth and last_mouth[ci].shape == mouth.shape:
                movement[wi, ci] += float(np.mean(np.abs(mouth - last_mouth[ci])))
            last_mouth[ci] = mouth

    ativos = attribute_speakers(windows, presence, movement)
    # Preenche janelas sem rosto com o vizinho anterior (ou próximo).
    for i in range(len(ativos)):
        if ativos[i] is None:
            ativos[i] = ativos[i - 1] if i > 0 and ativos[i - 1] is not None else next(
                (a for a in ativos[i:] if a is not None), 0)

    raw_segments = [{"start": w[0], "end": w[1], "cluster": a}
                    for w, a in zip(windows, ativos, strict=False)]
    segments = _merge_segments(raw_segments)

    out_segments = []
    for seg in segments:
        cx = clusters[seg["cluster"]]
        x = int(np.clip(cx - crop_w / 2, 0, src_w - crop_w))
        out_segments.append({"start": round(seg["start"], 3), "end": round(seg["end"], 3),
                             "x0": x, "x1": x})
    if out_segments:
        out_segments[0]["start"] = round(start, 3)
        out_segments[-1]["end"] = round(end, 3)
    return {"mode": "crop", "crop_w": crop_w, "crop_h": src_h,
            "face_hit_rate": round(hit_rate, 3), "segments": out_segments}


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

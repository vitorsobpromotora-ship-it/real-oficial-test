"""RHPT (Real HotPeak Tracking): curva de picos de interesse a partir do áudio.

Sinais por janela de 1s (streaming, nunca carrega o wav inteiro):
  R = energia RMS · H = força/altura de pitch (autocorrelação FFT) ·
  P = ritmo de fala (palavras/s) · T = eventos (picos de energia, risadas, pausas)
Fusão z-normalizada: 0.35R + 0.20H + 0.25P + 0.20T → sigmoide → suavização.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Features:
    hop: float
    times: np.ndarray
    rms: np.ndarray
    peak_curve: np.ndarray  # 0–1
    pauses: list[tuple[float, float]] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def peak_between(self, start: float, end: float) -> tuple[float, float]:
        """(máximo, média) da curva no intervalo."""
        i0 = max(0, int(start / self.hop))
        i1 = min(len(self.peak_curve), max(i0 + 1, int(np.ceil(end / self.hop))))
        window = self.peak_curve[i0:i1]
        if window.size == 0:
            return 0.0, 0.0
        return float(window.max()), float(window.mean())


def _autocorr_pitch_strength(x: np.ndarray, sr: int) -> float:
    """Pico de autocorrelação normalizada na faixa 60–350 Hz (0 = não vozeado)."""
    x = x - x.mean()
    energy = float(np.dot(x, x))
    if energy < 1e-8:
        return 0.0
    n = len(x)
    nfft = 1 << (2 * n - 1).bit_length()
    spec = np.fft.rfft(x, nfft)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lo, hi = int(sr / 350), min(int(sr / 60), n - 1)
    if lo >= hi:
        return 0.0
    return float(np.clip(ac[lo:hi].max() / (ac[0] + 1e-9), 0.0, 1.0))


def _z(a: np.ndarray) -> np.ndarray:
    return (a - a.mean()) / (a.std() + 1e-9)


def _smooth(a: np.ndarray, win: int = 5) -> np.ndarray:
    if len(a) < win:
        return a
    kernel = np.ones(win) / win
    return np.convolve(a, kernel, mode="same")


def compute_features(wav_path: str, words: list[dict], hop: float = 1.0,
                     progress_cb=None, cancel_check=None) -> Features:
    """`words`: [{"start_s","end_s","word"}] da transcrição (pode ser vazio)."""
    import soundfile as sf

    rms_list: list[float] = []
    pitch_list: list[float] = []
    with sf.SoundFile(str(wav_path)) as f:
        sr = f.samplerate
        total_blocks = max(1, int(f.frames / (sr * hop)))
        block = int(sr * hop)
        for bi, data in enumerate(f.blocks(blocksize=block, dtype="float32", always_2d=False,
                                           fill_value=0.0)):
            if cancel_check is not None and bi % 30 == 0:
                cancel_check()
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            rms_list.append(float(np.sqrt(np.mean(data ** 2) + 1e-12)))
            pitch_list.append(_autocorr_pitch_strength(data, sr))
            if progress_cb is not None and bi % 60 == 0:
                progress_cb(min(0.99, bi / total_blocks))

    rms = np.array(rms_list) if rms_list else np.zeros(1)
    pitch = np.array(pitch_list) if pitch_list else np.zeros(1)
    n = len(rms)
    times = np.arange(n) * hop

    # P — ritmo de fala: palavras iniciadas por janela, suavizado.
    pace = np.zeros(n)
    starts = np.array([w["start_s"] for w in words]) if words else np.array([])
    if starts.size:
        idx = np.clip((starts / hop).astype(int), 0, n - 1)
        np.add.at(pace, idx, 1.0)
        pace = _smooth(pace, 5)

    # Pausas: prioridade para lacunas entre palavras; fallback por energia baixa.
    pauses: list[tuple[float, float]] = []
    if words:
        prev_end = 0.0
        for w in words:
            if w["start_s"] - prev_end >= 0.7:
                pauses.append((round(prev_end, 3), round(w["start_s"], 3)))
            prev_end = max(prev_end, w["end_s"])
        total = n * hop
        if total - prev_end >= 0.7:
            pauses.append((round(prev_end, 3), round(total, 3)))
    else:
        thr = max(1e-4, float(np.percentile(rms, 20)) * 0.5)
        quiet = rms < thr
        i = 0
        while i < n:
            if quiet[i]:
                j = i
                while j < n and quiet[j]:
                    j += 1
                if (j - i) * hop >= 0.7:
                    pauses.append((round(i * hop, 3), round(j * hop, 3)))
                i = j
            else:
                i += 1

    # T — eventos.
    events: list[dict] = []
    rms_z = _z(rms)
    word_density = pace
    for i in range(n):
        if rms_z[i] > 2.2:
            events.append({"t": float(times[i]), "type": "pico_energia",
                           "intensity": float(min(3.0, rms_z[i]) / 3.0)})
        elif rms_z[i] > 1.3 and pitch[i] > 0.55 and (not words or word_density[i] < 0.2):
            events.append({"t": float(times[i]), "type": "riso", "intensity": 0.8})

    t_curve = np.zeros(n)
    for ev in events:
        t_curve[min(n - 1, int(ev["t"] / hop))] += ev["intensity"]

    fused = 0.35 * _z(rms) + 0.20 * _z(pitch) + 0.25 * _z(pace) + 0.20 * _z(t_curve)
    peak_curve = _smooth(1.0 / (1.0 + np.exp(-fused)), 5)

    if progress_cb is not None:
        progress_cb(1.0)
    return Features(hop=hop, times=times, rms=rms, peak_curve=peak_curve,
                    pauses=pauses, events=events)

"""Download best-effort de modelos no primeiro uso (máquina do usuário).

- YuNet (detecção facial, ~230 KB): baixado do opencv_zoo; sem ele o motor usa
  o Haar cascade embarcado no OpenCV (qualidade menor, mas funcional).
- Modelos whisper: baixados automaticamente pelo faster-whisper (Hugging Face)
  para config.models_dir() no primeiro uso.
"""

from __future__ import annotations

import logging

from .. import config

log = logging.getLogger(__name__)

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_MIN_SIZE = 100_000  # sanity check (~230 KB esperado)


def ensure_yunet(timeout: float = 20.0) -> str | None:
    """Retorna o caminho do ONNX (baixando se preciso) ou None (fallback Haar)."""
    dest = config.models_dir() / "yunet.onnx"
    if dest.exists() and dest.stat().st_size > _MIN_SIZE:
        return str(dest)
    marker = dest.with_suffix(".failed")
    if marker.exists():  # evita tentar a cada corte quando offline
        return None
    try:
        import httpx

        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(YUNET_URL)
            resp.raise_for_status()
            if len(resp.content) < _MIN_SIZE:
                raise ValueError("arquivo YuNet menor que o esperado")
            dest.write_bytes(resp.content)
        log.info("Modelo YuNet baixado para %s", dest)
        return str(dest)
    except Exception as exc:
        log.warning("Não foi possível baixar o YuNet (%s) — usando Haar cascade", exc)
        try:
            marker.touch()
        except OSError:
            pass
        return None

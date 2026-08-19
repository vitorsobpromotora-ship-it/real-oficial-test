from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import reframe

from .fixtures import make_media


@pytest.fixture(scope="session")
def foto_rosto(tmp_path_factory):
    dst = make_media.GENERATED / "face.jpg"
    photo = make_media.face_photo(dst)
    if photo is None:
        pytest.skip("foto de teste indisponível (matplotlib)")
    return photo


def test_face_detector_encontra_dois_rostos(foto_rosto):
    import cv2

    img = cv2.imread(str(foto_rosto))
    frame = np.full((1080, 1920, 3), (48, 34, 27), dtype=np.uint8)
    small = cv2.resize(img, (384, int(img.shape[0] * 384 / img.shape[1])))
    h, w = small.shape[:2]
    frame[270:270 + h, 240:240 + w] = small
    frame[270:270 + h, 1920 - 240 - w:1920 - 240] = small

    det = reframe.FaceDetector()
    faces = det.detect(frame)
    assert len(faces) >= 2, f"esperava 2 rostos, detectou {faces} (detector {det.kind})"


def test_plan_crop_video_com_rostos(foto_rosto):
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_30s.mp4", duration=30.0)
    plan = reframe.plan_crop(str(video), 2.0, 12.0, 1920, 1080)
    assert plan["mode"] == "crop", plan
    assert plan["face_hit_rate"] >= 0.6
    assert plan["crop_w"] == 606
    segs = plan["segments"]
    assert segs and segs[0]["start"] == 2.0 and segs[-1]["end"] == 12.0
    for seg in segs:
        assert 0 <= seg["x0"] <= 1920 - plan["crop_w"]
        assert seg["end"] > seg["start"]


def test_plan_crop_sem_rostos_vira_blur_pad():
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.make_video(make_media.GENERATED / "fixture_sem_rosto.mp4",
                                  duration=8.0, speech=None, faces=None)
    plan = reframe.plan_crop(str(video), 0.0, 8.0, 1920, 1080)
    assert plan["mode"] == "blur_pad"
    assert plan["segments"] == []


def test_atribuicao_por_movimento_de_boca():
    windows = [(i * 2.0, i * 2.0 + 2.0) for i in range(6)]
    presence = np.ones((6, 2))
    movement = np.zeros((6, 2))
    movement[:3, 0] = 20.0
    movement[3:, 1] = 25.0
    ativos = reframe.attribute_speakers(windows, presence, movement)
    assert ativos == [0, 0, 0, 1, 1, 1]

    # movimento fraco → decide por presença
    fraco = np.full((6, 2), 1.0)
    presenca = np.ones((6, 2))
    presenca[:, 1] = 3.0
    ativos2 = reframe.attribute_speakers(windows, presenca, fraco)
    assert ativos2 == [1] * 6


def test_merge_segments_absorve_curtos():
    raw = [
        {"start": 0.0, "end": 2.0, "cluster": 0},
        {"start": 2.0, "end": 4.0, "cluster": 0},
        {"start": 4.0, "end": 4.5, "cluster": 1},   # curto demais
        {"start": 4.5, "end": 8.0, "cluster": 0},
    ]
    merged = reframe._merge_segments(raw)
    assert merged == [{"start": 0.0, "end": 8.0, "cluster": 0}]


def test_video_ja_vertical_nao_recorta():
    plan = reframe.plan_crop("inexistente.mp4", 0, 10, 608, 1080)
    assert plan["mode"] == "crop"
    assert plan["segments"][0]["x0"] == 0

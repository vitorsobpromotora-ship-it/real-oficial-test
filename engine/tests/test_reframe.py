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


def test_atribuicao_por_movimento_de_boca_com_histerese():
    windows = [(float(i), float(i) + 1.0) for i in range(8)]
    presence = np.ones((8, 2))
    movement = np.full((8, 2), 2.0)
    movement[:3, 0] = 20.0     # falante 0 domina no início
    movement[3:, 1] = 30.0     # falante 1 assume do meio em diante
    movement[3:, 0] = 2.0
    ativos = reframe.attribute_speakers(windows, presence, movement)
    # histerese: a troca só acontece após SWITCH_WINDOWS janelas fortes consecutivas
    assert ativos == [0, 0, 0, 0, 1, 1, 1, 1]

    # movimento fraco em ambos → decide por presença e NÃO fica trocando
    fraco = np.full((8, 2), 1.0)
    presenca = np.ones((8, 2))
    presenca[:, 1] = 3.0
    ativos2 = reframe.attribute_speakers(windows, presenca, fraco)
    assert ativos2 == [1] * 8

    # pico isolado de 1 janela não rouba o foco (evita focar quem só reagiu)
    blip = np.full((8, 2), 2.0)
    blip[:, 0] = 20.0
    blip[4, 1] = 40.0
    ativos3 = reframe.attribute_speakers(windows, presence, blip)
    assert ativos3 == [0] * 8


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


def test_override_manual_de_enquadramento():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080,
            "clusters": [400.0, 1500.0],
            "segments": [{"start": 0.0, "end": 10.0, "x0": 1197, "x1": 1197}]}
    left = reframe.apply_framing_override(plan, "left", 1920, 1080, 0.0, 10.0)
    assert left["segments"][0]["x0"] == max(0, int(400 - 303))
    right = reframe.apply_framing_override(plan, "right", 1920, 1080, 0.0, 10.0)
    assert right["segments"][0]["x0"] == min(1920 - 606, int(1500 - 303))
    blur = reframe.apply_framing_override(plan, "blur", 1920, 1080, 0.0, 10.0)
    assert blur["mode"] == "blur_pad"
    auto = reframe.apply_framing_override(plan, "auto", 1920, 1080, 0.0, 10.0)
    assert auto == plan
    center = reframe.apply_framing_override({"mode": "crop", "crop_w": 606, "crop_h": 1080,
                                             "clusters": [], "segments": []},
                                            "center", 1920, 1080, 0.0, 10.0)
    assert center["segments"][0]["x0"] == int(1920 / 2 - 303)

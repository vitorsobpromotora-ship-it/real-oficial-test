from __future__ import annotations

import subprocess

import pytest

from app.pipeline import captions, censor


def _words(pairs):
    return [{"start_s": s, "end_s": e, "word": w} for s, e, w in pairs]


PALAVRAS = _words([
    (0.0, 0.4, "Eu"), (0.4, 0.9, "nunca"), (0.9, 1.4, "contei"), (1.4, 1.8, "isso"),
    (1.8, 2.2, "para"), (2.2, 2.9, "ninguém"), (3.6, 4.0, "foi"), (4.0, 4.6, "incrível"),
])


def test_build_ass_estrutura_e_karaoke():
    ass = captions.build_ass(PALAVRAS, {"preset": "bold_karaoke"})
    assert "[Script Info]" in ass and "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,Montserrat,72" in ass
    assert "{\\k" in ass, "preset bold_karaoke deve emitir tags de karaokê"
    assert "NUNCA" in ass, "preset bold_karaoke é uppercase"
    # duração do karaokê ≈ duração da palavra (centisegundos)
    assert "{\\k50}NUNCA" in ass  # 0.4→0.9 = 50cs
    # pausa de 0.7s entre 2.9 e 3.6 quebra em dois cartões
    assert ass.count("Dialogue: 0,") == 2


def test_ancora_fixa_topo_evita_pulos_de_altura():
    """Alinhamento 8 (topo-centro) + MarginV = anchor_top: a 1ª linha fica SEMPRE
    na mesma altura; cartões de 1 ou 2 linhas crescem para baixo, sem 'pular'."""
    for preset, anchor in [("bold_karaoke", 1280), ("clean", 1300),
                           ("podcast", 1360), ("minimal", 1400)]:
        ass = captions.build_ass(PALAVRAS, {"preset": preset})
        style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
        campos = style_line.split(",")
        assert campos[18] == "8", f"{preset}: alinhamento deve ser 8 (topo-centro)"
        assert campos[21] == str(anchor), f"{preset}: MarginV/âncora fixa esperada {anchor}"
    # estilo legado com margin_v (sem anchor_top) continua funcionando
    ass = captions.build_ass(PALAVRAS, {"preset": "clean", "anchor_top": None,
                                        "margin_v": 420})
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    assert style_line.split(",")[21] == str(1920 - 420 - 220)


def test_build_ass_sem_karaoke_e_headline():
    ass = captions.build_ass(PALAVRAS, {"preset": "clean"}, headline="Título do Corte",
                             clip_duration=10.0)
    assert "{\\k" not in ass
    assert "Style: Headline" in ass
    assert "Dialogue: 1,0:00:00.00,0:00:10.00,Headline,,0,0,0,,Título do Corte" in ass


def test_quebra_de_linha_nao_termina_em_preposicao():
    texts = ["falamos", "sobre", "a", "grande", "história", "de", "hoje"]
    # max_chars pequeno força quebra; a quebra não deve ficar logo após "de"
    breaks = captions.split_lines(texts, max_chars=18, max_lines=2)
    assert breaks, "esperava ao menos uma quebra"
    for b in breaks:
        assert texts[b - 1].lower() not in captions.NO_BREAK_AFTER


def test_ass_e_aceito_pelo_ffmpeg(tmp_path):
    ass = captions.build_ass(PALAVRAS, {"preset": "podcast"}, headline="Teste")
    (tmp_path / "subs.ass").write_text(ass, encoding="utf-8")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=black:s=1080x1920:d=1:r=10", "-vf", "ass=subs.ass",
         "-frames:v", "5", "-f", "null", "-"],
        cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_words_for_cut_desloca_e_corrige():
    all_words = [{"idx": i, "start_s": 10.0 + i, "end_s": 10.6 + i, "word": f"w{i}"}
                 for i in range(10)]
    out = captions.words_for_cut(all_words, 12.0, 16.0,
                                 edits={"word_overrides": {"3": "corrigida"}})
    assert out[0]["start_s"] == pytest.approx(0.0, abs=0.61)
    assert all(0 <= w["start_s"] < 4.0 for w in out)
    assert any(w["word"] == "corrigida" for w in out)


def test_censura_detecta_e_preserva():
    wl = censor.load_wordlist(["palavrainventada"])
    words = _words([
        (5.0, 5.3, "porra"), (6.0, 6.5, "computador"), (7.0, 7.4, "fodido"),
        (8.0, 8.4, "Porra!"), (9.0, 9.5, "palavrainventada"),
    ])
    intervals = censor.find_intervals(words, wl)
    spans = [(i["start"], i["end"]) for i in intervals]
    assert (4.94, 5.36) in spans
    assert any(abs(s - 6.94) < 0.01 for s, _ in spans), "fodido deve casar com fod*"
    assert not any(5.9 < s < 6.6 for s, _ in spans), "computador não pode ser censurado"
    assert len(intervals) == 4


def test_censura_intervalos_proximos_sao_fundidos():
    wl = censor.load_wordlist()
    words = _words([(1.0, 1.3, "merda"), (1.35, 1.7, "bosta")])
    intervals = censor.find_intervals(words, wl)
    assert len(intervals) == 1
    assert intervals[0]["start"] == pytest.approx(0.94)
    assert intervals[0]["end"] == pytest.approx(1.76)

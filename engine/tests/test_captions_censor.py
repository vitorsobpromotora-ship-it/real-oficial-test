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


def _eventos(ass: str, layer: str = "Dialogue: 0,") -> list[tuple[float, float]]:
    def s2t(x):
        h, m, s = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    out = []
    for ln in ass.splitlines():
        if ln.startswith(layer):
            p = ln.split(",")
            out.append((s2t(p[1]), s2t(p[2])))
    return out


def _palavras_rapidas(n=40, dur=0.28, gap=0.02):
    t, out = 0.0, []
    for i in range(n):
        out.append({"start_s": round(t, 3), "end_s": round(t + dur, 3), "word": f"palavra{i}"})
        t += dur + gap
    return out


def test_build_ass_estrutura_e_karaoke():
    ass = captions.build_ass(PALAVRAS, {"preset": "bold_karaoke"})
    assert "[Script Info]" in ass and "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,Montserrat,74" in ass
    assert "{\\k" in ass, "preset bold_karaoke deve emitir tags de karaokê"
    assert "NUNCA" in ass, "preset bold_karaoke é uppercase"
    assert "{\\k50}NUNCA" in ass  # 0.4→0.9 = 50cs
    # pausa de 0.7s entre 2.9 e 3.6 quebra em dois cartões
    assert ass.count("Dialogue: 0,") == 2


def test_regra_temporal_cartoes_nunca_coexistem():
    """P0: fim_N < início_N+1 em QUALQUER preset e FPS — sem colisão do libass,
    sem legenda 'empilhando' em faixas diferentes."""
    cenarios = {
        "fala_rapida": _palavras_rapidas(),
        "pausa_curta": PALAVRAS,
        "pausa_longa": _words([(0, 0.5, "Uma"), (0.5, 1.0, "frase"), (5.0, 5.5, "depois"),
                               (5.5, 6.2, "do"), (6.2, 6.9, "silêncio")]),
    }
    for preset in captions.PRESETS:
        for fps in (24.0, 30.0, 60.0):
            for nome, palavras in cenarios.items():
                ass = captions.build_ass(palavras, {"preset": preset}, fps=fps)
                evs = _eventos(ass)
                frame = 1.0 / fps
                for (s1, e1), (s2, _e2) in zip(evs, evs[1:], strict=False):
                    assert e1 <= s2 + 1e-9, \
                        f"{preset}@{fps}fps/{nome}: cartão termina {e1} após o próximo começar {s2}"
                    if s2 - s1 > 3 * frame:  # quando o dado permite, folga ≥ meio frame
                        assert s2 - e1 >= frame * 0.49 - 1e-9, \
                            f"{preset}@{fps}fps/{nome}: folga {s2 - e1:.4f} < meio frame"


def test_ancora_unica_em_sequencia_1_2_1_linhas():
    """Cartão de 1 linha → 2 linhas → 1 linha: todos usam o MESMO estilo ancorado
    no topo (o texto cresce para baixo; nenhum cartão muda de faixa)."""
    palavras = _words([
        (0.0, 0.4, "Curto"),                                # 1 linha
        (1.2, 1.6, "Agora"), (1.6, 2.0, "uma"), (2.0, 2.5, "frase"),
        (2.5, 3.0, "bem"), (3.0, 3.5, "comprida"), (3.5, 4.0, "aqui"),  # 2 linhas
        (5.0, 5.4, "Fim"),                                  # 1 linha
    ])
    ass = captions.build_ass(palavras, {"preset": "clean"})
    estilos = [ln for ln in ass.splitlines() if ln.startswith("Style: Default,")]
    assert len(estilos) == 1, "um único estilo — âncora única para todos os cartões"
    campos = estilos[0].split(",")
    assert campos[18] == "8" and campos[21] == "1300"
    for ln in ass.splitlines():
        if ln.startswith("Dialogue: 0,"):
            assert "\\pos(" not in ln and "\\an" not in ln, \
                "cartões não podem redefinir posição individualmente"


def test_presets_sao_realmente_distintos():
    assinaturas = set()
    for _nome, p in captions.PRESETS.items():
        assinaturas.add((p["font_size"], p["border_style"], p["word_mode"],
                         p["anim_word"], p["anchor_top"], p["max_lines"]))
    assert len(assinaturas) == len(captions.PRESETS), \
        "cada preset precisa diferir de verdade (tamanho/caixa/modo/animação/âncora/linhas)"


def test_palavra_pop_um_cartao_por_palavra_com_animacao():
    palavras = _palavras_rapidas(6)
    ass = captions.build_ass(palavras, {"preset": "palavra_pop"})
    evs = _eventos(ass)
    assert len(evs) == 6, "word_mode: um cartão por palavra"
    assert "\\t(0," in ass and "\\fscx" in ass, "animação de pop por palavra"
    for (_s1, e1), (s2, _) in zip(evs, evs[1:], strict=False):
        assert e1 <= s2 + 1e-9


def test_bounce_tem_overshoot_e_subtitle_bar_tem_caixa():
    ass_b = captions.build_ass(PALAVRAS, {"preset": "bounce"})
    assert "\\fscx114" in ass_b, "bounce: overshoot acima de 100%"
    ass_s = captions.build_ass(PALAVRAS, {"preset": "subtitle_bar"})
    style = next(ln for ln in ass_s.splitlines() if ln.startswith("Style: Default,"))
    assert style.split(",")[15] == "3", "subtitle_bar usa BorderStyle=3 (caixa de fundo)"
    assert style.split(",")[21] == "1680", "barra ancorada no rodapé"


def test_max_words_cria_cartao_sequencial_sem_comprimir():
    palavras = _palavras_rapidas(9, dur=0.4, gap=0.05)
    ass = captions.build_ass(palavras, {"preset": "highlight_box"})  # max_words=4
    assert ass.count("Dialogue: 0,") == 3, "9 palavras ÷ 4 por cartão = 3 cartões"
    assert "Style: Default,Montserrat,64" in ass, "fonte NÃO encolhe para caber"


def test_config_explicita_largura_e_alinhamento():
    ass = captions.build_ass(PALAVRAS, {"preset": "clean", "max_width_pct": 60,
                                        "align": "left", "anchor_top": 900})
    style = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    campos = style.split(",")
    assert campos[18] == "7", "align left no topo (7) mantém âncora fixa"
    assert campos[19] == campos[20] == str(int(1080 * 40 / 200)), "margens de 60% de largura"
    assert campos[21] == "900"


def test_kit_sobrescreve_estilo_sem_quebrar_regras():
    kit = {"caption_preset": "podcast", "primary_color": "#00FF00",
           "caption_style": {"anchor_top": 1500, "max_words": 3}}
    palavras = _palavras_rapidas(7, dur=0.35, gap=0.03)
    ass = captions.build_ass(palavras, None, brand_kit=kit)
    style = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    assert style.split(",")[21] == "1500", "âncora do kit vale para TODOS os cartões"
    evs = _eventos(ass)
    assert len(evs) == 3, "max_words=3 do kit agrupa 7 palavras em 3 cartões"
    for (_s1, e1), (s2, _) in zip(evs, evs[1:], strict=False):
        assert e1 <= s2 + 1e-9, "override do kit não pode reintroduzir sobreposição"


def test_karaoke_nao_ultrapassa_janela_do_cartao():
    palavras = _palavras_rapidas(12)
    ass = captions.build_ass(palavras, {"preset": "bold_karaoke"}, fps=30.0)
    import re

    for ln in ass.splitlines():
        if not ln.startswith("Dialogue: 0,"):
            continue
        (s, e), = _eventos("\n" + ln)
        soma_cs = sum(int(m) for m in re.findall(r"\\k(\d+)", ln))
        assert soma_cs <= round((e - s) * 100) + 1, \
            "soma dos {\\k} não pode ultrapassar a duração do cartão"


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

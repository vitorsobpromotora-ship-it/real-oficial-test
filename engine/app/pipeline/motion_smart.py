"""Smart Motion (v4 FASE J) — sugestões automáticas de efeitos.

A camada SEMÂNTICA decide onde o motion entra (Entrega 75: semântica manda,
áudio confirma): os sinais são estrutura de VERSO (pausas), RIMA entre finais
de versos, léxico de impacto e posição — nunca "volume alto = efeito".

Princípios inegociáveis:
- A sugestão só escolhe do CATÁLOGO controlado (Entrega 70) e sai como
  Suggestion {start, end, target_words, semantic_role, impact_score,
  suggested_preset, intensity, reason} — o reason em PT-BR aparece no
  Inspector (Entrega 73).
- Nada é aplicado aqui: o app expande as sugestões em EffectInstances comuns
  (origin="auto"), 100% editáveis e desfazíveis (Entrega 77).
- Estilos editoriais são DADOS (Limpa/Dinâmica/Batalha/Agressiva): perfis de
  densidade e de mapeamento papel→presets — nenhum `if batalha:` no motor
  (Entregas 24–25, 132).
- Cooldown por densidade (Entrega 23): batalha ≠ tudo piscando; o gap mínimo
  entre efeitos é parte do estilo, e "Desativado" existe.
- Determinismo: mesma transcrição + estilo + seed → as MESMAS sugestões.
"""

from __future__ import annotations

import unicodedata

from . import motion

# léxico de IMPACTO em PT — conclusão/agressão/superlativo genéricos de
# short-form (não é um dicionário de nicho; estilos só mudam pesos/densidade)
IMPACT_WORDS = {
    "matou", "matei", "morreu", "acabou", "acabei", "destruí", "destruiu",
    "nunca", "nada", "ninguém", "tudo", "sempre", "fim", "game", "over",
    "melhor", "pior", "único", "última", "último", "perdeu", "ganhei",
    "venci", "calou", "cala", "quebrou", "quebrei", "explodiu", "chocou",
    "absurdo", "insano", "brabo", "pesado", "forte", "real", "verdade",
    "mentira", "medo", "rei", "reinado", "coroa", "trono", "lenda", "mito",
    "fraco", "covarde", "lixo", "fácil", "impossível", "história", "nível",
}

EDITORIAL_STYLES: dict[str, dict] = {
    "limpa": {
        "id": "limpa", "label": "Limpa",
        "descricao": "Quase nada se mexe — só o essencial, discreto.",
        "densidade": "baixa", "intensidade": "suave", "composites": False,
        "roles": {"punchline": ["pop_clean"], "fatality": ["punch"],
                  "build": [], "setup": [], "reaction": []},
        "min_score": 6.0,
    },
    "dinamica": {
        "id": "dinamica", "label": "Dinâmica",
        "descricao": "Ritmo de short-form geral: pops e punches nos ganchos.",
        "densidade": "balanceada", "intensidade": "normal", "composites": False,
        "roles": {"punchline": ["punch", "pop_elastic"], "fatality": ["slam"],
                  "build": ["color_pop"], "setup": [], "reaction": []},
        "min_score": 4.5,
    },
    "batalha": {
        "id": "batalha", "label": "Batalha",
        "descricao": "Arco de rima: arma no setup, cresce no build, estoura "
                     "na punchline e a fatality leva a cena junto.",
        "densidade": "balanceada", "intensidade": "normal", "composites": True,
        "roles": {"punchline": ["punch", "slam", "bass_hit"],
                  "fatality": ["fatality_composta"],
                  "build": ["pop_clean"], "setup": ["soft_impact"],
                  "reaction": ["zoom_out"]},
        "min_score": 4.0,
    },
    "agressiva": {
        "id": "agressiva", "label": "Agressiva",
        "descricao": "Tudo mais pesado e mais frequente — para trechos de caos.",
        "densidade": "alta", "intensidade": "forte", "composites": True,
        "roles": {"punchline": ["slam", "knockout", "bass_hit"],
                  "fatality": ["fatality_composta"],
                  "build": ["word_stretch", "glitch_snap"],
                  "setup": ["color_pop"], "reaction": ["zoom_out"]},
        "min_score": 3.2,
    },
}

DENSITIES: dict[str, dict | None] = {
    "desativado": None,
    "baixa": {"min_gap_s": 8.0, "max_por_min": 4},
    "balanceada": {"min_gap_s": 4.5, "max_por_min": 9},
    "alta": {"min_gap_s": 2.2, "max_por_min": 16},
}

PAUSA_VERSO_S = 0.35  # gap que fecha um verso
PAUSA_REACAO_S = 0.8  # respiro pós-punchline = janela de reação


def _norm(txt: str) -> str:
    s = unicodedata.normalize("NFD", txt.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn"
                   and ch.isalpha())


def _sufixos_rima(txt: str) -> tuple[str, str]:
    """(sufixo forte de 3 letras, sufixo fraco de 2) — 'chegou/acabou'
    rimam pelo fraco ('ou'); 'coroa/patroa' pelo forte ('roa')."""
    n = _norm(txt)
    return (n[-3:] if len(n) >= 3 else n, n[-2:] if len(n) >= 2 else n)


def versos_de(words: list[dict]) -> list[list[dict]]:
    """Quebra a transcrição em VERSOS pelas pausas — a unidade da rima."""
    versos: list[list[dict]] = []
    atual: list[dict] = []
    for i, w in enumerate(words):
        atual.append(w)
        gap = (words[i + 1]["start_s"] - w["end_s"]) if i + 1 < len(words) else 99
        if gap >= PAUSA_VERSO_S and atual:
            versos.append(atual)
            atual = []
    if atual:
        versos.append(atual)
    return versos


def classify(words: list[dict]) -> list[dict]:
    """Papel semântico por palavra candidata (Entrega 21): estrutura de verso
    + rima + léxico + posição. Retorna candidatos com score e reason."""
    out: list[dict] = []
    versos = versos_de(words)
    suf_ant: tuple[str, str] | None = None
    cadeia_rima = 0  # versos consecutivos rimando = build-up armado
    for vi, verso in enumerate(versos):
        ultima = verso[-1]
        score = 2.0
        motivos = ["fim de verso"]
        suf = _sufixos_rima(str(ultima["word"]))
        rimou = False
        if suf_ant and suf[0] and suf[0] == suf_ant[0]:
            score += 3.0
            motivos.append("rima com o verso anterior")
            rimou = True
        elif suf_ant and suf[1] and suf[1] == suf_ant[1]:
            score += 2.0
            motivos.append("rima com o verso anterior")
            rimou = True
        if rimou:
            cadeia_rima += 1
            if cadeia_rima >= 2:  # 3º verso da sequência: a rima vinha armando
                score += min(3.0, 1.5 * (cadeia_rima - 1))
                motivos.append("sequência de rimas armada")
        else:
            cadeia_rima = 0
        if _norm(str(ultima["word"])) in IMPACT_WORDS:
            score += 2.5
            motivos.append("palavra de impacto")
        if len(verso) >= 4:
            score += 1.0
            motivos.append("verso cheio")
        if vi == len(versos) - 1:
            score += 1.5
            motivos.append("fecho do trecho")
        role = "fatality" if score >= 8.0 else "punchline" if score >= 4.0 \
            else "build" if score >= 3.0 else "normal"
        if role != "normal":
            out.append({"idx": int(ultima["idx"]), "word": str(ultima["word"]),
                        "start_s": float(ultima["start_s"]),
                        "end_s": float(ultima["end_s"]),
                        "role": role, "score": round(score, 2),
                        "reason": ", ".join(motivos)})
        # palavras de impacto NO MEIO do verso viram build (a subida)
        for w in verso[:-1]:
            if _norm(str(w["word"])) in IMPACT_WORDS:
                out.append({"idx": int(w["idx"]), "word": str(w["word"]),
                            "start_s": float(w["start_s"]),
                            "end_s": float(w["end_s"]),
                            "role": "build", "score": 3.0,
                            "reason": "palavra de impacto no meio do verso"})
        # respiro longo após o verso = janela de REAÇÃO (Entrega 74)
        fim = float(ultima["end_s"])
        prox = next((float(v[0]["start_s"]) for v in versos[vi + 1:vi + 2]), None)
        if prox is not None and prox - fim >= PAUSA_REACAO_S and score >= 4.0:
            out.append({"idx": int(ultima["idx"]), "word": str(ultima["word"]),
                        "start_s": fim, "end_s": prox, "role": "reaction",
                        "score": round(score - 1.0, 2),
                        "reason": "respiro após a punchline — deixe a reação viver"})
        suf_ant = suf
    return out


def suggest(words: list[dict], style: str = "batalha",
            density: str | None = None, seed: int = 1) -> list[dict]:
    """Sugestões prontas para o Inspector (Entrega 72) — nada aplicado."""
    perfil = EDITORIAL_STYLES.get(style) or EDITORIAL_STYLES["batalha"]
    dens = DENSITIES.get(density or perfil["densidade"])
    if dens is None:
        return []
    candidatos = [c for c in classify(words)
                  if c["score"] >= perfil["min_score"] or c["role"] == "reaction"]
    candidatos.sort(key=lambda c: (-c["score"], c["start_s"]))
    total = (words[-1]["end_s"] - words[0]["start_s"]) if words else 0.0
    max_n = max(1, int(dens["max_por_min"] * max(total, 1.0) / 60.0))
    aceitos: list[dict] = []
    for i, c in enumerate(candidatos):
        if len(aceitos) >= max_n:
            break
        if any(abs(c["start_s"] - a["start"]) < dens["min_gap_s"]
               for a in aceitos):
            continue  # cooldown (Entrega 23)
        pool = perfil["roles"].get(c["role"]) or []
        if not pool:
            continue
        preset = pool[int(motion.rng01(seed, i) * len(pool)) % len(pool)]
        composite = preset.endswith("_composta")
        aceitos.append({
            "start": round(c["start_s"], 3),
            "end": round(c["end_s"] + (0.25 if c["role"] != "reaction" else 0.0), 3),
            "target_words": [c["idx"]],
            "semantic_role": c["role"],
            "impact_score": c["score"],
            "suggested_preset": preset,
            "kind": "composite" if composite
            else ("video_fx" if c["role"] == "reaction" else "text_emphasis"),
            "intensity": perfil["intensidade"],
            "reason": f"“{c['word']}”: {c['reason']}",
            "word": c["word"],
        })
    aceitos.sort(key=lambda a: a["start"])
    return aceitos

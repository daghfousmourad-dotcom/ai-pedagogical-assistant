import re
from typing import Optional

WORD_TO_NUM = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "dix-sept": 17, "dix sept": 17, "dix-huit": 18, "dix huit": 18,
    "dix-neuf": 19, "dix neuf": 19, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60, "soixante-dix": 70, "soixante dix": 70,
    "quatre-vingt": 80, "quatre vingt": 80, "quatre-vingt-dix": 90, "quatre vingt dix": 90,
    "cent": 100,
}

def word_or_digit_to_int(s: str) -> Optional[int]:
    """Convertit un token en entier (chiffre ou mot français)."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    return WORD_TO_NUM.get(s)

def parse_navigation_command(speech_text: str, current_page: int) -> Optional[dict]:
    """
    Version légère du navigator pour le Super Agent.
    Détecte les commandes de navigation simples.
    """
    text = speech_text.lower().strip()

    # 1. Page suivante
    if re.search(r"\b(page\s+suivante|suivant|prochain(?:e)?|avance[rz]?)\b", text):
        return {"action": "JUMP", "target_page": current_page + 1}

    # 2. Page précédente
    if re.search(r"\b(page\s+pr[eé]c[eé]dente|pr[eé]c[eé]dent|retour|revenir|recu[lr][ue][rs]?|recule)\b", text):
        return {"action": "JUMP", "target_page": max(1, current_page - 1)}

    # 3. Numéro de page explicite
    pattern_page = re.compile(
        r"\b(?:page|slide|diapo(?:sitive)?|num[eé]ro)\s+(\d+|"
        + "|".join(re.escape(w) for w in sorted(WORD_TO_NUM, key=len, reverse=True))
        + r")\b"
    )
    m = pattern_page.search(text)
    if m:
        page_num = word_or_digit_to_int(m.group(1))
        if page_num:
            return {"action": "JUMP", "target_page": page_num}

    # 4. "va au début"
    if re.search(r"\b(d[eé]but|premi[eè]re?\s+page|page\s+1|page\s+un(?:e)?)\b", text):
        return {"action": "JUMP", "target_page": 1}

    return None

"""Utilitários de texto para nomes de medicamentos."""
from __future__ import annotations

import re
import unicodedata


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    """minúsculas, sem acento, espaços simples, µ -> mc."""
    if not s:
        return ""
    s = s.replace("µ", "mc").replace("μ", "mc")
    s = strip_accents(s).lower()
    s = re.sub(r"[^\w%/.,+\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Sais e prefixos que não alteram o princípio ativo para fins de busca.
SALTS = [
    "cloridrato", "dicloridrato", "bromidrato", "maleato", "fumarato", "succinato",
    "tartarato", "hemitartarato", "sulfato", "fosfato", "citrato", "acetato",
    "mesilato", "besilato", "cloreto", "oxalato", "hemifumarato", "hidrobrometo",
    "monoidratado", "di-hidratado", "sodico", "sodica", "potassico", "potassica",
    "calcico", "calcica", "magnesico", "valproato de", "hiclato", "pamoato",
    "decanoato", "enantato", "propionato", "lactato", "gluconato", "levomalato",
]

FORMS = {
    "comprimido": ["comprimido", "comprimidos", "comp", "comps", "cpr", "cp", "cpd", "drageas", "dragea",
                   "comprimido revestido", "comprimidos revestidos", "rev", "cpr rev"],
    "capsula": ["capsula", "capsulas", "caps", "cap", "cps"],
    "solucao_oral": ["gotas", "gts", "solucao oral", "sol oral", "solucao", "sol", "xarope", "suspensao", "susp"],
    "injetavel": ["injetavel", "inj", "ampola", "ampolas", "amp", "solucao injetavel"],
    "creme": ["creme", "pomada", "gel", "unguento"],
}

PACK_UNITS = r"(?:comprimidos?|comp|comps|cpr|cprs|cp|cpd|capsulas?|caps|cps|drageas?|unidades?|un|und|ampolas?|amp|envelopes?|saches?|flaconetes?|adesivos?)"


def detect_form(text: str) -> str | None:
    t = f" {norm(text)} "
    # injetável antes de solução (solução injetável)
    for form in ["injetavel", "capsula", "comprimido", "solucao_oral", "creme"]:
        for kw in FORMS[form]:
            if re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", t):
                return form
    return None


_DOSE_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(mcg|mg|g|ui)(?![a-z/])", re.I)
_CONC_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mcg|mg|g|ui)\s*/\s*(\d+(?:[.,]\d+)?)?\s*(ml|g|gota|gt)", re.I)
_PACK_RES = [
    re.compile(rf"(?:c/|com|cx|caixa|x)\s*(\d{{1,4}})\s*{PACK_UNITS}?(?![a-z])", re.I),
    re.compile(rf"(?<![\d.,])(\d{{1,4}})\s*{PACK_UNITS}(?![a-z])", re.I),
]
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*ml(?![a-z/])", re.I)


def _f(x: str) -> float:
    return float(x.replace(",", "."))


def parse_concentration(text: str) -> str | None:
    m = _CONC_RE.search(norm(text))
    if not m:
        return None
    per = m.group(3)
    per_s = f"{_f(per):g}" if per else ""
    return f"{_f(m.group(1)):g}{m.group(2).lower()}/{per_s}{m.group(4).lower()}"


def parse_dose(text: str) -> tuple[float | None, str | None]:
    """Dosagem por unidade (ex.: 25 mg). Ignora concentrações (mg/ml) e
    nunca usa a quantidade de comprimidos da embalagem."""
    t = norm(text)
    t_wo_conc = _CONC_RE.sub(" ", t)
    m = _DOSE_RE.search(t_wo_conc)
    if not m:
        return None, None
    return _f(m.group(1)), m.group(2).lower()


def parse_pack_quantity(text: str) -> int | None:
    """Quantidade de unidades na embalagem (ex.: '20 comprimidos', 'c/ 20').

    Remove antes as dosagens (25mg) para não confundir dose com quantidade."""
    t = norm(text)
    t = _CONC_RE.sub(" ", t)
    t = _DOSE_RE.sub(" ", t)
    for rx in _PACK_RES:
        m = rx.search(t)
        if m:
            n = int(m.group(1))
            if 0 < n <= 2000:
                return n
    return None


def remove_salts(text: str) -> tuple[str, str | None]:
    t = norm(text)
    found = None
    for salt in sorted(SALTS, key=len, reverse=True):
        rx = rf"(?<![a-z]){re.escape(salt)}(?: de)?(?![a-z])"
        if re.search(rx, t):
            found = found or salt
            t = re.sub(rx, " ", t)
    return re.sub(r"\s+", " ", t).strip(), found

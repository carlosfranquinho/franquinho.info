#!/usr/bin/env python3
"""
GEDCOM vs BD comparison with family-context BFS matching.
Generates /dados/projetos/franquinho.info/relatorio_ged.html
"""
import json
import re
import unicodedata
import os
import sys
from collections import deque, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from datetime import date

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path("/dados/projetos/franquinho.info")
GED_FILE = BASE / "data" / "5n469m_96606156exucx6eiv65a79_A.ged"
PESSOAS_DIR = BASE / "src" / "data" / "pessoas"
FAMILIAS_DIR = BASE / "src" / "data" / "familias"
OUTPUT_HTML = BASE / "relatorio_ged.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    """Lowercase, strip accents, keep only letters/spaces."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z ]", "", s)
    return s.strip()


def first_name(s: str) -> str:
    """Return first token of normalized name."""
    parts = normalize(s).split()
    return parts[0] if parts else ""


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def first_name_match(a: str, b: str, threshold=0.8) -> bool:
    fa, fb = first_name(a), first_name(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    return SequenceMatcher(None, fa, fb).ratio() >= threshold


def year_from_date(d) -> int | None:
    if not d:
        return None
    if isinstance(d, int):
        return d
    m = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', str(d))
    return int(m.group(1)) if m else None


def years_compatible(y1, y2, tolerance=3) -> bool:
    if y1 is None or y2 is None:
        return True
    return abs(y1 - y2) <= tolerance


def year_distance(y1, y2) -> float:
    """Distance between two years; None counts as neutral (10)."""
    if y1 is None or y2 is None:
        return 10.0
    return float(abs(y1 - y2))


# ---------------------------------------------------------------------------
# Parse GEDCOM
# ---------------------------------------------------------------------------
def parse_ged(filepath):
    """
    Returns:
        individuals: dict[ged_id] -> {id, name, givn, surn, sex, birth_year,
                                       birth_date, birth_place, death_year,
                                       death_date, death_place, fams: list,
                                       famc: list}
        families:   dict[fam_id] -> {husb, wife, children: list}
    """
    individuals = {}
    families = {}

    # File is UTF-8 with BOM but has ~4 corrupted bytes; use replace to get clean Unicode
    with open(filepath, encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()

    cur_indi = None
    cur_fam = None
    cur_tag = None  # last 1-level tag inside INDI (BIRT/DEAT)
    cur_event = {}  # accumulating event fields

    def flush_event(indi, tag, ev):
        if tag == "BIRT":
            indi["birth_date"] = ev.get("DATE", "")
            indi["birth_year"] = year_from_date(ev.get("DATE", ""))
            indi["birth_place"] = ev.get("PLAC", "")
        elif tag == "DEAT":
            indi["death_date"] = ev.get("DATE", "")
            indi["death_year"] = year_from_date(ev.get("DATE", ""))
            indi["death_place"] = ev.get("PLAC", "")

    for raw in lines:
        line = raw.rstrip("\n\r")
        if not line.strip():
            continue
        m = re.match(r'^(\d+)\s+(\S+)(?:\s+(.*))?$', line)
        if not m:
            continue
        level, tag, value = int(m.group(1)), m.group(2), (m.group(3) or "").strip()

        if level == 0:
            # Flush previous event
            if cur_indi and cur_tag in ("BIRT", "DEAT"):
                flush_event(cur_indi, cur_tag, cur_event)
            cur_tag = None
            cur_event = {}

            if tag.startswith("@I") and value == "INDI":
                ged_id = tag.strip("@")
                cur_indi = {
                    "id": ged_id,
                    "name": "", "givn": "", "surn": "", "sex": "",
                    "birth_date": "", "birth_year": None,
                    "birth_place": "", "death_date": "", "death_year": None,
                    "death_place": "", "fams": [], "famc": []
                }
                individuals[ged_id] = cur_indi
                cur_fam = None
            elif tag.startswith("@F") and value == "FAM":
                fam_id = tag.strip("@")
                cur_fam = {"husb": None, "wife": None, "children": []}
                families[fam_id] = cur_fam
                cur_indi = None
            else:
                cur_indi = None
                cur_fam = None

        elif cur_indi is not None:
            if level == 1:
                # Flush previous event first
                if cur_tag in ("BIRT", "DEAT"):
                    flush_event(cur_indi, cur_tag, cur_event)
                cur_tag = tag
                cur_event = {}
                if tag == "NAME":
                    cur_indi["name"] = value
                elif tag == "SEX":
                    cur_indi["sex"] = value
                elif tag == "FAMS":
                    fid = value.strip("@")
                    cur_indi["fams"].append(fid)
                elif tag == "FAMC":
                    fid = value.strip("@")
                    cur_indi["famc"].append(fid)
            elif level == 2 and cur_tag in ("BIRT", "DEAT", "CHR"):
                if tag in ("DATE", "PLAC"):
                    cur_event[tag] = value
            elif level == 1 and tag == "GIVN":
                cur_indi["givn"] = value
            elif level == 1 and tag == "SURN":
                cur_indi["surn"] = value

            # Also handle GIVN/SURN at level 2 under NAME
            if level == 2 and cur_tag == "NAME":
                if tag == "GIVN":
                    cur_indi["givn"] = value
                elif tag == "SURN":
                    cur_indi["surn"] = value

        elif cur_fam is not None:
            if level == 1:
                if tag == "HUSB":
                    cur_fam["husb"] = value.strip("@")
                elif tag == "WIFE":
                    cur_fam["wife"] = value.strip("@")
                elif tag == "CHIL":
                    cur_fam["children"].append(value.strip("@"))

    # Final flush
    if cur_indi and cur_tag in ("BIRT", "DEAT"):
        flush_event(cur_indi, cur_tag, cur_event)

    # Post-process: extract name from NAME field if givn/surn empty
    for indi in individuals.values():
        if not indi["givn"] and indi["name"]:
            # NAME format: "Given /Surname/"
            nm = indi["name"]
            m2 = re.match(r'^(.*?)\s*/([^/]*)/\s*(.*)$', nm)
            if m2:
                indi["givn"] = (m2.group(1) + " " + m2.group(3)).strip()
                indi["surn"] = m2.group(2)
            else:
                indi["givn"] = nm
        indi["display_name"] = (indi["givn"] + " " + indi["surn"]).strip()

    return individuals, families


# ---------------------------------------------------------------------------
# Load BD
# ---------------------------------------------------------------------------
def load_bd():
    pessoas = {}
    for f in PESSOAS_DIR.glob("*.json"):
        with open(f) as fp:
            data = json.load(fp)
        pessoas[data["id"]] = data

    familias = {}
    for f in FAMILIAS_DIR.glob("*.json"):
        with open(f) as fp:
            data = json.load(fp)
        familias[data["id"]] = data

    return pessoas, familias


def bd_person_name(p):
    """Best display name for a BD person (may be protected)."""
    if p.get("protegida"):
        nome = p.get("nome", "") or ""
        apelido = p.get("apelido", "") or ""
        if nome == "Familiar":
            return f"[Familiar] {apelido}".strip()
        return (nome + " " + apelido).strip()
    nome = p.get("nome", "") or ""
    apelido = p.get("apelido", "") or ""
    return (nome + " " + apelido).strip()


def bd_first_name(p):
    """First given name for matching purposes."""
    if p.get("protegida"):
        # Use apelido tokens as fallback
        return first_name(p.get("apelido", "") or "")
    nome_proprio = p.get("nome_proprio", "") or ""
    if nome_proprio:
        return first_name(nome_proprio)
    return first_name(p.get("nome", "") or "")


def bd_birth_year(p):
    birt = p.get("nascimento") or {}
    return year_from_date(birt.get("data", ""))


# ---------------------------------------------------------------------------
# BFS matching
# ---------------------------------------------------------------------------
def match_pair(bd_p, ged_p) -> tuple[bool, str]:
    """
    Try to match a BD person to a GED individual.
    Returns (matched, confidence).
    """
    # For protected BD persons: use apelido tokens
    if bd_p.get("protegida"):
        bd_name = bd_p.get("apelido", "") or ""
    else:
        bd_name = bd_person_name(bd_p)

    ged_name = ged_p["display_name"]

    # Sex check (if both have data)
    bd_sex = bd_p.get("sexo", "")
    ged_sex = ged_p.get("sex", "")
    if bd_sex and ged_sex and bd_sex != ged_sex:
        return False, ""

    # Name matching
    fn_ok = first_name_match(bd_name, ged_name)
    sim = name_similarity(bd_name, ged_name)
    name_ok = fn_ok or sim >= 0.7

    if not name_ok:
        # Last resort: check if any token of bd apelido in ged surname
        if bd_p.get("protegida"):
            ap_tokens = normalize(bd_p.get("apelido", "") or "").split()
            ged_surn = normalize(ged_p.get("surn", "") or "")
            ged_givn = normalize(ged_p.get("givn", "") or "")
            if any(t in ged_surn or t in ged_givn for t in ap_tokens if len(t) > 3):
                name_ok = True
        if not name_ok:
            return False, ""

    # Year matching — tighter tolerance for protected persons (to avoid sibling confusion)
    bd_year = bd_birth_year(bd_p)
    ged_year = ged_p.get("birth_year")
    tol = 1 if (bd_p.get("protegida") and bd_year and ged_year) else 3
    year_ok = years_compatible(bd_year, ged_year, tolerance=tol)

    if not year_ok:
        return False, ""

    # Determine confidence
    if fn_ok and bd_year and ged_year and abs(bd_year - ged_year) <= 1:
        return True, "ALTO"
    elif fn_ok and (bd_year is None or ged_year is None):
        return True, "MÉDIO"
    elif sim >= 0.7:
        return True, "BAIXO"
    else:
        return True, "MÉDIO"


def get_bd_relatives(bd_id, pessoas, familias):
    """Return list of BD IDs related to bd_id."""
    p = pessoas.get(bd_id)
    if not p:
        return []
    rel = []
    all_fams = list(p.get("familias_como_filho", []) or []) + list(p.get("familias_como_pai", []) or [])
    for fid in all_fams:
        fam = familias.get(fid)
        if not fam:
            continue
        for role in ("pai", "mae"):
            rid = fam.get(role)
            if rid and rid != bd_id:
                rel.append(rid)
        for cid in (fam.get("filhos") or []):
            if cid != bd_id:
                rel.append(cid)
    return rel


def get_ged_relatives(ged_id, ged_inds, ged_fams):
    """Return list of GED IDs related to ged_id."""
    p = ged_inds.get(ged_id)
    if not p:
        return []
    rel = []
    for fid in p.get("famc", []):
        fam = ged_fams.get(fid)
        if fam:
            for r in ("husb", "wife"):
                rid = fam.get(r)
                if rid:
                    rel.append(rid)
            for cid in fam.get("children", []):
                if cid != ged_id:
                    rel.append(cid)
    for fid in p.get("fams", []):
        fam = ged_fams.get(fid)
        if fam:
            for r in ("husb", "wife"):
                rid = fam.get(r)
                if rid and rid != ged_id:
                    rel.append(rid)
            for cid in fam.get("children", []):
                rel.append(cid)
    return rel


def bfs_match(anchor_bd, anchor_ged, pessoas, familias, ged_inds, ged_fams):
    """
    BFS from anchor. Returns:
        matched: dict[bd_id] -> {ged_id, confidence}
        matched_rev: dict[ged_id] -> bd_id
    """
    matched = {anchor_bd: {"ged_id": anchor_ged, "confidence": "ALTO"}}
    matched_rev = {anchor_ged: anchor_bd}
    visited_bd = {anchor_bd}
    visited_ged = {anchor_ged}
    queue = deque([(anchor_bd, anchor_ged)])

    while queue:
        bd_id, ged_id = queue.popleft()
        bd_rels = get_bd_relatives(bd_id, pessoas, familias)
        ged_rels = get_ged_relatives(ged_id, ged_inds, ged_fams)

        # Try to match unmatched BD relatives to unmatched GED relatives
        for bd_rel in bd_rels:
            if bd_rel in visited_bd:
                continue
            bd_p = pessoas.get(bd_rel)
            if not bd_p:
                continue
            best_ged = None
            best_conf = ""
            best_score = None  # (rank, -year_dist) — higher is better

            for ged_rel in ged_rels:
                if ged_rel in visited_ged:
                    continue
                ged_p = ged_inds.get(ged_rel)
                if not ged_p:
                    continue
                ok, conf = match_pair(bd_p, ged_p)
                if ok:
                    rank = {"ALTO": 3, "MÉDIO": 2, "BAIXO": 1}.get(conf, 0)
                    ydist = year_distance(bd_birth_year(bd_p), ged_p.get("birth_year"))
                    score = (rank, -ydist)
                    if best_score is None or score > best_score:
                        best_ged = ged_rel
                        best_conf = conf
                        best_score = score

            if best_ged:
                matched[bd_rel] = {"ged_id": best_ged, "confidence": best_conf}
                matched_rev[best_ged] = bd_rel
                visited_bd.add(bd_rel)
                visited_ged.add(best_ged)
                queue.append((bd_rel, best_ged))

    return matched, matched_rev


# ---------------------------------------------------------------------------
# Find ancestors of a GED individual (recursive via FAMC)
# ---------------------------------------------------------------------------
def ancestors_ged(ged_id, ged_inds, ged_fams):
    """Return set of all ancestor GED IDs (parents, grandparents, ...)."""
    result = set()
    queue = deque([ged_id])
    while queue:
        gid = queue.popleft()
        p = ged_inds.get(gid)
        if not p:
            continue
        for fid in p.get("famc", []):
            fam = ged_fams.get(fid)
            if not fam:
                continue
            for role in ("husb", "wife"):
                rid = fam.get(role)
                if rid and rid not in result:
                    result.add(rid)
                    queue.append(rid)
    return result


# ---------------------------------------------------------------------------
# Differences in matched pairs
# ---------------------------------------------------------------------------
def compute_differences(matched, pessoas, ged_inds):
    diffs = []
    for bd_id, info in matched.items():
        ged_id = info["ged_id"]
        bd_p = pessoas.get(bd_id)
        ged_p = ged_inds.get(ged_id)
        if not bd_p or not ged_p:
            continue

        diff_fields = []

        # Name
        bd_name = bd_person_name(bd_p)
        ged_name = ged_p["display_name"]
        if normalize(bd_name) != normalize(ged_name):
            diff_fields.append(("Nome", bd_name, ged_name))

        # Birth year
        bd_by = bd_birth_year(bd_p)
        ged_by = ged_p.get("birth_year")
        if bd_by and ged_by and bd_by != ged_by:
            diff_fields.append(("Ano nascimento", str(bd_by), str(ged_by)))

        # Birth date (full)
        bd_bd = (bd_p.get("nascimento") or {}).get("data", "") or ""
        ged_bd = ged_p.get("birth_date", "") or ""
        if bd_bd and ged_bd:
            # Normalize both to comparable form
            bd_bd_n = re.sub(r'[^0-9]', '', bd_bd)
            ged_bd_n = re.sub(r'[^0-9]', '', ged_bd)
            if bd_bd_n != ged_bd_n:
                diff_fields.append(("Data nascimento", bd_bd, ged_bd))

        # Death year
        bd_dy = year_from_date((bd_p.get("obito") or {}).get("data", ""))
        ged_dy = ged_p.get("death_year")
        if bd_dy and ged_dy and bd_dy != ged_dy:
            diff_fields.append(("Ano óbito", str(bd_dy), str(ged_dy)))

        if diff_fields:
            diffs.append({
                "bd_id": bd_id,
                "ged_id": ged_id,
                "bd_name": bd_name,
                "ged_name": ged_name,
                "confidence": info["confidence"],
                "diffs": diff_fields
            })

    return diffs


# ---------------------------------------------------------------------------
# GED parent names helper
# ---------------------------------------------------------------------------
def ged_parent_names(ged_id, ged_inds, ged_fams):
    p = ged_inds.get(ged_id)
    if not p:
        return "", ""
    for fid in p.get("famc", []):
        fam = ged_fams.get(fid)
        if not fam:
            continue
        husb = ged_inds.get(fam.get("husb", "")) if fam.get("husb") else None
        wife = ged_inds.get(fam.get("wife", "")) if fam.get("wife") else None
        pai = husb["display_name"] if husb else ""
        mae = wife["display_name"] if wife else ""
        return pai, mae
    return "", ""


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------
HTML_STYLE = """
body { font-family: Georgia, serif; max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; color: #222; background: #fafaf8; }
h1 { color: #5a3010; border-bottom: 3px solid #c8a060; padding-bottom: .5rem; }
h2 { color: #5a3010; border-left: 5px solid #c8a060; padding-left: .8rem; margin-top: 2.5rem; }
h3 { color: #444; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: .9rem; }
th { background: #c8a060; color: #fff; padding: .5rem .7rem; text-align: left; }
td { padding: .4rem .7rem; border-bottom: 1px solid #e0d5c0; vertical-align: top; }
tr:nth-child(even) td { background: #f4ede0; }
.badge-alto { background: #2a7a2a; color: #fff; padding: 1px 7px; border-radius: 10px; font-size: .8rem; }
.badge-medio { background: #b07a00; color: #fff; padding: 1px 7px; border-radius: 10px; font-size: .8rem; }
.badge-baixo { background: #b03030; color: #fff; padding: 1px 7px; border-radius: 10px; font-size: .8rem; }
.badge-incerto { background: #888; color: #fff; padding: 1px 7px; border-radius: 10px; font-size: .8rem; }
.summary-box { background: #fff8ee; border: 1px solid #c8a060; border-radius: 8px; padding: 1rem 1.5rem; margin: 1rem 0; }
.summary-box dl { display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1.5rem; margin: 0; }
.summary-box dt { font-weight: bold; color: #5a3010; }
.ok { color: #2a7a2a; font-weight: bold; }
.warn { color: #b03030; font-weight: bold; }
"""

def html_badge(conf):
    c = {"ALTO": "alto", "MÉDIO": "medio", "BAIXO": "baixo", "INCERTO": "incerto"}.get(conf, "baixo")
    return f'<span class="badge-{c}">{conf}</span>'


def escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_html(stats, validation, new_high, new_uncertain, diffs):
    sections = []

    # ---- 1. Resumo ----
    s = ['<div class="summary-box"><dl>']
    for k, v in stats.items():
        s.append(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>")
    s.append("</dl></div>")
    s.append("""<p><strong>Método:</strong> Correspondência BFS com âncora confirmada (I0007 ↔ @I1@: Francisco Franquinho, 1859).
    A partir da âncora, percorre recursivamente familiares na BD (via ficheiros de famílias) e no GED (FAMC/FAMS),
    tentando associar por: primeiro nome normalizado igual <em>ou</em> similaridade ≥ 0,8 (SequenceMatcher),
    e compatibilidade de ano de nascimento ±3 anos.
    Antepassados de Alexandrina (@I158@) foram excluídos da análise de novos.</p>""")
    sections.append(("<h2>1. Resumo</h2>", "\n".join(s)))

    # ---- 2. Validação I1035 ----
    vmark = '<span class="ok">✓ ASSOCIADA</span>' if validation["matched"] else '<span class="warn">✗ NÃO ASSOCIADA</span>'
    v = [f"<p>Pessoa I1035 na BD — {vmark}</p>"]
    for line in validation["details"]:
        v.append(f"<p>{escape(line)}</p>")
    sections.append(("<h2>2. Validação I1035 (Carina)</h2>", "\n".join(v)))

    # ---- 3. Novos (alta confiança) ----
    if new_high:
        rows = []
        for p in sorted(new_high, key=lambda x: x["name"]):
            pai, mae = p.get("pai", ""), p.get("mae", "")
            rows.append(
                f"<tr><td>{escape(p['id'])}</td><td>{escape(p['name'])}</td>"
                f"<td>{escape(p['sex'])}</td>"
                f"<td>{escape(p['birth_date'])} {escape(p['birth_place'])}</td>"
                f"<td>{escape(p['death_date'])} {escape(p['death_place'])}</td>"
                f"<td>{escape(pai)}</td><td>{escape(mae)}</td></tr>"
            )
        tbl = ("<table><thead><tr><th>ID GED</th><th>Nome</th><th>Sexo</th>"
               "<th>Nascimento</th><th>Óbito</th><th>Pai</th><th>Mãe</th></tr></thead><tbody>"
               + "".join(rows) + "</tbody></table>")
        sections.append((f"<h2>3. Indivíduos novos — alta confiança ({len(new_high)})</h2>", tbl))
    else:
        sections.append(("<h2>3. Indivíduos novos — alta confiança</h2>", "<p>Nenhum encontrado.</p>"))

    # ---- 4. Novos (incertos) ----
    if new_uncertain:
        rows = []
        for p in sorted(new_uncertain, key=lambda x: x["name"]):
            pai, mae = p.get("pai", ""), p.get("mae", "")
            rows.append(
                f"<tr><td>{escape(p['id'])}</td><td>{escape(p['name'])}</td>"
                f"<td>{escape(p['sex'])}</td>"
                f"<td>{escape(p['birth_date'])} {escape(p['birth_place'])}</td>"
                f"<td>{escape(p['death_date'])} {escape(p['death_place'])}</td>"
                f"<td>{escape(pai)}</td><td>{escape(mae)}</td>"
                f"<td>{html_badge('INCERTO')}</td></tr>"
            )
        tbl = ("<table><thead><tr><th>ID GED</th><th>Nome</th><th>Sexo</th>"
               "<th>Nascimento</th><th>Óbito</th><th>Pai</th><th>Mãe</th><th></th></tr></thead><tbody>"
               + "".join(rows) + "</tbody></table>")
        sections.append((f"<h2>4. Indivíduos novos — incertos ({len(new_uncertain)})</h2>", tbl))
    else:
        sections.append(("<h2>4. Indivíduos novos — incertos</h2>", "<p>Nenhum encontrado.</p>"))

    # ---- 5. Diferenças em existentes ----
    if diffs:
        rows = []
        for d in sorted(diffs, key=lambda x: x["bd_id"]):
            field_rows = "".join(
                f"<tr><td>{escape(f)}</td><td>{escape(v1)}</td><td>{escape(v2)}</td></tr>"
                for f, v1, v2 in d["diffs"]
            )
            inner = (f"<table style='width:100%;font-size:.85rem'>"
                     f"<tr><th>Campo</th><th>BD</th><th>GED</th></tr>{field_rows}</table>")
            rows.append(
                f"<tr><td>{escape(d['bd_id'])}</td><td>{escape(d['ged_id'])}</td>"
                f"<td>{escape(d['bd_name'])}</td><td>{escape(d['ged_name'])}</td>"
                f"<td>{html_badge(d['confidence'])}</td><td>{inner}</td></tr>"
            )
        tbl = ("<table><thead><tr><th>ID BD</th><th>ID GED</th><th>Nome BD</th>"
               "<th>Nome GED</th><th>Confiança</th><th>Diferenças</th></tr></thead><tbody>"
               + "".join(rows) + "</tbody></table>")
        sections.append((f"<h2>5. Diferenças em existentes ({len(diffs)})</h2>", tbl))
    else:
        sections.append(("<h2>5. Diferenças em existentes</h2>", "<p>Nenhuma diferença relevante encontrada.</p>"))

    # Build full HTML
    body_parts = []
    for heading, content in sections:
        body_parts.append(heading + "\n" + content)

    today = date.today().strftime("%d/%m/%Y")
    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório GED vs BD — {today}</title>
<style>{HTML_STYLE}</style>
</head>
<body>
<h1>Comparação GEDCOM vs Base de Dados</h1>
<p style="color:#666;font-size:.9rem">Gerado em {today} · Método: BFS com âncora e contexto familiar</p>
{"".join(body_parts)}
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("A carregar GED...", flush=True)
    ged_inds, ged_fams = parse_ged(GED_FILE)
    print(f"  {len(ged_inds)} indivíduos, {len(ged_fams)} famílias no GED")

    print("A carregar BD...", flush=True)
    pessoas, familias = load_bd()
    print(f"  {len(pessoas)} pessoas, {len(familias)} famílias na BD")

    # ---- Passo 1: Âncora ----
    print("Âncora: I0007 (Francisco Franquinho, 1859) ↔ @I1@ (GED)")
    anchor_bd = "I0007"
    anchor_ged = "I1"

    # ---- Passo 2: BFS ----
    print("A executar BFS...", flush=True)
    matched, matched_rev = bfs_match(anchor_bd, anchor_ged, pessoas, familias, ged_inds, ged_fams)
    print(f"  {len(matched)} pares BD↔GED encontrados")

    # ---- Passo 3: Excluir antepassados de Alexandrina ----
    alexandrina_ged = "I158"
    alex_ancestors = ancestors_ged(alexandrina_ged, ged_inds, ged_fams)
    alex_ancestors.add(alexandrina_ged)
    print(f"  {len(alex_ancestors)} antepassados de Alexandrina excluídos (incl. ela própria)")

    # ---- Passo 4: Validação I1035 ----
    validation = {"matched": False, "details": []}
    if "I1035" in matched:
        validation["matched"] = True
        ged_id = matched["I1035"]["ged_id"]
        conf = matched["I1035"]["confidence"]
        ged_p = ged_inds.get(ged_id, {})
        validation["details"] = [
            f"I1035 na BD (apelido: Franquinho Rainho, nasc. 1978) foi associada a @{ged_id}@ no GED.",
            f"Nome no GED: {ged_p.get('display_name', '?')}",
            f"Nascimento GED: {ged_p.get('birth_date', '?')} {ged_p.get('birth_place', '')}",
            f"Confiança: {conf}",
        ]
    else:
        # Manual search
        validation["details"].append("I1035 não foi associada por BFS. A procurar manualmente no GED...")
        # I1035 is protected, apelido="Franquinho Rainho", born 1978
        # Search by apelido tokens and year
        candidates = []
        for gid, gp in ged_inds.items():
            if gid in matched_rev:
                continue
            name_n = normalize(gp["display_name"])
            if "franquinho" in name_n or "rainho" in name_n:
                bd_year = 1978
                gy = gp.get("birth_year")
                if gy is None or abs(gy - bd_year) <= 5:
                    candidates.append(gid)
        if candidates:
            for cid in candidates:
                gp = ged_inds[cid]
                validation["details"].append(
                    f"  Candidato GED @{cid}@: {gp['display_name']} "
                    f"(nasc. {gp.get('birth_date','?')} {gp.get('birth_place','')})"
                )
            validation["details"].append(
                "NOTA: I1035 é pessoa protegida (nome='Familiar') — a correspondência por BFS é difícil "
                "pois o nome próprio não está disponível. Verificação manual acima mostra candidatos plausíveis."
            )
        else:
            validation["details"].append(
                "  Nenhum candidato directo encontrado por apelido. "
                "I1035 é protegida (nome='Familiar'), impossível associar automaticamente."
            )

    # ---- Passo 5: Classificar não-associados no GED ----
    new_high = []
    new_uncertain = []

    for ged_id, gp in ged_inds.items():
        if ged_id in matched_rev:
            continue
        if ged_id in alex_ancestors:
            continue

        pai_name, mae_name = ged_parent_names(ged_id, ged_inds, ged_fams)

        rec = {
            "id": ged_id,
            "name": gp["display_name"],
            "sex": gp.get("sex", "?"),
            "birth_date": gp.get("birth_date", ""),
            "birth_place": gp.get("birth_place", ""),
            "death_date": gp.get("death_date", ""),
            "death_place": gp.get("death_place", ""),
            "pai": pai_name,
            "mae": mae_name,
        }

        # Classify: uncertain if no birth date and no family links
        has_date = bool(gp.get("birth_year") or gp.get("death_year"))
        has_family = bool(gp.get("fams") or gp.get("famc"))
        name_parts = normalize(gp["display_name"]).split()
        has_surname = len(name_parts) > 1

        if has_date and (has_family or has_surname):
            new_high.append(rec)
        else:
            new_uncertain.append(rec)

    print(f"  {len(new_high)} novos (alta confiança), {len(new_uncertain)} novos (incertos) no GED")

    # ---- Diferenças ----
    diffs = compute_differences(matched, pessoas, ged_inds)
    print(f"  {len(diffs)} pares com diferenças de campos")

    # ---- Stats ----
    conf_counts = {}
    for v in matched.values():
        c = v["confidence"]
        conf_counts[c] = conf_counts.get(c, 0) + 1

    stats = {
        "Indivíduos no GED": len(ged_inds),
        "Pessoas na BD": len(pessoas),
        "Pares associados (total)": len(matched),
        "  — Alta confiança": conf_counts.get("ALTO", 0),
        "  — Confiança média": conf_counts.get("MÉDIO", 0),
        "  — Baixa confiança": conf_counts.get("BAIXO", 0),
        "Antepassados Alexandrina excluídos": len(alex_ancestors),
        "Novos no GED (alta confiança)": len(new_high),
        "Novos no GED (incertos)": len(new_uncertain),
        "Pares com diferenças de campos": len(diffs),
    }

    # ---- Generate HTML ----
    print("A gerar HTML...", flush=True)
    html = generate_html(stats, validation, new_high, new_uncertain, diffs)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Relatório guardado em: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()

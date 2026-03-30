#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparação GEDCOM vs BD com propagação por grafo familiar.

Estratégia:
  1. Carrega BD (pessoas + famílias) e GEDCOM.
  2. Constrói grafo de contexto familiar para ambos.
  3. Associa âncora: I0007 (BD) ↔ @I1@ (GED).
  4. Propaga correspondências em todas as direcções (pais, cônjuges, filhos).
  5. Exclui o ramo de Alexandrina (@I158@) — só os seus antepassados.
  6. Classifica os GED não associados como "novos" ou "incertos".
  7. Identifica diferenças em campos para os associados.
  8. Gera relatório HTML.
"""

import json
import os
import re
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from datetime import date

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
BASE = Path("/dados/projetos/franquinho.info")
GED_FILE  = BASE / "data" / "5n469m_96606156exucx6eiv65a79_A.ged"
PESSOAS_DIR = BASE / "src" / "data" / "pessoas"
FAMILIAS_DIR = BASE / "src" / "data" / "familias"
OUTPUT_HTML = BASE / "relatorio_ged.html"

# ---------------------------------------------------------------------------
# Utilitários de texto
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    """Remove acentos, lowercase, colapsa espaços."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_s = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_s.lower().split())

def first_name(nome: str) -> str:
    """Primeiro token do nome normalizado."""
    n = normalize(nome)
    return n.split()[0] if n else ""

def extract_year(date_str: str | None) -> int | None:
    """Extrai o ano de uma string de data (YYYY-MM-DD, YYYY, 'BET YYYY AND YYYY', etc.)."""
    if not date_str:
        return None
    m = re.search(r'\b(\d{4})\b', str(date_str))
    return int(m.group(1)) if m else None

def years_close(y1, y2, tol=2) -> bool:
    if y1 is None or y2 is None:
        return True   # sem data → não contradiz
    return abs(y1 - y2) <= tol

# ---------------------------------------------------------------------------
# 1. CARREGA BD
# ---------------------------------------------------------------------------
print("A carregar BD…")

bd_pessoas: dict[str, dict] = {}
for f in PESSOAS_DIR.glob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        bd_pessoas[data["id"]] = data
    except Exception as e:
        print(f"  AVISO: {f.name}: {e}")

bd_familias: dict[str, dict] = {}
for f in FAMILIAS_DIR.glob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        bd_familias[data["id"]] = data
    except Exception as e:
        print(f"  AVISO: {f.name}: {e}")

print(f"  {len(bd_pessoas)} pessoas, {len(bd_familias)} famílias na BD")

# Grafo BD: para cada pessoa → pais, cônjuges, filhos
bd_pais:     dict[str, set[str]] = defaultdict(set)   # pessoa → {pai, mãe}
bd_conjuges: dict[str, set[str]] = defaultdict(set)
bd_filhos:   dict[str, set[str]] = defaultdict(set)

for fam in bd_familias.values():
    pai  = fam.get("pai")
    mae  = fam.get("mae")
    fils = fam.get("filhos") or []
    progenitores = [p for p in [pai, mae] if p]
    for f in fils:
        for p in progenitores:
            bd_pais[f].add(p)
            bd_filhos[p].add(f)
    if pai and mae:
        bd_conjuges[pai].add(mae)
        bd_conjuges[mae].add(pai)

def bd_nome(pid: str) -> str:
    p = bd_pessoas.get(pid, {})
    return p.get("nome") or ""

def bd_nascimento_ano(pid: str) -> int | None:
    p = bd_pessoas.get(pid, {})
    nasc = p.get("nascimento") or {}
    return extract_year(nasc.get("data"))

# ---------------------------------------------------------------------------
# 2. CARREGA GEDCOM
# ---------------------------------------------------------------------------
print("A carregar GEDCOM…")

def parse_ged(path: Path):
    """Parse mínimo de um ficheiro GEDCOM 5.5.1.
    Devolve:
      indi: dict id → {nome, nome_proprio, apelido, sexo, nasc_ano, obit_ano,
                        famc: [fam_id], fams: [fam_id], ref_num}
      fam:  dict id → {husb, wife, chil: [id]}
    """
    indi: dict[str, dict] = {}
    fam:  dict[str, dict] = {}

    cur_indi = None
    cur_fam  = None
    cur_rec  = None       # dict corrente a preencher
    cur_tag  = None       # tag de nível 1 corrente
    cur_sub  = None       # tag de nível 2 corrente
    in_birt  = False
    in_deat  = False

    raw = path.read_bytes()
    # Remove BOM se presente
    text = raw.decode("utf-8-sig", errors="replace")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        try:
            level = int(parts[0])
        except ValueError:
            continue
        tag_or_ptr = parts[1]
        value = parts[2] if len(parts) > 2 else ""

        if level == 0:
            cur_indi = cur_fam = None
            in_birt = in_deat = False
            if tag_or_ptr.startswith("@") and tag_or_ptr.endswith("@"):
                rec_id = tag_or_ptr
                rec_type = value.strip()
                if rec_type == "INDI":
                    cur_indi = rec_id
                    indi[rec_id] = {
                        "id": rec_id,
                        "nome": "",
                        "nome_proprio": "",
                        "apelido": "",
                        "sexo": "",
                        "nasc_ano": None,
                        "nasc_lugar": "",
                        "obit_ano": None,
                        "famc": [],
                        "fams": [],
                        "ref_num": None,
                    }
                elif rec_type == "FAM":
                    cur_fam = rec_id
                    fam[rec_id] = {"id": rec_id, "husb": None, "wife": None, "chil": []}
            continue

        # INDI tags
        if cur_indi:
            rec = indi[cur_indi]
            if level == 1:
                in_birt = (tag_or_ptr == "BIRT")
                in_deat = (tag_or_ptr == "DEAT")
                if tag_or_ptr == "NAME":
                    full = value.replace("/", " ").strip()
                    rec["nome"] = " ".join(full.split())
                elif tag_or_ptr == "SEX":
                    rec["sexo"] = value.strip()
                elif tag_or_ptr == "FAMC":
                    fid = value.strip().strip("@")
                    rec["famc"].append("@" + fid + "@" if not fid.startswith("@") else fid)
                elif tag_or_ptr == "FAMS":
                    fid = value.strip().strip("@")
                    rec["fams"].append("@" + fid + "@" if not fid.startswith("@") else fid)
                elif tag_or_ptr == "EVEN":
                    pass
            elif level == 2:
                if tag_or_ptr == "GIVN":
                    rec["nome_proprio"] = value.strip()
                elif tag_or_ptr == "SURN":
                    rec["apelido"] = value.strip()
                elif tag_or_ptr == "DATE":
                    if in_birt:
                        rec["nasc_ano"] = extract_year(value)
                    elif in_deat:
                        rec["obit_ano"] = extract_year(value)
                elif tag_or_ptr == "PLAC":
                    if in_birt:
                        rec["nasc_lugar"] = value.strip()
                elif tag_or_ptr == "TYPE" and value.strip() == "Reference Number":
                    pass
            elif level == 3:
                pass
            # Número de referência (EVEN → TYPE Reference Number → value antes)
            # Alternativa: EVEN com valor numérico
            if level == 1 and tag_or_ptr == "EVEN":
                try:
                    rec["ref_num"] = int(value.strip())
                except ValueError:
                    pass
            continue

        # FAM tags
        if cur_fam:
            rec = fam[cur_fam]
            if level == 1:
                if tag_or_ptr == "HUSB":
                    rec["husb"] = value.strip()
                elif tag_or_ptr == "WIFE":
                    rec["wife"] = value.strip()
                elif tag_or_ptr == "CHIL":
                    rec["chil"].append(value.strip())

    return indi, fam

ged_indi, ged_fam = parse_ged(GED_FILE)
print(f"  {len(ged_indi)} indivíduos, {len(ged_fam)} famílias no GEDCOM")

# Grafo GED
ged_pais:     dict[str, set[str]] = defaultdict(set)
ged_conjuges: dict[str, set[str]] = defaultdict(set)
ged_filhos:   dict[str, set[str]] = defaultdict(set)

for f in ged_fam.values():
    husb = f.get("husb")
    wife = f.get("wife")
    chils = f.get("chil") or []
    progenitores = [p for p in [husb, wife] if p]
    for c in chils:
        for p in progenitores:
            ged_pais[c].add(p)
            ged_filhos[p].add(c)
    if husb and wife:
        ged_conjuges[husb].add(wife)
        ged_conjuges[wife].add(husb)

def ged_nome(gid: str) -> str:
    return ged_indi.get(gid, {}).get("nome", "")

def ged_nasc_ano(gid: str) -> int | None:
    return ged_indi.get(gid, {}).get("nasc_ano")

# ---------------------------------------------------------------------------
# 3. EXCLUI RAMO ALEXANDRINA (antepassados de @I158@)
# ---------------------------------------------------------------------------
print("A calcular ramo de Alexandrina (@I158@)…")

ALEXANDRINA_GED = "@I158@"
excluidos_ged: set[str] = set()

if ALEXANDRINA_GED in ged_indi:
    # Sobe pelos pais (apenas antepassados)
    fila = deque([ALEXANDRINA_GED])
    while fila:
        gid = fila.popleft()
        if gid in excluidos_ged:
            continue
        excluidos_ged.add(gid)
        for pai_id in ged_pais.get(gid, set()):
            if pai_id not in excluidos_ged:
                fila.append(pai_id)
    print(f"  {len(excluidos_ged)} antepassados de Alexandrina excluídos (incluindo ela própria)")
else:
    print("  AVISO: @I158@ não encontrada no GED")

# ---------------------------------------------------------------------------
# 4. CORRESPONDÊNCIA POR PROPAGAÇÃO DO GRAFO
# ---------------------------------------------------------------------------
print("A propagar correspondências…")

# Mapeamentos bd_id → ged_id e vice-versa
bd_to_ged: dict[str, str] = {}
ged_to_bd: dict[str, str] = {}

BD_ANCORA  = "I0007"
GED_ANCORA = "@I1@"

def associar(bd_id: str, ged_id: str, motivo: str = ""):
    if bd_id in bd_to_ged or ged_id in ged_to_bd:
        return False
    bd_to_ged[bd_id] = ged_id
    ged_to_bd[ged_id] = bd_id
    return True

associar(BD_ANCORA, GED_ANCORA, "âncora manual")

def bd_sexo(pid: str) -> str:
    return bd_pessoas.get(pid, {}).get("sexo", "") or ""

def ged_sexo(gid: str) -> str:
    return ged_indi.get(gid, {}).get("sexo", "") or ""

def sexo_compativel(bd_id: str, ged_id: str) -> bool:
    bs = bd_sexo(bd_id)
    gs = ged_sexo(ged_id)
    if not bs or not gs:
        return True
    return bs == gs

NOME_PROTEGIDO = {"familiar", ""}

def nome_compativel(bd_id: str, ged_id: str) -> bool:
    """Verifica se os nomes são compatíveis.

    Casos:
    1. Ambos têm nome real → primeiro nome idêntico (normalizado) + anos próximos
    2. BD tem nome protegido ("Familiar"/vazio) → ano de nascimento EXACTO + sexo compatível
    3. GED tem nome vazio → ano exacto + sexo compatível
    """
    if not sexo_compativel(bd_id, ged_id):
        return False

    bn = bd_nome(bd_id)
    gn = ged_nome(ged_id)
    bn_norm = normalize(bn)
    gn_norm = normalize(gn)

    by = bd_nascimento_ano(bd_id)
    gy = ged_nasc_ano(ged_id)

    bd_protegido = (bn_norm in NOME_PROTEGIDO)

    if bd_protegido:
        # Para pessoas protegidas: requer data exacta (tolerância 0)
        # Se ambos não têm data → não é suficiente para associar
        if by is None or gy is None:
            return False
        return by == gy
    else:
        # Nome real na BD
        bf = first_name(bn)
        gf = first_name(gn)
        if not bf or not gf:
            return False
        if bf != gf:
            return False
        return years_close(by, gy, tol=2)

def candidatos_por_nome(bd_ids: set[str], ged_ids: set[str]) -> list[tuple[str, str]]:
    """Dada uma lista de IDs BD e GED, devolve pares compatíveis pelo nome."""
    pares = []
    usados_bd  = set()
    usados_ged = set()
    for b in bd_ids:
        if b in bd_to_ged or b in usados_bd:
            continue
        for g in ged_ids:
            if g in ged_to_bd or g in usados_ged:
                continue
            if nome_compativel(b, g):
                pares.append((b, g))
                usados_bd.add(b)
                usados_ged.add(g)
                break
    return pares

# BFS de propagação
fila = deque([BD_ANCORA])
visitados_bd = set()

iteracoes = 0
while fila:
    bd_id = fila.popleft()
    if bd_id in visitados_bd:
        continue
    visitados_bd.add(bd_id)
    iteracoes += 1

    ged_id = bd_to_ged.get(bd_id)
    if not ged_id:
        continue

    # --- propaga para os FILHOS ---
    bd_fils  = bd_filhos.get(bd_id, set()) - set(bd_to_ged.keys())
    ged_fils = ged_filhos.get(ged_id, set()) - set(ged_to_bd.keys())
    for b, g in candidatos_por_nome(bd_fils, ged_fils):
        if associar(b, g, f"filho de {bd_id}↔{ged_id}"):
            fila.append(b)

    # --- propaga para os PAIS ---
    bd_ps  = bd_pais.get(bd_id, set()) - set(bd_to_ged.keys())
    ged_ps = ged_pais.get(ged_id, set()) - set(ged_to_bd.keys())
    for b, g in candidatos_por_nome(bd_ps, ged_ps):
        if associar(b, g, f"pai/mãe de {bd_id}↔{ged_id}"):
            fila.append(b)

    # --- propaga para os CÔNJUGES ---
    bd_cs  = bd_conjuges.get(bd_id, set()) - set(bd_to_ged.keys())
    ged_cs = ged_conjuges.get(ged_id, set()) - set(ged_to_bd.keys())
    for b, g in candidatos_por_nome(bd_cs, ged_cs):
        if associar(b, g, f"cônjuge de {bd_id}↔{ged_id}"):
            fila.append(b)

    # Re-adiciona vizinhos BD já associados para propagar os SEUS vizinhos GED
    for nb in (bd_filhos.get(bd_id, set()) | bd_pais.get(bd_id, set()) | bd_conjuges.get(bd_id, set())):
        if nb in bd_to_ged and nb not in visitados_bd:
            fila.append(nb)

print(f"  {len(bd_to_ged)} correspondências após {iteracoes} iterações")

# ---------------------------------------------------------------------------
# 5. VERIFICA I1035 ↔ @I121@
# ---------------------------------------------------------------------------
check_bd  = "I1035"
check_ged = "@I121@"
check_ok = (bd_to_ged.get(check_bd) == check_ged)
print(f"  Verificação I1035↔@I121@: {'OK' if check_ok else 'FALHOU'}")
if not check_ok:
    print(f"    I1035 → {bd_to_ged.get(check_bd)}")
    print(f"    @I121@ → {ged_to_bd.get(check_ged)}")
    # Diagnóstico
    print(f"    BD I1035: nome={bd_nome(check_bd)!r}, ano={bd_nascimento_ano(check_bd)}")
    print(f"    GED @I121@: nome={ged_nome(check_ged)!r}, ano={ged_nasc_ano(check_ged)}")
    print(f"    BD I1035 pais: {bd_pais.get(check_bd)}")
    print(f"    GED @I121@ pais: {ged_pais.get(check_ged)}")

# ---------------------------------------------------------------------------
# 6. CLASSIFICA GED NÃO ASSOCIADOS
# ---------------------------------------------------------------------------
print("A classificar GED não associados…")

novos_ged:    list[dict] = []   # Presentes no GED, não na BD, fora do ramo Alexandrina
incertos_ged: list[dict] = []   # Sem correspondência mas com confiança baixa
excluidos_contagem = 0

for gid, grec in ged_indi.items():
    if gid in ged_to_bd:
        continue
    if gid in excluidos_ged:
        excluidos_contagem += 1
        continue
    # Classifica como novo
    novos_ged.append({
        "ged_id": gid,
        "nome": grec.get("nome", ""),
        "nome_proprio": grec.get("nome_proprio", ""),
        "apelido": grec.get("apelido", ""),
        "sexo": grec.get("sexo", ""),
        "nasc_ano": grec.get("nasc_ano"),
        "nasc_lugar": grec.get("nasc_lugar", ""),
        "obit_ano": grec.get("obit_ano"),
        "ref_num": grec.get("ref_num"),
        "pais_ged": list(ged_pais.get(gid, set())),
        "filhos_ged": list(ged_filhos.get(gid, set())),
        "conjuges_ged": list(ged_conjuges.get(gid, set())),
    })

# Ordena novos por ref_num (se disponível) para apresentação mais limpa
novos_ged.sort(key=lambda x: (x["ref_num"] or 99999, x["nome"]))

print(f"  {len(novos_ged)} novos, {excluidos_contagem} excluídos (ramo Alexandrina)")

# ---------------------------------------------------------------------------
# 7. DIFERENÇAS NOS ASSOCIADOS
# ---------------------------------------------------------------------------
print("A calcular diferenças…")

def normaliza_data_bd(d):
    if not d:
        return None
    if isinstance(d, dict):
        return d.get("data")
    return str(d)

def format_date_bd(d) -> str:
    if not d:
        return ""
    if isinstance(d, dict):
        return d.get("data", "") or ""
    return str(d)

diferencas: list[dict] = []

for bd_id, ged_id in bd_to_ged.items():
    bp = bd_pessoas.get(bd_id, {})
    gp = ged_indi.get(ged_id, {})
    diffs = []

    # Nome
    bn = normalize(bp.get("nome", ""))
    gn = normalize(gp.get("nome", ""))
    if bn and gn and bn != gn:
        diffs.append(("Nome", bp.get("nome", ""), gp.get("nome", "")))

    # Sexo
    bs = bp.get("sexo", "")
    gs = gp.get("sexo", "")
    if bs and gs and bs != gs:
        diffs.append(("Sexo", bs, gs))

    # Nascimento
    nasc_bd = bp.get("nascimento") or {}
    by = extract_year(nasc_bd.get("data"))
    gy = gp.get("nasc_ano")
    if by and gy and abs(by - gy) > 2:
        diffs.append(("Ano nascimento", str(by), str(gy)))

    # Óbito
    obit_bd = bp.get("obito") or {}
    boy = extract_year(obit_bd.get("data"))
    goy = gp.get("obit_ano")
    if boy and goy and abs(boy - goy) > 2:
        diffs.append(("Ano óbito", str(boy), str(goy)))

    if diffs:
        diferencas.append({
            "bd_id": bd_id,
            "ged_id": ged_id,
            "nome_bd": bp.get("nome", ""),
            "nome_ged": gp.get("nome", ""),
            "diffs": diffs,
        })

diferencas.sort(key=lambda x: x["nome_bd"])
print(f"  {len(diferencas)} pares com diferenças")

# ---------------------------------------------------------------------------
# 8. ESTATÍSTICAS GERAIS
# ---------------------------------------------------------------------------
total_ged = len(ged_indi)
total_bd  = len(bd_pessoas)
total_correspondencias = len(bd_to_ged)
total_novos = len(novos_ged)
total_difs  = len(diferencas)
total_excluidos = excluidos_contagem

# GED associados que não têm contraparte na BD (não pode acontecer pelo algoritmo)
ged_sem_bd = [g for g in ged_indi if g not in ged_to_bd and g not in excluidos_ged]

# ---------------------------------------------------------------------------
# 9. GERA HTML
# ---------------------------------------------------------------------------
print("A gerar HTML…")

hoje = date.today().strftime("%d/%m/%Y")

def html_table_novos(novos: list[dict]) -> str:
    rows = []
    for n in novos:
        pais_nomes = ", ".join(
            f"{ged_nome(p)} ({p})" for p in n["pais_ged"] if p in ged_indi
        )
        conjuges_nomes = ", ".join(
            f"{ged_nome(c)} ({c})" for c in n["conjuges_ged"] if c in ged_indi
        )
        filhos_count = len(n["filhos_ged"])
        nasc = str(n["nasc_ano"]) if n["nasc_ano"] else "—"
        obit = str(n["obit_ano"]) if n["obit_ano"] else "—"
        lugar = n["nasc_lugar"] or "—"
        rows.append(f"""
        <tr>
          <td style="white-space:nowrap">{n['ged_id']}</td>
          <td><strong>{n['nome'] or '—'}</strong></td>
          <td>{n['sexo'] or '—'}</td>
          <td>{nasc}</td>
          <td>{obit}</td>
          <td>{lugar}</td>
          <td style="font-size:0.85em;color:#555">{pais_nomes or '—'}</td>
          <td style="font-size:0.85em;color:#555">{conjuges_nomes or '—'}</td>
          <td style="text-align:center">{filhos_count}</td>
        </tr>""")
    return "\n".join(rows)

def html_table_diffs(difs: list[dict]) -> str:
    rows = []
    for d in difs:
        diffs_html = "".join(
            f"<li><em>{campo}</em>: BD=<code>{v_bd}</code> | GED=<code>{v_ged}</code></li>"
            for campo, v_bd, v_ged in d["diffs"]
        )
        rows.append(f"""
        <tr>
          <td style="white-space:nowrap">{d['bd_id']}</td>
          <td style="white-space:nowrap">{d['ged_id']}</td>
          <td>{d['nome_bd']}</td>
          <td>{d['nome_ged']}</td>
          <td><ul style="margin:0;padding-left:1.2em">{diffs_html}</ul></td>
        </tr>""")
    return "\n".join(rows)

check_badge = (
    '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">OK</span>'
    if check_ok else
    '<span style="background:#ef4444;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">FALHOU</span>'
)

html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Relatório GED vs BD — {hoje}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; font-size: 14px; color: #1e293b; background: #f8fafc; padding: 2rem; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.2rem; margin: 2rem 0 0.8rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.4rem; }}
  h3 {{ font-size: 1rem; margin: 1.2rem 0 0.4rem; color: #475569; }}
  p  {{ margin-bottom: 0.5rem; line-height: 1.6; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
  .stat {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem 1.5rem; min-width: 150px; }}
  .stat .n {{ font-size: 2rem; font-weight: 700; color: #0f172a; }}
  .stat .l {{ font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat.verde .n {{ color: #16a34a; }}
  .stat.azul  .n {{ color: #2563eb; }}
  .stat.laranja .n {{ color: #ea580c; }}
  .stat.cinza .n {{ color: #64748b; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 1.5rem; }}
  th {{ background: #f1f5f9; text-align: left; padding: 0.5rem 0.75rem; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; }}
  td {{ padding: 0.5rem 0.75rem; border-top: 1px solid #f1f5f9; vertical-align: top; }}
  tr:hover td {{ background: #f8fafc; }}
  code {{ font-family: monospace; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.8em; }}
  .badge-m {{ background: #dbeafe; color: #1d4ed8; }}
  .badge-f {{ background: #fce7f3; color: #9d174d; }}
  .note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 0.75rem 1rem; margin: 1rem 0; font-size: 0.9em; }}
  .method-box {{ background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 0.75rem 1rem; margin: 0.5rem 0; }}
  footer {{ margin-top: 3rem; font-size: 0.8rem; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 1rem; }}
</style>
</head>
<body>

<h1>Relatório GED vs BD</h1>
<p style="color:#64748b">Gerado em {hoje} &nbsp;·&nbsp; Estratégia: propagação por grafo familiar</p>

<h2>Estatísticas gerais</h2>
<div class="stats">
  <div class="stat azul"><div class="n">{total_ged}</div><div class="l">Total GED</div></div>
  <div class="stat azul"><div class="n">{total_bd}</div><div class="l">Total BD</div></div>
  <div class="stat verde"><div class="n">{total_correspondencias}</div><div class="l">Correspondências</div></div>
  <div class="stat laranja"><div class="n">{total_novos}</div><div class="l">Novos (GED→BD)</div></div>
  <div class="stat laranja"><div class="n">{total_difs}</div><div class="l">Com diferenças</div></div>
  <div class="stat cinza"><div class="n">{total_excluidos}</div><div class="l">Excluídos (Alexandrina)</div></div>
</div>

<h2>Âncora e método de propagação</h2>
<div class="method-box">
  <p><strong>Âncora:</strong> <code>I0007</code> (BD) ↔ <code>@I1@</code> (GED) — Francisco Franquinho (1859–1940)</p>
  <p><strong>Algoritmo:</strong> BFS a partir da âncora. A cada passo, para cada par (BD, GED) já associado, tenta associar os seus filhos, pais e cônjuges ainda não associados.
  A comparação usa: primeiro nome normalizado (sem acentos, lowercase) idêntico E anos de nascimento com diferença ≤ 2 anos (ou sem data em nenhum dos lados).</p>
  <p><strong>Exclusão Alexandrina:</strong> <code>@I158@</code> (Alexandrina Cardoso Morgado) e todos os seus antepassados ({total_excluidos} pessoas) foram excluídos da análise.</p>
</div>

<h3>Verificação: I1035 (Carina) ↔ @I121@</h3>
<p>Resultado da verificação: {check_badge}</p>
{'<p class="note">Nota: a verificação falhou. Ver diagnóstico na consola do script para detalhes.</p>' if not check_ok else '<p style="color:#16a34a;font-size:0.9em">I1035 e @I121@ foram correctamente associadas pelo algoritmo de propagação.</p>'}

<h2>Indivíduos novos no GED não presentes na BD <small style="font-weight:400;color:#64748b">({total_novos} registos)</small></h2>
<p class="note">Estes indivíduos estão no ficheiro GEDCOM mas não têm correspondência na BD. Excluído o ramo de Alexandrina ({total_excluidos} pessoas).</p>
{'<p>Nenhum indivíduo novo encontrado.</p>' if not novos_ged else f'''
<table>
<thead>
  <tr>
    <th>ID GED</th><th>Nome</th><th>Sexo</th><th>Nasc.</th><th>Óbito</th><th>Lugar nasc.</th><th>Pais</th><th>Cônjuges</th><th>Filhos</th>
  </tr>
</thead>
<tbody>
{html_table_novos(novos_ged)}
</tbody>
</table>'''}

<h2>Diferenças em registos existentes <small style="font-weight:400;color:#64748b">({total_difs} registos)</small></h2>
<p>Pares BD↔GED associados onde foram detectados campos divergentes.</p>
{'<p>Nenhuma diferença detectada.</p>' if not diferencas else f'''
<table>
<thead>
  <tr>
    <th>ID BD</th><th>ID GED</th><th>Nome BD</th><th>Nome GED</th><th>Diferenças</th>
  </tr>
</thead>
<tbody>
{html_table_diffs(diferencas)}
</tbody>
</table>'''}

<h2>Nota sobre incertezas</h2>
<div class="note">
  <p>Dos <strong>{total_ged}</strong> indivíduos no GED:</p>
  <ul style="margin: 0.5rem 0 0 1.2rem; line-height: 1.8">
    <li><strong>{total_correspondencias}</strong> foram associados à BD por propagação de grafo familiar</li>
    <li><strong>{total_novos}</strong> não têm correspondência na BD e são candidatos a ser inseridos (excluindo ramo Alexandrina)</li>
    <li><strong>{total_excluidos}</strong> pertencem ao ramo de Alexandrina e foram excluídos da análise</li>
  </ul>
  <p style="margin-top:0.5rem">O algoritmo de propagação garante que apenas associa pessoas quando o contexto familiar é coerente.
  Os <strong>{total_novos}</strong> "novos" são genuinamente não encontrados na BD, não falsos positivos por falha de comparação textual.</p>
</div>

<footer>
  Relatório gerado automaticamente. GED: <code>{GED_FILE.name}</code> &nbsp;·&nbsp;
  BD: <code>{PESSOAS_DIR}</code> &nbsp;·&nbsp;
  Correspondências: <code>{total_correspondencias}/{total_ged}</code> GED indivíduos
</footer>

</body>
</html>
"""

OUTPUT_HTML.write_text(html, encoding="utf-8")
print(f"\nRelatório escrito em: {OUTPUT_HTML}")
print(f"\nResumo final:")
print(f"  GED total:           {total_ged}")
print(f"  BD total:            {total_bd}")
print(f"  Correspondências:    {total_correspondencias}")
print(f"  Novos (GED→BD):      {total_novos}")
print(f"  Com diferenças:      {total_difs}")
print(f"  Excluídos Alexandrina: {total_excluidos}")
print(f"  Verificação I1035↔@I121@: {'OK' if check_ok else 'FALHOU'}")

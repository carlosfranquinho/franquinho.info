#!/usr/bin/env python3
"""
gramps_to_json.py
Converte um ficheiro GrampsXML (.gramps, .gpkg ou .xml) para ficheiros JSON
usados pelo site Astro em src/data/.

Formatos suportados:
  .gramps  — XML comprimido em gzip
  .gpkg    — tar.gz com data.gramps + media (exportacao completa do Gramps)
  .xml     — XML descomprimido

Uso:
    python3 scripts/gramps_to_json.py [--input data/arvore.gpkg] [--output src/data]
"""

import argparse
import gzip
import re
import io
import json
import os
import sys
import tarfile
from datetime import date, datetime
from pathlib import Path
from lxml import etree

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

ANO_REFERENCIA = date.today().year

# ---------------------------------------------------------------------------
# Utilitários XML
# ---------------------------------------------------------------------------

NS = {'g': 'http://gramps-project.org/xml/1.7.1/'}

# Suporte a múltiplas versões de namespace Gramps
NAMESPACES_GRAMPS = [
    'http://gramps-project.org/xml/1.7.1/',
    'http://gramps-project.org/xml/1.7.0/',
    'http://gramps-project.org/xml/1.6.0/',
    'http://gramps-project.org/xml/1.5.1/',
    'http://gramps-project.org/xml/1.5.0/',
]


def detectar_namespace(root):
    """Detecta o namespace Gramps no elemento raiz."""
    tag = root.tag
    if tag.startswith('{'):
        ns = tag[1:tag.index('}')]
        return ns
    return ''


def ns(tag, namespace):
    if namespace:
        return f'{{{namespace}}}{tag}'
    return tag


def texto(el, xpath, namespace=''):
    """Devolve texto de um elemento filho, ou None."""
    if el is None:
        return None
    found = el.find(ns(xpath, namespace))
    if found is not None and found.text:
        return found.text.strip()
    return None


def atrib(el, nome, default=None):
    if el is None:
        return default
    return el.get(nome, default)


# ---------------------------------------------------------------------------
# Parsing de datas Gramps
# ---------------------------------------------------------------------------

def parse_data_gramps(el, namespace):
    """
    Extrai informação de data de um elemento <dateval>, <daterange> ou <datestr>.
    Devolve dict com campos: val, val_ano, val_mes, val_dia, qualidade, tipo
    """
    if el is None:
        return None

    dateval = el.find(ns('dateval', namespace))
    daterange = el.find(ns('daterange', namespace))
    datestr = el.find(ns('datestr', namespace))

    if dateval is not None:
        val = atrib(dateval, 'val', '')
        return {
            'val': val,
            'val_ano': _extrair_ano(val),
            'qualidade': atrib(dateval, 'quality', ''),
            'tipo': 'dateval',
        }
    if daterange is not None:
        inicio = atrib(daterange, 'start', '')
        fim = atrib(daterange, 'stop', '')
        return {
            'val': f'{inicio} – {fim}',
            'val_ano': _extrair_ano(inicio),
            'qualidade': atrib(daterange, 'quality', ''),
            'tipo': 'daterange',
        }
    if datestr is not None:
        val = atrib(datestr, 'val', '')
        return {
            'val': val,
            'val_ano': _extrair_ano_str(val),
            'qualidade': '',
            'tipo': 'datestr',
        }
    return None


def _extrair_ano(val):
    """Extrai ano de uma data no formato YYYY-MM-DD ou YYYY."""
    if not val:
        return None
    partes = val.split('-')
    try:
        ano = int(partes[0])
        return ano if 1000 <= ano <= 2200 else None
    except (ValueError, IndexError):
        return None


def _extrair_ano_str(val):
    """Tenta extrair ano de uma string de data livre."""
    import re
    m = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', val or '')
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Privacidade
# ---------------------------------------------------------------------------

def calcular_protegida(private):
    """Respeita directamente o flag de privacidade do Gramps."""
    return private


# ---------------------------------------------------------------------------
# Parsing de eventos
# ---------------------------------------------------------------------------

def parse_evento(handle, eventos_map, namespace):
    """Devolve dict com tipo, data, lugar_handle, media_handles para um evento pelo handle."""
    ev = eventos_map.get(handle)
    if ev is None:
        return None

    tipo_el = ev.find(ns('type', namespace))
    tipo = tipo_el.text.strip() if tipo_el is not None and tipo_el.text else ''

    data = parse_data_gramps(ev, namespace)

    lugar_ref = ev.find(ns('place', namespace))
    lugar_handle = atrib(lugar_ref, 'hlink')

    descricao_el = ev.find(ns('description', namespace))
    descricao = descricao_el.text.strip() if descricao_el is not None and descricao_el.text else None

    media_handles = extrair_media_refs(ev, namespace)

    return {
        'tipo': tipo,
        'data': data,
        'lugar_handle': lugar_handle,
        'descricao': descricao,
        'media_handles': media_handles,
    }


def extrair_eventos_pessoa(person_el, eventos_map, namespace):
    """Extrai todos os eventos de uma pessoa, organizados por tipo."""
    resultado = {}
    for evref in person_el.findall(ns('eventref', namespace)):
        handle = atrib(evref, 'hlink')
        role = atrib(evref, 'role', 'Primary')
        if role != 'Primary':
            continue
        ev = parse_evento(handle, eventos_map, namespace)
        if ev:
            tipo = ev['tipo'].lower()
            resultado[tipo] = ev
    return resultado


# ---------------------------------------------------------------------------
# Parsing de notas
# ---------------------------------------------------------------------------

def extrair_notas(el, notas_map, namespace):
    notas = []
    for noteref in el.findall(ns('noteref', namespace)):
        handle = atrib(noteref, 'hlink')
        nota_el = notas_map.get(handle)
        if nota_el is not None:
            texto_el = nota_el.find(ns('text', namespace))
            if texto_el is not None and texto_el.text:
                tipo_el = nota_el.find(ns('type', namespace))
                tipo = tipo_el.text.strip() if tipo_el is not None and tipo_el.text else ''
                notas.append({
                    'tipo': tipo,
                    'texto': texto_el.text.strip(),
                })
    return notas


# ---------------------------------------------------------------------------
# Parsing de fontes e citações
# ---------------------------------------------------------------------------

def extrair_citacoes(el, citacoes_map, fontes_map, namespace):
    citacoes = []
    for citref in el.findall(ns('citationref', namespace)):
        handle = atrib(citref, 'hlink')
        cit_el = citacoes_map.get(handle)
        if cit_el is None:
            continue
        fonte_ref = cit_el.find(ns('sourceref', namespace))
        fonte_handle = atrib(fonte_ref, 'hlink')
        fonte_el = fontes_map.get(fonte_handle)

        pagina_el = cit_el.find(ns('page', namespace))
        pagina = pagina_el.text.strip() if pagina_el is not None and pagina_el.text else None

        titulo_fonte = None
        if fonte_el is not None:
            titulo_el = fonte_el.find(ns('stitle', namespace))
            titulo_fonte = titulo_el.text.strip() if titulo_el is not None and titulo_el.text else None

        citacoes.append({
            'fonte': titulo_fonte,
            'pagina': pagina,
        })
    return citacoes


# ---------------------------------------------------------------------------
# Parsing de media
# ---------------------------------------------------------------------------

def extrair_media_refs(el, namespace):
    refs = []
    for objref in el.findall(ns('objref', namespace)):
        handle = atrib(objref, 'hlink')
        if handle:
            refs.append(handle)
    return refs


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

def abrir_gramps(caminho):
    """
    Abre ficheiro .gramps (gzip), .gpkg (tar.gz com data.gramps) ou .xml
    e devolve (root_element, tar_archive_ou_None).
    O tar é devolvido para que processar_media possa extrair ficheiros de media.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        sys.exit(f'Erro: ficheiro nao encontrado: {caminho}')

    sufixo = caminho.suffix.lower()

    # .gpkg — tar.gz contendo data.gramps + media
    if sufixo == '.gpkg':
        with gzip.open(caminho, 'rb') as f:
            conteudo_tar = f.read()
        tar = tarfile.open(fileobj=io.BytesIO(conteudo_tar))
        # Encontrar o ficheiro .gramps dentro do tar
        gramps_entry = next(
            (m for m in tar.getmembers() if m.name.endswith('.gramps')),
            None
        )
        if gramps_entry is None:
            sys.exit('Erro: nao foi encontrado ficheiro .gramps dentro do .gpkg')
        gramps_bytes = tar.extractfile(gramps_entry).read()
        # O .gramps dentro do .gpkg pode ser gzip ou XML directo
        try:
            xml_bytes = gzip.decompress(gramps_bytes)
        except gzip.BadGzipFile:
            xml_bytes = gramps_bytes
        return etree.fromstring(xml_bytes), tar

    # .gramps — gzip directo
    try:
        with gzip.open(caminho, 'rb') as f:
            conteudo = f.read()
        return etree.fromstring(conteudo), None
    except (gzip.BadGzipFile, OSError):
        pass

    # .xml — descomprimido
    return etree.parse(str(caminho)).getroot(), None


def construir_mapas(root, namespace):
    """Indexa todos os elementos por handle para lookup O(1)."""
    def indexar(tag):
        return {atrib(el, 'handle'): el for el in root.iter(ns(tag, namespace))}

    return {
        'pessoas': indexar('person'),
        'familias': indexar('family'),
        'eventos': indexar('event'),
        'lugares': indexar('placeobj'),
        'media': indexar('object'),
        'notas': indexar('note'),
        'citacoes': indexar('citation'),
        'fontes': indexar('source'),
    }


def handle_para_id(mapas, tipo, handle):
    """Converte handle interno para o ID público Gramps (ex: I0001)."""
    el = mapas[tipo].get(handle)
    if el is None:
        return None
    return atrib(el, 'id')


# ---------------------------------------------------------------------------
# Converter pessoa
# ---------------------------------------------------------------------------

def converter_pessoa(person_el, mapas, namespace):
    handle = atrib(person_el, 'handle')
    gramps_id = atrib(person_el, 'id')
    private = atrib(person_el, 'priv', '0') == '1'

    def parse_apelidos(nome_el):
        """
        Lê todos os elementos <surname> com prefixo opcional.
        Ex: <surname prefix="da">Silva</surname><surname>Franquinho</surname>
        → "da Silva Franquinho"
        Devolve (apelido_completo_str, apelido_primario_str).
        """
        partes_apelido = []
        prim_apelido = None
        for sur in nome_el.findall(ns('surname', namespace)):
            texto = sur.text.strip() if sur.text else ''
            if not texto:
                continue
            prefixo = atrib(sur, 'prefix', '').strip()
            parte = f'{prefixo} {texto}'.strip() if prefixo else texto
            partes_apelido.append(parte)
            if atrib(sur, 'prim', '0') == '1' or prim_apelido is None:
                prim_apelido = parte
        return ' '.join(partes_apelido) if partes_apelido else None, prim_apelido

    # Nome principal
    nome_el = person_el.find(ns('name', namespace))
    nome_completo = None
    nome_proprio = None
    apelido = None
    if nome_el is not None:
        primeiro_el = nome_el.find(ns('first', namespace))
        nome_proprio = primeiro_el.text.strip() if primeiro_el is not None and primeiro_el.text else None
        apelido, _ = parse_apelidos(nome_el)
        partes = [p for p in [nome_proprio, apelido] if p]
        nome_completo = ' '.join(partes) if partes else None

    # Nome alternativo
    nomes_alt = []
    for nome_alt_el in person_el.findall(ns('name', namespace)):
        tipo_nome = atrib(nome_alt_el, 'type', '')
        if tipo_nome and tipo_nome != 'Birth Name':
            primeiro_el = nome_alt_el.find(ns('first', namespace))
            apelido_alt, _ = parse_apelidos(nome_alt_el)
            partes = []
            if primeiro_el is not None and primeiro_el.text:
                partes.append(primeiro_el.text.strip())
            if apelido_alt:
                partes.append(apelido_alt)
            if partes:
                nomes_alt.append({'tipo': tipo_nome, 'nome': ' '.join(partes)})

    # Sexo
    sexo_el = person_el.find(ns('gender', namespace))
    sexo_raw = sexo_el.text.strip().upper() if sexo_el is not None and sexo_el.text else 'U'
    sexo_map = {'MALE': 'M', 'FEMALE': 'F', 'UNKNOWN': 'U', 'M': 'M', 'F': 'F'}
    sexo = sexo_map.get(sexo_raw, 'U')

    # Eventos
    eventos = extrair_eventos_pessoa(person_el, mapas['eventos'], namespace)

    def evento_info(chave):
        ev = eventos.get(chave)
        if not ev:
            return None
        data = ev.get('data')
        ano = data.get('val_ano') if data else None
        lugar_handle = ev.get('lugar_handle')
        lugar_id = handle_para_id(mapas, 'lugares', lugar_handle) if lugar_handle else None
        val = data.get('val') if data else None
        return val, lugar_id, ano

    nasc = evento_info('birth')
    bap = evento_info('baptism')
    obit = evento_info('death')
    sep = evento_info('burial')

    data_nasc, lugar_nasc_id, ano_nasc = nasc if nasc else (None, None, None)
    data_bap, lugar_bap_id, _ = bap if bap else (None, None, None)
    data_obit, lugar_obit_id, ano_obit = obit if obit else (None, None, None)
    data_sep, lugar_sep_id, _ = sep if sep else (None, None, None)

    # Profissão — guardada como evento do tipo Occupation em Gramps
    profissao = None
    ev_occ = eventos.get('occupation')
    if ev_occ:
        profissao = ev_occ.get('descricao') or None

    # Famílias
    familias_como_filho = [
        handle_para_id(mapas, 'familias', atrib(ref, 'hlink'))
        for ref in person_el.findall(ns('childof', namespace))
        if atrib(ref, 'hlink')
    ]
    familias_como_pai = [
        handle_para_id(mapas, 'familias', atrib(ref, 'hlink'))
        for ref in person_el.findall(ns('parentin', namespace))
        if atrib(ref, 'hlink')
    ]
    familias_como_filho = [f for f in familias_como_filho if f]
    familias_como_pai = [f for f in familias_como_pai if f]

    todas_familias = list(set(familias_como_filho + familias_como_pai))

    # Privacidade
    protegida = calcular_protegida(private)

    # Anonimizar primeiro nome se privado
    if protegida:
        nome_proprio = 'Privado'
        nome_completo = f'Privado {apelido}' if apelido else 'Privado'

    # Notas, citações, media
    notas = extrair_notas(person_el, mapas['notas'], namespace)
    citacoes = extrair_citacoes(person_el, mapas['citacoes'], mapas['fontes'], namespace)

    # Media directa na pessoa + media de cada evento (sem duplicados)
    todos_media_handles = list(extrair_media_refs(person_el, namespace))
    for ev in eventos.values():
        for h in ev.get('media_handles', []):
            if h not in todos_media_handles:
                todos_media_handles.append(h)

    media_ids = [
        handle_para_id(mapas, 'media', h)
        for h in todos_media_handles
        if handle_para_id(mapas, 'media', h)
    ]

    # Óbito: usar o registado, ou estimar se nasceu há mais de 110 anos
    obito_final = {'data': data_obit, 'lugar_id': lugar_obit_id} if data_obit or lugar_obit_id else None
    data_nasc_ou_bap = data_nasc or data_bap
    if obito_final is None and data_nasc_ou_bap:
        m = re.search(r'(\d{4})', data_nasc_ou_bap)
        if m:
            ano_nasc = int(m.group(1))
            ano_limite = ano_nasc + 110
            if ano_limite < date.today().year:
                obito_final = {'data': f'antes de {ano_limite}', 'lugar_id': None, 'estimado': True}

    return {
        'id': gramps_id,
        'protegida': protegida,
        'nome': nome_completo,
        'nome_proprio': nome_proprio,
        'apelido': apelido,
        'nomes_alt': nomes_alt or None,
        'sexo': sexo,
        'nascimento': {'data': data_nasc, 'lugar_id': lugar_nasc_id} if data_nasc or lugar_nasc_id else None,
        'baptismo': {'data': data_bap, 'lugar_id': lugar_bap_id} if data_bap or lugar_bap_id else None,
        'obito': obito_final,
        'sepultura': {'data': data_sep, 'lugar_id': lugar_sep_id} if data_sep or lugar_sep_id else None,
        'profissao': profissao,
        'familias_como_filho': familias_como_filho or None,
        'familias_como_pai': familias_como_pai or None,
        'media': media_ids or None,
        'notas': notas or None,
        'citacoes': citacoes or None,
    }


# ---------------------------------------------------------------------------
# Converter família
# ---------------------------------------------------------------------------

def converter_familia(family_el, mapas, namespace):
    gramps_id = atrib(family_el, 'id')

    pai_ref = family_el.find(ns('father', namespace))
    mae_ref = family_el.find(ns('mother', namespace))
    pai_id = handle_para_id(mapas, 'pessoas', atrib(pai_ref, 'hlink')) if pai_ref is not None else None
    mae_id = handle_para_id(mapas, 'pessoas', atrib(mae_ref, 'hlink')) if mae_ref is not None else None

    filhos = [
        handle_para_id(mapas, 'pessoas', atrib(ref, 'hlink'))
        for ref in family_el.findall(ns('childref', namespace))
        if atrib(ref, 'hlink')
    ]
    filhos = [f for f in filhos if f]

    tipo_rel_el = family_el.find(ns('rel', namespace))
    tipo_relacao = atrib(tipo_rel_el, 'type', 'Married') if tipo_rel_el is not None else 'Married'

    # Evento de casamento
    eventos = {}
    for evref in family_el.findall(ns('eventref', namespace)):
        handle = atrib(evref, 'hlink')
        role = atrib(evref, 'role', 'Family')
        ev = parse_evento(handle, mapas['eventos'], namespace)
        if ev:
            tipo = ev['tipo'].lower()
            eventos[tipo] = ev

    casamento = eventos.get('marriage') or eventos.get('civil union')
    data_casamento = None
    lugar_casamento_id = None
    if casamento:
        data_ev = casamento.get('data')
        data_casamento = data_ev.get('val') if data_ev else None
        lugar_handle = casamento.get('lugar_handle')
        lugar_casamento_id = handle_para_id(mapas, 'lugares', lugar_handle) if lugar_handle else None

    notas = extrair_notas(family_el, mapas['notas'], namespace)

    # Media directa na família + media dos eventos da família
    todos_media_handles = list(extrair_media_refs(family_el, namespace))
    for ev in eventos.values():
        for h in ev.get('media_handles', []):
            if h not in todos_media_handles:
                todos_media_handles.append(h)
    media_ids = [
        handle_para_id(mapas, 'media', h)
        for h in todos_media_handles
        if handle_para_id(mapas, 'media', h)
    ]

    return {
        'id': gramps_id,
        'pai': pai_id,
        'mae': mae_id,
        'filhos': filhos or None,
        'tipo_relacao': tipo_relacao,
        'casamento': {
            'data': data_casamento,
            'lugar_id': lugar_casamento_id,
        } if data_casamento or lugar_casamento_id else None,
        'notas': notas or None,
        'media': media_ids or None,
    }


# ---------------------------------------------------------------------------
# Converter lugar
# ---------------------------------------------------------------------------

def converter_lugar(place_el, mapas, namespace):
    gramps_id = atrib(place_el, 'id')

    ptitle_el = place_el.find(ns('ptitle', namespace))
    nome = ptitle_el.text.strip() if ptitle_el is not None and ptitle_el.text else None

    # Nome alternativo ou tipo
    pname_el = place_el.find(ns('pname', namespace))
    nome_val = atrib(pname_el, 'value') if pname_el is not None else None
    if not nome and nome_val:
        nome = nome_val

    tipo_el = place_el.find(ns('type', namespace))
    tipo = tipo_el.text.strip() if tipo_el is not None and tipo_el.text else None

    # Coordenadas
    coord_el = place_el.find(ns('coord', namespace))
    lat = atrib(coord_el, 'lat') if coord_el is not None else None
    lon = atrib(coord_el, 'long') if coord_el is not None else None

    # Lugar pai (hierarquia)
    placeref = place_el.find(ns('placeref', namespace))
    pai_id = handle_para_id(mapas, 'lugares', atrib(placeref, 'hlink')) if placeref is not None else None

    return {
        'id': gramps_id,
        'nome': nome,
        'tipo': tipo,
        'lat': lat,
        'lon': lon,
        'pai_id': pai_id,
    }


# ---------------------------------------------------------------------------
# Converter media
# ---------------------------------------------------------------------------

def converter_media(obj_el, namespace):
    gramps_id = atrib(obj_el, 'id')

    file_el = obj_el.find(ns('file', namespace))
    caminho_original = atrib(file_el, 'src') if file_el is not None else None
    mime = atrib(file_el, 'mime') if file_el is not None else None
    descricao_file = atrib(file_el, 'description') if file_el is not None else None

    descricao_el = obj_el.find(ns('description', namespace))
    descricao = descricao_el.text.strip() if descricao_el is not None and descricao_el.text else descricao_file

    data_el = obj_el.find(ns('date', namespace))
    data = None
    if data_el is not None:
        dateval = data_el.find(ns('dateval', None))  # sem namespace às vezes
        if dateval is None:
            dateval = obj_el.find('.//{*}dateval')
        if dateval is not None:
            data = atrib(dateval, 'val')

    # Tipo inferido da pasta e do MIME
    # A pasta é mais fiável do que o MIME (documentos digitalizados são image/jpeg)
    PASTAS_FOTO      = {'fotos', 'perfil'}
    PASTAS_DOCUMENTO = {'registos', 'obitos', 'casamentos', 'batizados',
                        'assinaturas', 'livros', 'outros'}
    pasta = caminho_original.split('/')[-2].lower() if caminho_original and '/' in caminho_original else ''
    tipo = 'outro'
    if mime:
        if mime.startswith('video/'):
            tipo = 'video'
        elif mime.startswith('audio/'):
            tipo = 'audio'
        elif pasta in PASTAS_FOTO:
            tipo = 'foto'
        elif pasta in PASTAS_DOCUMENTO:
            tipo = 'documento'
        elif mime in ('application/pdf', 'image/tiff'):
            tipo = 'documento'
        elif mime.startswith('image/'):
            # imagem em pasta desconhecida — assumir documento (mais seguro)
            tipo = 'documento'

    return {
        'id': gramps_id,
        'caminho_original': caminho_original,
        'caminho': None,  # preenchido por processar_media.py
        'thumb': None,    # preenchido por processar_media.py
        'descricao': descricao,
        'data': data,
        'mime': mime,
        'tipo': tipo,
    }


# ---------------------------------------------------------------------------
# Gerar índice
# ---------------------------------------------------------------------------

def gerar_indice(pessoas_data, media_por_id=None):
    import re
    indice = []
    for p in pessoas_data:
        entrada = {'id': p['id']}
        if p.get('nome'):
            entrada['nome'] = p['nome']
        if p.get('apelido'):
            entrada['apelido'] = p['apelido']
        entrada['sexo'] = p.get('sexo', 'U')

        nasc = p.get('nascimento') or p.get('baptismo')
        if nasc and nasc.get('data'):
            m = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', nasc['data'])
            if m:
                entrada['ano_nasc'] = int(m.group(1))
            data_str = nasc['data']
            # MM-DD para filtragem de aniversários (requer formato YYYY-MM-DD)
            if len(data_str) >= 10 and data_str[4] == '-' and data_str[7] == '-':
                entrada['mmdd_nasc'] = data_str[5:10]

        obit = p.get('obito')
        if obit and obit.get('data'):
            m = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', obit['data'])
            if m:
                entrada['ano_obit'] = int(m.group(1))
            data_str = obit['data']
            if len(data_str) >= 10 and data_str[4] == '-' and data_str[7] == '-':
                entrada['mmdd_obit'] = data_str[5:10]

        # ID do primeiro retrato (pasta Fotos/) para lookup de thumb em mediaMap
        if media_por_id and p.get('media'):
            for mid in p['media']:
                m_item = media_por_id.get(mid)
                if m_item and m_item.get('caminho_original') and '/Fotos/' in m_item['caminho_original']:
                    entrada['thumb_id'] = mid
                    break

        indice.append(entrada)
    indice.sort(key=lambda x: x.get('nome', ''))
    return indice


def gerar_media_pessoas(pessoas_data):
    """Gera mapa inverso: media_id → lista de {id, nome} de pessoas públicas."""
    mapa = {}
    for p in pessoas_data:
        if p.get('protegida') or not p.get('media'):
            continue
        entrada_pessoa = {'id': p['id'], 'nome': p.get('nome') or p['id']}
        for mid in p['media']:
            if mid not in mapa:
                mapa[mid] = []
            mapa[mid].append(entrada_pessoa)
    return mapa


# ---------------------------------------------------------------------------
# Escrita de ficheiros
# ---------------------------------------------------------------------------

def escrever_json(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Converte GrampsXML para JSON')
    parser.add_argument('--input', default='data/arvore.gpkg',
                        help='Caminho para o ficheiro .gpkg, .gramps ou .xml')
    parser.add_argument('--output', default='src/data',
                        help='Directorio de saida para os ficheiros JSON')
    args = parser.parse_args()

    print(f'A ler: {args.input}')
    root, tar = abrir_gramps(args.input)
    namespace = detectar_namespace(root)

    # Guardar referencia ao tar para uso pelo processar_media
    if tar is not None:
        print('Formato .gpkg detectado: media incluida no pacote')
    print(f'Namespace detectado: {namespace or "(nenhum)"}')

    mapas = construir_mapas(root, namespace)

    n_pessoas = len(mapas['pessoas'])
    n_familias = len(mapas['familias'])
    n_lugares = len(mapas['lugares'])
    n_media = len(mapas['media'])
    print(f'Encontrado: {n_pessoas} pessoas, {n_familias} familias, {n_lugares} lugares, {n_media} media')

    output = Path(args.output)

    # Pessoas
    pessoas_data = []
    protegidas = 0
    for handle, person_el in mapas['pessoas'].items():
        dados = converter_pessoa(person_el, mapas, namespace)
        pessoas_data.append(dados)
        if dados.get('protegida'):
            protegidas += 1
        escrever_json(output / 'pessoas' / f'{dados["id"]}.json', dados)

    print(f'Pessoas: {len(pessoas_data)} total, {protegidas} protegidas, {len(pessoas_data) - protegidas} publicas')

    # Familias
    familias_data = []
    for handle, family_el in mapas['familias'].items():
        dados = converter_familia(family_el, mapas, namespace)
        familias_data.append(dados)
        escrever_json(output / 'familias' / f'{dados["id"]}.json', dados)

    print(f'Familias: {n_familias} escritas')

    # Lugares
    lugares_data = []
    for handle, place_el in mapas['lugares'].items():
        dados = converter_lugar(place_el, mapas, namespace)
        lugares_data.append(dados)

    escrever_json(output / 'lugares.json', lugares_data)
    print(f'Lugares: {len(lugares_data)} escritos')

    # Recolher IDs de media de todos os indivíduos; marcar os de privados para pixelização
    media_permitidos: set[str] = set()
    media_ids_privados: set[str] = set()
    for p in pessoas_data:
        for mid in (p.get('media') or []):
            media_permitidos.add(mid)
            if p.get('protegida'):
                media_ids_privados.add(mid)

    # Famílias: incluir sempre a media de família
    for fam in familias_data:
        for mid in (fam.get('media') or []):
            media_permitidos.add(mid)

    # Preservar caminhos já resolvidos pelo processar_media.py
    media_anterior = {}
    media_json_existente = output / 'media.json'
    if media_json_existente.exists():
        for m in json.loads(media_json_existente.read_text(encoding='utf-8')):
            if m.get('caminho') or m.get('thumb'):
                media_anterior[m['id']] = {'caminho': m['caminho'], 'thumb': m['thumb']}

    media_data = []
    n_excluidos = 0
    for handle, obj_el in mapas['media'].items():
        dados = converter_media(obj_el, namespace)
        if dados['id'] not in media_permitidos:
            n_excluidos += 1
            continue
        if dados['id'] in media_anterior:
            dados['caminho'] = media_anterior[dados['id']]['caminho']
            dados['thumb'] = media_anterior[dados['id']]['thumb']
        if dados['id'] in media_ids_privados:
            dados['privado'] = True
        media_data.append(dados)

    escrever_json(output / 'media.json', media_data)
    print(f'Media: {len(media_data)} entradas escritas ({len(media_ids_privados)} de privados para pixelização)')

    # Indice (com campos extra para evitar leituras individuais no build)
    media_por_id = {m['id']: m for m in media_data}
    indice = gerar_indice(pessoas_data, media_por_id)
    escrever_json(output / 'indice.json', indice)
    print(f'Indice: {len(indice)} entradas')

    # Mapa inverso media → pessoas públicas (para arquivo.astro)
    media_pessoas = gerar_media_pessoas(pessoas_data)
    escrever_json(output / 'media-pessoas.json', media_pessoas)
    print(f'media-pessoas.json: {len(media_pessoas)} entradas de media')

    # arvore.json — dataset compacto para a arvore interactiva React
    # Inclui thumb do primeiro retrato (pasta Fotos/) de cada pessoa
    import re as _re
    media_por_id = {m['id']: m for m in media_data}
    arvore_pessoas = {}
    for p in pessoas_data:
        pid = p['id']
        thumb = None
        if p.get('media'):
            for mid in p['media']:
                m = media_por_id.get(mid)
                if m and m.get('caminho_original', '') and '/Fotos/' in m['caminho_original']:
                    thumb = m.get('thumb')
                    break
        entrada = {
            'nome': p.get('nome'),
            'apelido': p.get('apelido'),
            'sexo': p.get('sexo', 'U'),
            'protegida': p.get('protegida', False),
            'thumb': thumb,
        }
        # ano_nasc e ano_obit para todos (necessário para silhuetas)
        nasc = p.get('nascimento') or p.get('baptismo')
        obit = p.get('obito')
        if nasc and nasc.get('data'):
            m_ano = _re.search(r'\b(\d{4})\b', nasc['data'])
            if m_ano:
                entrada['ano_nasc'] = int(m_ano.group(1))
        if obit and obit.get('data'):
            m_ano = _re.search(r'\b(\d{4})\b', obit['data'])
            if m_ano:
                entrada['ano_obit'] = int(m_ano.group(1))
        arvore_pessoas[pid] = entrada

    arvore_familias = {}
    for handle, family_el in mapas['familias'].items():
        fid = atrib(family_el, 'id')
        # Ler do JSON já gerado para evitar duplicar lógica
        fam_path = output / 'familias' / f'{fid}.json'
        if fam_path.exists():
            fam = json.loads(fam_path.read_text(encoding='utf-8'))
            entrada_fam = {}
            if fam.get('pai'): entrada_fam['pai'] = fam['pai']
            if fam.get('mae'): entrada_fam['mae'] = fam['mae']
            if fam.get('filhos'): entrada_fam['filhos'] = fam['filhos']
            arvore_familias[fid] = entrada_fam

    arvore_json = {'pessoas': arvore_pessoas, 'familias': arvore_familias}
    arvore_dir = Path('public/data')
    arvore_dir.mkdir(parents=True, exist_ok=True)
    (arvore_dir / 'arvore.json').write_text(
        json.dumps(arvore_json, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8'
    )
    print(f'arvore.json: {len(arvore_pessoas)} pessoas, {len(arvore_familias)} familias')

    print('Concluido.')


if __name__ == '__main__':
    main()

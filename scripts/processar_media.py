#!/usr/bin/env python3
"""
processar_media.py
Extrai e processa ficheiros de media do Gramps para public/media/ e gera thumbnails.
Actualiza src/data/media.json com os caminhos correctos.

Suporta:
  .gpkg  — extrai media directamente do pacote (nao requer --gramps-media-dir)
  outros — copia de --gramps-media-dir ou do caminho original guardado no Gramps

Uso:
    python3 scripts/processar_media.py [--gpkg data/arvore.gpkg]
                                       [--gramps-media-dir /caminho/para/media]
                                       [--media-json src/data/media.json]
                                       [--output-dir public/media]
                                       [--thumb-size 300]
"""

import argparse
import gzip
import io
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit('Erro: Pillow nao instalado. Corra: pip3 install Pillow')


EXTENSOES_IMAGEM = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.tif', '.bmp'}
EXTENSOES_DOCUMENTO = {'.pdf'}


def abrir_gpkg(caminho_gpkg):
    """
    Abre um .gpkg e devolve um tarfile aberto em memoria.
    Constroi indice {nome_do_ficheiro: member} para lookup rapido.
    """
    with gzip.open(caminho_gpkg, 'rb') as f:
        conteudo = f.read()
    tar = tarfile.open(fileobj=io.BytesIO(conteudo))
    # Indice por nome base e por caminho completo
    indice = {}
    for membro in tar.getmembers():
        if membro.isfile():
            indice[membro.name] = membro
            indice[Path(membro.name).name] = membro
    return tar, indice


def extrair_de_gpkg(tar, indice, caminho_original, destino):
    """
    Extrai um ficheiro do tar .gpkg para o caminho de destino.
    Tenta correspondencia pelo caminho completo, depois so pelo nome base.
    Devolve True se bem sucedido.
    """
    p = Path(caminho_original)

    # Tentativas de correspondencia
    candidatos = [
        caminho_original,           # caminho tal como esta no XML
        p.name,                     # so o nome do ficheiro
    ]
    # Tambem tentar partes do caminho (ex: Fotos/foto.jpg)
    partes = p.parts
    for i in range(len(partes)):
        candidatos.append(str(Path(*partes[i:])))

    for candidato in candidatos:
        membro = indice.get(candidato)
        if membro is None:
            # Normalizar separadores
            membro = indice.get(candidato.replace('\\', '/'))
        if membro is not None:
            dados = tar.extractfile(membro)
            if dados is not None:
                Path(destino).parent.mkdir(parents=True, exist_ok=True)
                with open(destino, 'wb') as f:
                    f.write(dados.read())
                return True

    return False


def carregar_media_json(caminho):
    with open(caminho, 'r', encoding='utf-8') as f:
        return json.load(f)


def gravar_media_json(caminho, dados):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def resolver_caminho(caminho_original, gramps_media_dir):
    """
    Tenta encontrar o ficheiro de media.
    Gramps guarda caminhos absolutos da maquina original.
    Se o ficheiro nao existir no caminho original, tenta resolver
    relativo ao directorio de media do Gramps fornecido.
    """
    p = Path(caminho_original)

    # Caminho absoluto existe directamente
    if p.exists():
        return p

    # Tentar relativo ao directorio de media Gramps
    if gramps_media_dir:
        alternativo = Path(gramps_media_dir) / p.name
        if alternativo.exists():
            return alternativo

        # Tentar com subdirectorios preservados
        partes = p.parts
        for i in range(len(partes)):
            tentativa = Path(gramps_media_dir) / Path(*partes[i:])
            if tentativa.exists():
                return tentativa

    return None


def gerar_nome_destino(gramps_id, caminho_original):
    """Gera nome de ficheiro seguro baseado no ID Gramps e extensao original."""
    sufixo = Path(caminho_original).suffix.lower()
    return f'{gramps_id}{sufixo}'


def _para_rgb(img):
    """Converte qualquer modo de imagem para RGB (necessario para guardar em JPEG)."""
    if img.mode in ('RGBA', 'LA', 'P'):
        if img.mode == 'P':
            img = img.convert('RGBA')
        fundo = Image.new('RGB', img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        return fundo
    if img.mode != 'RGB':
        return img.convert('RGB')
    return img


def _pixelizar(img, blocos=12):
    """Pixeliza uma imagem reduzindo para `blocos` px e escalando de volta."""
    orig_size = img.size
    pequena = img.resize((blocos, blocos), Image.NEAREST)
    return pequena.resize(orig_size, Image.NEAREST)


def gerar_thumbnail(caminho_orig, caminho_thumb, tamanho, pixelizar=False):
    """Gera thumbnail de uma imagem. Devolve True se bem sucedido."""
    try:
        with Image.open(caminho_orig) as img:
            img.thumbnail((tamanho, tamanho), Image.LANCZOS)
            img = _para_rgb(img)
            if pixelizar:
                img = _pixelizar(img)
            caminho_thumb.parent.mkdir(parents=True, exist_ok=True)
            img.save(caminho_thumb, 'JPEG', quality=85, optimize=True)
        return True
    except Exception as e:
        print(f'  Aviso: nao foi possivel gerar thumbnail para {caminho_orig.name}: {e}')
        return False


def gerar_web(caminho_orig, caminho_web, tamanho_max, qualidade, pixelizar=False):
    """
    Gera versao web de uma imagem: redimensiona para max tamanho_max px no lado
    maior (se necessario) e guarda em JPEG com a qualidade indicada.
    Devolve True se bem sucedido.
    """
    try:
        with Image.open(caminho_orig) as img:
            larg, alt = img.size
            if larg <= tamanho_max and alt <= tamanho_max:
                img = _para_rgb(img)
            else:
                img.thumbnail((tamanho_max, tamanho_max), Image.LANCZOS)
                img = _para_rgb(img)
            if pixelizar:
                img = _pixelizar(img)
            caminho_web.parent.mkdir(parents=True, exist_ok=True)
            img.save(caminho_web, 'JPEG', quality=qualidade, optimize=True)
        return True
    except Exception as e:
        print(f'  Aviso: nao foi possivel gerar versao web para {caminho_orig.name}: {e}')
        return False


def processar_pdf_thumb(caminho_orig, caminho_thumb):
    """
    Tenta gerar thumbnail de PDF usando pdf2image (opcional).
    Se nao disponivel, copia um placeholder.
    """
    try:
        from pdf2image import convert_from_path
        paginas = convert_from_path(str(caminho_orig), first_page=1, last_page=1, dpi=72)
        if paginas:
            img = paginas[0]
            img.thumbnail((300, 300), Image.LANCZOS)
            caminho_thumb.parent.mkdir(parents=True, exist_ok=True)
            img.save(caminho_thumb, 'JPEG', quality=80)
            return True
    except ImportError:
        pass
    except Exception as e:
        print(f'  Aviso: erro ao processar PDF {caminho_orig.name}: {e}')
    return False


def main():
    parser = argparse.ArgumentParser(description='Processa media do Gramps')
    parser.add_argument('--gpkg', default='data/arvore.gpkg',
                        help='Caminho para o .gpkg (se existir, tem prioridade sobre --gramps-media-dir)')
    parser.add_argument('--gramps-media-dir', default=None,
                        help='Directorio raiz dos ficheiros de media (alternativa ao .gpkg)')
    parser.add_argument('--media-json', default='src/data/media.json',
                        help='Caminho para media.json gerado pelo gramps_to_json.py')
    parser.add_argument('--output-dir', default='public/media',
                        help='Directorio de saida (originais/ e thumbs/ serao criados aqui)')
    parser.add_argument('--thumb-size', type=int, default=300,
                        help='Tamanho maximo do thumbnail em pixeis (default: 300)')
    parser.add_argument('--web-size', type=int, default=1920,
                        help='Tamanho maximo da versao web em pixeis (default: 1920)')
    parser.add_argument('--web-quality', type=int, default=80,
                        help='Qualidade JPEG da versao web (default: 80)')
    args = parser.parse_args()

    media_json_path = Path(args.media_json)
    if not media_json_path.exists():
        sys.exit(f'Erro: {media_json_path} nao encontrado. Corra gramps_to_json.py primeiro.')

    media_data = carregar_media_json(media_json_path)
    if not media_data:
        print('Nenhuma entrada de media encontrada. Nada a fazer.')
        return

    # IDs de media de pessoas privadas — serão pixelizados
    ids_privados = {m['id'] for m in media_data if m.get('privado')}

    # Abrir .gpkg se disponivel
    tar = None
    tar_indice = None
    gpkg_path = Path(args.gpkg)
    if gpkg_path.exists():
        print(f'A usar media do .gpkg: {gpkg_path}')
        tar, tar_indice = abrir_gpkg(gpkg_path)
    elif args.gramps_media_dir:
        print(f'A usar media de directorio: {args.gramps_media_dir}')
    else:
        print('Aviso: nem .gpkg nem --gramps-media-dir fornecidos. Apenas caminhos absolutos serao tentados.')

    output_dir = Path(args.output_dir)
    dir_originais = output_dir / 'originais'
    dir_thumbs = output_dir / 'thumbs'
    dir_web = output_dir / 'web'
    dir_originais.mkdir(parents=True, exist_ok=True)
    dir_thumbs.mkdir(parents=True, exist_ok=True)
    dir_web.mkdir(parents=True, exist_ok=True)

    copiados = 0
    thumbnails = 0
    webs = 0
    nao_encontrados = []

    for entrada in media_data:
        gramps_id = entrada.get('id')
        caminho_original = entrada.get('caminho_original')

        if not caminho_original:
            continue

        ext = Path(caminho_original).suffix.lower()
        nome_dest = gerar_nome_destino(gramps_id, caminho_original)
        caminho_dest = dir_originais / nome_dest
        caminho_thumb = dir_thumbs / f'{gramps_id}.jpg'

        # Tentar obter ficheiro
        fonte = None

        if tar is not None and tar_indice is not None:
            # Extrair do .gpkg se ainda nao existir no destino
            if not caminho_dest.exists():
                ok = extrair_de_gpkg(tar, tar_indice, caminho_original, caminho_dest)
                if ok:
                    copiados += 1
                    fonte = caminho_dest
                else:
                    nao_encontrados.append(caminho_original)
            else:
                fonte = caminho_dest
        else:
            fonte = resolver_caminho(caminho_original, args.gramps_media_dir)
            if fonte is None:
                nao_encontrados.append(caminho_original)
            elif not caminho_dest.exists() or fonte.stat().st_mtime > caminho_dest.stat().st_mtime:
                shutil.copy2(fonte, caminho_dest)
                copiados += 1
                fonte = caminho_dest

        if fonte is None or not Path(fonte).exists():
            entrada['caminho'] = f'/media/originais/{nome_dest}'
            entrada['thumb'] = None
            entrada['web'] = None
            continue

        # Caminho publico
        entrada['caminho'] = f'/media/originais/{nome_dest}'

        # Gerar thumbnail e versao web
        if ext in EXTENSOES_IMAGEM:
            e_privado = gramps_id in ids_privados
            # Re-gerar sempre se for privado (para garantir pixelização actualizada)
            if not caminho_thumb.exists() or e_privado:
                ok = gerar_thumbnail(Path(fonte), caminho_thumb, args.thumb_size, pixelizar=e_privado)
                if ok:
                    thumbnails += 1
            entrada['thumb'] = f'/media/thumbs/{gramps_id}.jpg'

            caminho_web = dir_web / f'{gramps_id}.jpg'
            if not caminho_web.exists() or e_privado:
                ok = gerar_web(Path(fonte), caminho_web, args.web_size, args.web_quality, pixelizar=e_privado)
                if ok:
                    webs += 1
            entrada['web'] = f'/media/web/{gramps_id}.jpg'

        elif ext in EXTENSOES_DOCUMENTO:
            if not caminho_thumb.exists():
                ok = processar_pdf_thumb(Path(fonte), caminho_thumb)
                if ok:
                    thumbnails += 1
            if caminho_thumb.exists():
                entrada['thumb'] = f'/media/thumbs/{gramps_id}.jpg'
            else:
                entrada['thumb'] = None
            entrada['web'] = None

        else:
            entrada['thumb'] = None
            entrada['web'] = None

    gravar_media_json(media_json_path, media_data)

    print(f'Ficheiros copiados/extraidos: {copiados}')
    print(f'Thumbnails gerados: {thumbnails}')
    print(f'Versoes web geradas: {webs}')
    if nao_encontrados:
        print(f'Nao encontrados ({len(nao_encontrados)}):')
        for c in nao_encontrados[:10]:
            print(f'  {c}')
        if len(nao_encontrados) > 10:
            print(f'  ... e mais {len(nao_encontrados) - 10}')
    print('media.json actualizado.')


if __name__ == '__main__':
    main()

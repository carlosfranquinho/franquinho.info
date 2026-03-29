#!/usr/bin/env python3
"""Gera o mosaico do hero da página inicial a partir de thumbnails de documentos."""

import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT   = Path(__file__).parent.parent
OUTPUT = ROOT / 'public' / 'hero-mosaic.webp'
COLS, ROWS = 5, 3
TILE   = 300          # pixels por lado de cada célula
GAP    = 2            # gap entre células (bg stone-900)

media = json.loads((ROOT / 'src' / 'data' / 'media.json').read_text())

thumbs = [
    m for m in media
    if m.get('thumb') and m.get('caminho')
    and m.get('mime', '').startswith('image/')
    and '/Fotos/' not in (m.get('caminho_original') or '')
][: COLS * ROWS]

if not thumbs:
    print('build-hero: sem thumbnails, a saltar.')
    raise SystemExit(0)

W = COLS * TILE + (COLS - 1) * GAP
H = ROWS * TILE + (ROWS - 1) * GAP
mosaic = Image.new('RGB', (W, H), (28, 25, 23))  # stone-900 aprox.

for idx, m in enumerate(thumbs):
    col = idx % COLS
    row = idx // COLS
    x   = col * (TILE + GAP)
    y   = row * (TILE + GAP)

    path = ROOT / 'public' / m['thumb'].lstrip('/')
    try:
        tile = Image.open(path).convert('RGB')
        tile = ImageOps.fit(tile, (TILE, TILE), Image.LANCZOS)
        # grayscale já incorporado na imagem (equivale ao filtro CSS da versão anterior)
        tile = ImageOps.grayscale(tile).convert('RGB')
        mosaic.paste(tile, (x, y))
    except Exception as e:
        print(f'  aviso: {path.name}: {e}')

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
mosaic.save(OUTPUT, 'WEBP', quality=75, method=4)
print(f'build-hero: {OUTPUT.relative_to(ROOT)}  ({W}×{H}px, {len(thumbs)} tiles)')

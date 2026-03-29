# Site Genealógico da Família

## Contexto

Vou criar um site genealógico estático com Astro + React + Tailwind CSS.
Os dados vêm de um ficheiro GrampsXML exportado do software Gramps
(ficheiro `data/arvore.gramps` ou `data/arvore.xml` descomprimido).

---

## Passo 1 — Script de conversão GrampsXML → JSON

Cria `scripts/gramps_to_json.py` que lê `data/arvore.gramps` e gera
ficheiros JSON em `src/data/`.

### Regras de privacidade (obrigatórias)

Uma pessoa é considerada **protegida** se:

- Estiver marcada como privada no Gramps (campo `private`)
- Não tiver data de óbito registada (presume-se viva)
- Tiver falecido há menos de 20 anos

Para pessoas protegidas, gerar apenas:

```json
{
  "id": "I0042",
  "protegida": true,
  "sexo": "M",
  "nome": "Familiar",
  "relacoes": ["F0010", "F0015"]
}
```

Sem nome real, datas, lugares, fotos ou documentos.
Para todas as outras pessoas, exportar todos os campos disponíveis.

### Ficheiros a gerar em `src/data/`

- `pessoas/[id].json` — um ficheiro por pessoa com:
  - id, nome completo, nome alternativo, sexo
  - datas e lugares: nascimento, baptismo, casamento, óbito, sepultura
  - profissão, notas, fontes e citações
  - IDs de famílias (como filho e como pai/mãe)
  - IDs de media associada
- `familias/[id].json` — pai, mãe, filhos, tipo de relação, data e lugar do casamento
- `lugares.json` — id, nome, coordenadas, lugar pai (hierarquia: freguesia > concelho > distrito)
- `media.json` — id, caminho original, descrição, data, tipo (foto, documento, etc.)
- `indice.json` — array com id, nome, ano de nascimento, ano de óbito
  (para listagens e busca; campos omitidos para pessoas protegidas)

Incluir também um script auxiliar `scripts/processar_media.py` que:

- Lê os caminhos de media do GrampsXML
- Copia os ficheiros para `public/media/originais/`
- Gera thumbnails com Pillow para `public/media/thumbs/`
- Actualiza `media.json` com os caminhos correctos

---

## Passo 2 — Estrutura Astro

Inicializar projecto Astro com integração React e Tailwind CSS.

Estrutura de pastas:

```
src/
  components/
  pages/
    index.astro
    pessoas/
      index.astro          <- índice alfabético
      [id].astro           <- ficha individual
    lugares/
      index.astro
      [id].astro
    arvore.astro           <- página da árvore interactiva
    arquivo.astro          <- galeria de documentos e fotos
    pesquisa.astro
  data/                    <- gerado pelo script Python
  layouts/
    Base.astro
public/
  media/
scripts/
```

Navegação global: **Início | Árvore | Pessoas | Lugares | Arquivo | Pesquisa**

---

## Passo 3 — Ficha individual (`/pessoas/[id]`)

Para pessoas não protegidas, mostrar:

- Nome, datas e lugares (lugares com link para `/lugares/[id]`)
- Pais, cônjuges e filhos com foto em miniatura e link para a ficha
- Irmãos
- Linha do tempo de eventos
- Galeria de fotos e documentos digitalizados com zoom
- Fontes e citações
- Notas de investigação

Para pessoas protegidas, mostrar apenas:

- "Familiar (dados privados)" como título
- Relações familiares visíveis (sem dados das pessoas protegidas)
- Tooltip explicativo: "Os dados desta pessoa não são públicos por razões de privacidade."

---

## Passo 4 — Árvore interactiva (`/arvore`)

Componente React `TreeView.jsx` usando a biblioteca **react-flow**:

- Nós clicáveis que navegam para a ficha do indivíduo
- Pessoas protegidas aparecem como nós anónimos (sem nome)
- Modos de visualização: árvore de antepassados, árvore de descendentes, modo ampulheta (antepassados + descendentes)
- Zoom, pan e minimap
- Ponto de entrada configurável (id da pessoa de referência)

---

## Passo 5 — Busca estática

Integrar **Pagefind** para busca por nome, lugar e data.
Só indexar páginas de pessoas não protegidas.

---

## Notas gerais

- Sem base de dados, sem servidor — tudo estático
- Compatível com hosting em GitHub Pages ou Netlify
- Código sem emojis
- Tailwind para todos os estilos
- Componentes React apenas onde há interactividade (árvore, galeria, busca); resto em Astro puro
- Começar pelo script Python do Passo 1, que é a base de tudo

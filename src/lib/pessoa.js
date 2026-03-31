/**
 * Devolve o nome a apresentar para uma pessoa.
 * Ficheiro JS puro partilhado entre contexto servidor (utils.ts) e cliente (TreeView.jsx).
 *
 * @param {{ nome?: string|null }} pessoa
 * @param {string} [fallback]
 * @returns {string}
 */
export function formatarNome(pessoa, fallback = 'Sem nome') {
  return pessoa.nome ?? fallback;
}

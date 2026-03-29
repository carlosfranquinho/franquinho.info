/**
 * Devolve o nome a apresentar para uma pessoa, respeitando a sua privacidade.
 * Ficheiro JS puro partilhado entre contexto servidor (utils.ts) e cliente (TreeView.jsx).
 *
 * @param {{ protegida: boolean, apelido?: string|null, nome?: string|null }} pessoa
 * @param {string} [fallback]
 * @returns {string}
 */
export function formatarNome(pessoa, fallback = 'Sem nome') {
  return pessoa.protegida
    ? (pessoa.apelido ? `Privado ${pessoa.apelido}` : 'Privado')
    : (pessoa.nome ?? fallback);
}

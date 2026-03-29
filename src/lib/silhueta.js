/**
 * Devolve o caminho para a silhueta SVG adequada ao sexo, época e idade.
 * Ficheiro JS puro (sem tipos) para ser importado tanto em utils.ts (servidor)
 * como em TreeView.jsx (cliente React).
 *
 * @param {string|undefined} sexo
 * @param {string|number|null|undefined} anoNasc
 * @param {string|number|null|undefined} anoObit
 * @returns {string}
 */
export function silhueta(sexo, anoNasc, anoObit) {
  const nasc = anoNasc ? parseInt(anoNasc) : null;
  const obit = anoObit ? parseInt(anoObit) : null;
  const anoAtual = new Date().getFullYear();

  // Criança falecida com menos de 16 anos
  if (nasc && obit && obit - nasc < 16) return '/silhuetas/crianca_antiga.svg';
  // Criança viva hoje com menos de 16 anos
  if (nasc && !obit && anoAtual - nasc < 16)
    return sexo === 'F' ? '/silhuetas/crianca_rapariga.svg' : '/silhuetas/crianca_rapaz.svg';

  const s = sexo === 'F' ? 'mulher' : 'homem';
  if (!nasc)        return `/silhuetas/${s}_contemporaneo.svg`;
  if (nasc < 1700)  return `/silhuetas/${s}_sec17.svg`;
  if (nasc < 1800)  return `/silhuetas/${s}_sec18.svg`;
  if (nasc < 1850)  return `/silhuetas/${s}_sec19a.svg`;
  if (nasc < 1900)  return `/silhuetas/${s}_sec19b.svg`;
  if (nasc < 1950)  return `/silhuetas/${s}_sec20a.svg`;
  return `/silhuetas/${s}_contemporaneo.svg`;
}

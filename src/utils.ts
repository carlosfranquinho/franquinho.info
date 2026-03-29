/** Indica se um item de media é um retrato (foto da pessoa), não um documento */
export function eRetrato(item: { caminho_original: string | null }): boolean {
  return !!item.caminho_original?.includes('/Fotos/');
}

export { silhueta } from './lib/silhueta.js';
export { formatarNome } from './lib/pessoa.js';

/** Extrai o primeiro ano válido (1000–2099) de uma string de data */
export function extrairAno(data: string | null | undefined): string | undefined {
  return data?.match(/\b(1[0-9]{3}|20[0-9]{2})\b/)?.[1];
}

const MESES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

/** Devolve a categoria (key) de um documento com base no caminho do ficheiro original */
export function categoriaPorCaminho(caminho: string | null | undefined): string {
  const p = caminho ?? '';
  if (p.includes('/Registos/'))    return 'nascimento';
  if (p.includes('/Casamentos/'))  return 'casamento';
  if (p.includes('/Obitos/'))      return 'obito';
  if (p.includes('/Passaportes/')) return 'passaporte';
  return 'outro';
}

/** Devolve a legenda legível de um documento com base no caminho do ficheiro original */
export function legendaDocumento(caminho: string | null | undefined): string {
  const p = caminho ?? '';
  if (p.includes('/Registos/'))    return 'Registo de Nascimento';
  if (p.includes('/Casamentos/'))  return 'Registo de Casamento';
  if (p.includes('/Obitos/'))      return 'Registo de Óbito';
  if (p.includes('/Passaportes/')) return 'Pedido de Passaporte';
  if (p.includes('/Assinaturas/')) return 'Assinatura';
  if (p.includes('/Batizados/'))   return 'Registo de Batismo';
  return 'Documento';
}

/** Converte "1950-06-10" → "10 de junho de 1950"; "1950-06" → "junho de 1950"; "1950" → "1950" */
export function formatarData(data: string | null | undefined): string {
  if (!data) return '';
  const full = data.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (full) {
    const mes = parseInt(full[2]) - 1;
    if (mes >= 0 && mes < 12)
      return `${parseInt(full[3])} de ${MESES[mes]} de ${full[1]}`;
  }
  const ym = data.match(/^(\d{4})-(\d{2})$/);
  if (ym) {
    const mes = parseInt(ym[2]) - 1;
    if (mes >= 0 && mes < 12)
      return `${MESES[mes]} de ${ym[1]}`;
  }
  return data;
}

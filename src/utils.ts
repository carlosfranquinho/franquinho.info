/** Indica se um item de media é um retrato (foto da pessoa), não um documento */
export function eRetrato(item: { caminho_original: string | null }): boolean {
  return !!item.caminho_original?.includes('/Fotos/');
}

/** Devolve o caminho para a silhueta SVG adequada ao sexo, época e idade */
export function silhueta(
  sexo: string | undefined,
  anoNasc?: string | null,
  anoObit?: string | null,
): string {
  const nasc = anoNasc ? parseInt(anoNasc) : null;
  const obit = anoObit ? parseInt(anoObit) : null;
  const anoAtual = new Date().getFullYear();

  // Criança falecida com menos de 16 anos
  if (nasc && obit && obit - nasc < 16) return '/silhuetas/crianca_antiga.svg';
  // Criança viva hoje com menos de 16 anos
  if (nasc && !obit && anoAtual - nasc < 16)
    return sexo === 'F' ? '/silhuetas/crianca_rapariga.svg' : '/silhuetas/crianca_rapaz.svg';

  const s = sexo === 'F' ? 'mulher' : 'homem';
  if (!nasc)  return `/silhuetas/${s}_contemporaneo.svg`;
  if (nasc < 1700) return `/silhuetas/${s}_sec17.svg`;
  if (nasc < 1800) return `/silhuetas/${s}_sec18.svg`;
  if (nasc < 1850) return `/silhuetas/${s}_sec19a.svg`;
  if (nasc < 1900) return `/silhuetas/${s}_sec19b.svg`;
  if (nasc < 1950) return `/silhuetas/${s}_sec20a.svg`;
  return `/silhuetas/${s}_contemporaneo.svg`;
}

const MESES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

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

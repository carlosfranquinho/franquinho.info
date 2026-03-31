// Tipos partilhados entre componentes e páginas

export interface EventoData {
  val: string;
  val_ano: number | null;
  qualidade: string;
  tipo: string;
}

export interface EventoPessoa {
  data: string | null;
  lugar_id: string | null;
}

export interface Pessoa {
  id: string;
  protegida: boolean;
  sexo: 'M' | 'F' | 'U';
  nome: string | null;
  nome_proprio: string | null;
  apelido: string | null;
  nomes_alt: { tipo: string; nome: string }[] | null;
  nascimento: EventoPessoa | null;
  baptismo: EventoPessoa | null;
  obito: EventoPessoa | null;
  sepultura: EventoPessoa | null;
  profissao: string | null;
  familias_como_filho: string[] | null;
  familias_como_pai: string[] | null;
  media: string[] | null;
  notas: { tipo: string; texto: string }[] | null;
  citacoes: { fonte: string | null; pagina: string | null }[] | null;
}


export interface Familia {
  id: string;
  pai: string | null;
  mae: string | null;
  filhos: string[] | null;
  tipo_relacao: string;
  casamento: { data: string | null; lugar_id: string | null } | null;
  notas: { tipo: string; texto: string }[] | null;
}

export interface Lugar {
  id: string;
  nome: string | null;
  tipo: string | null;
  lat: string | null;
  lon: string | null;
  pai_id: string | null;
}

export interface LugarNode extends Lugar {
  filhos: LugarNode[];
  total_pessoas: number;
}

export interface MediaItem {
  id: string;
  caminho_original: string | null;
  caminho: string | null;
  thumb: string | null;
  web: string | null;
  descricao: string | null;
  data: string | null;
  mime: string | null;
  tipo: 'foto' | 'documento' | 'video' | 'audio' | 'outro';
  privado?: boolean;
}

export interface EntradaIndice {
  id: string;
  nome?: string;
  sexo?: 'M' | 'F' | 'U';
  ano_nasc?: number;
  ano_obit?: number;
  /** MM-DD do nascimento, presente apenas quando a data tem dia e mês exactos */
  mmdd_nasc?: string;
  /** MM-DD do óbito, presente apenas quando a data tem dia e mês exactos */
  mmdd_obit?: string;
  /** ID do primeiro retrato (pasta Fotos/) para lookup de thumb em mediaMap */
  thumb_id?: string;
}

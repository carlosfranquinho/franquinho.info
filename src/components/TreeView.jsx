import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  Panel,
} from '@xyflow/react';
import * as dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import { silhueta } from '../lib/silhueta.js';
import { formatarNome } from '../lib/pessoa.js';

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const PERSON_W = 200;
const PERSON_H = 76;
const FAMILY_W = 14;
const FAMILY_H = 14;

const COR_SEXO = {
  M: { border: '#3b82f6', bg: '#eff6ff', iniciais: '#1d4ed8' },
  F: { border: '#f43f5e', bg: '#fff1f2', iniciais: '#be123c' },
  U: { border: '#a8a29e', bg: '#fafaf9', iniciais: '#78716c' },
};

// ---------------------------------------------------------------------------
// Nó de pessoa
// ---------------------------------------------------------------------------

function PersonNode({ data }) {
  const { nome, apelido, sexo, protegida, ano_nasc, ano_obit, thumb, isRoot } = data;
  const cor = COR_SEXO[sexo] ?? COR_SEXO.U;
  const nomeDisplay = formatarNome({ protegida, apelido, nome });
  const avatarSrc = thumb ?? silhueta(sexo, ano_nasc, ano_obit);

  return (
    <div
      style={{
        width: PERSON_W,
        height: PERSON_H,
        border: `2px solid ${protegida ? '#d6d3d1' : cor.border}`,
        borderRadius: 10,
        background: protegida ? '#f5f5f4' : cor.bg,
        boxShadow: isRoot
          ? '0 0 0 3px #f59e0b, 0 4px 12px rgba(0,0,0,0.15)'
          : '0 1px 4px rgba(0,0,0,0.08)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 12px',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, pointerEvents: 'none' }} />

      {/* Avatar */}
      <div style={{
        width: 40, height: 40, borderRadius: '50%',
        flexShrink: 0, overflow: 'hidden',
        border: `1.5px solid ${protegida ? '#d6d3d1' : cor.border}`,
        background: protegida ? '#e7e5e4' : cor.bg,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <img src={avatarSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>

      {/* Texto */}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, lineHeight: 1.3,
          color: protegida ? '#a8a29e' : '#1c1917',
          fontStyle: protegida ? 'italic' : 'normal',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {nomeDisplay}
        </div>
        {(ano_nasc || ano_obit) && (
          <div style={{ fontSize: 11, color: '#78716c', marginTop: 2 }}>
            {ano_nasc ?? '?'}{ano_obit ? ` — ${ano_obit}` : ''}
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nó de família (conector)
// ---------------------------------------------------------------------------

function FamilyNode() {
  return (
    <div style={{
      width: FAMILY_W, height: FAMILY_H,
      background: '#d6d3d1', borderRadius: 3,
      border: '1.5px solid #a8a29e',
    }}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
    </div>
  );
}

const nodeTypes = { person: PersonNode, family: FamilyNode };

// ---------------------------------------------------------------------------
// Layout com dagre
// ---------------------------------------------------------------------------

function applyLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70, marginx: 40, marginy: 40 });

  nodes.forEach((n) => {
    g.setNode(n.id, {
      width: n.type === 'family' ? FAMILY_W : PERSON_W,
      height: n.type === 'family' ? FAMILY_H : PERSON_H,
    });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    const w = n.type === 'family' ? FAMILY_W : PERSON_W;
    const h = n.type === 'family' ? FAMILY_H : PERSON_H;
    return { ...n, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
  });
}

// ---------------------------------------------------------------------------
// Construção do grafo
// ---------------------------------------------------------------------------

function buildIndices(familias) {
  const deFilho = {};   // personId → [familyId] (famílias onde é filho)
  const dePai = {};     // personId → [familyId] (famílias onde é pai/mãe)
  Object.entries(familias).forEach(([fid, f]) => {
    (f.filhos ?? []).forEach((cid) => {
      if (!deFilho[cid]) deFilho[cid] = [];
      deFilho[cid].push(fid);
    });
    [f.pai, f.mae].filter(Boolean).forEach((pid) => {
      if (!dePai[pid]) dePai[pid] = [];
      dePai[pid].push(fid);
    });
  });
  return { deFilho, dePai };
}

function buildGraph(rootId, mode, maxDepth, pessoas, familias, indices) {
  const { deFilho, dePai } = indices;
  const nodesMap = new Map();
  const edgesMap = new Map();

  function addPerson(id, isRoot = false) {
    if (nodesMap.has(id)) return;
    const p = pessoas[id];
    if (!p) return;
    nodesMap.set(id, {
      id, type: 'person', position: { x: 0, y: 0 },
      data: { ...p, id, isRoot },
    });
  }

  function addFamily(fid) {
    if (nodesMap.has(fid)) return;
    nodesMap.set(fid, {
      id: fid, type: 'family', position: { x: 0, y: 0 }, data: {},
    });
  }

  function addEdge(source, target, dashed = false) {
    const eid = `${source}→${target}`;
    if (edgesMap.has(eid)) return;
    edgesMap.set(eid, {
      id: eid, source, target, type: 'smoothstep',
      style: { stroke: '#c7c3be', strokeWidth: 1.5, ...(dashed ? { strokeDasharray: '5 3' } : {}) },
    });
  }

  // Sobe na árvore (antepassados)
  function goUp(pid, depth) {
    if (depth > maxDepth) return;
    addPerson(pid, pid === rootId);
    (deFilho[pid] ?? []).forEach((fid) => {
      const f = familias[fid];
      if (!f) return;
      addFamily(fid);
      addEdge(fid, pid);
      if (f.pai) { addPerson(f.pai); addEdge(f.pai, fid); goUp(f.pai, depth + 1); }
      if (f.mae) { addPerson(f.mae); addEdge(f.mae, fid); goUp(f.mae, depth + 1); }
    });
  }

  // Desce na árvore (descendentes)
  function goDown(pid, depth) {
    if (depth > maxDepth) return;
    addPerson(pid, pid === rootId);
    (dePai[pid] ?? []).forEach((fid) => {
      const f = familias[fid];
      if (!f) return;
      addFamily(fid);
      // Pai e mãe → família
      if (f.pai) { addPerson(f.pai); addEdge(f.pai, fid, f.pai !== pid); }
      if (f.mae) { addPerson(f.mae); addEdge(f.mae, fid, f.mae !== pid); }
      // Família → filhos
      (f.filhos ?? []).forEach((cid) => {
        addPerson(cid);
        addEdge(fid, cid);
        goDown(cid, depth + 1);
      });
    });
  }

  addPerson(rootId, true);
  if (mode === 'ancestors'    || mode === 'hourglass') goUp(rootId, 0);
  if (mode === 'descendants'  || mode === 'hourglass') goDown(rootId, 0);

  return {
    nodes: Array.from(nodesMap.values()),
    edges: Array.from(edgesMap.values()),
  };
}

// ---------------------------------------------------------------------------
// Painel de informação (nó seleccionado)
// ---------------------------------------------------------------------------

function InfoPanel({ data, id, onClose, onSetRoot }) {
  if (!data) return null;
  const { nome, apelido, sexo, ano_nasc, ano_obit, protegida, thumb } = data;
  const cor = COR_SEXO[sexo] ?? COR_SEXO.U;
  const nomeDisplay = formatarNome({ protegida, apelido, nome });
  const avatarSrc = thumb ?? silhueta(sexo, ano_nasc, ano_obit);

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'absolute', inset: 0, zIndex: 30,
          background: 'rgba(0,0,0,0.35)',
        }}
      />
      {/* Card centrado */}
      <div style={{
        position: 'absolute', zIndex: 31,
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 300, background: '#fff', borderRadius: 16,
        boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
        overflow: 'hidden',
      }}>
        {/* Barra de cor */}
        <div style={{ height: 5, background: protegida ? '#d6d3d1' : cor.border }} />

        <div style={{ padding: '20px 20px 18px' }}>
          {/* Cabeçalho: avatar + nome */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%', flexShrink: 0, overflow: 'hidden',
              border: `2px solid ${protegida ? '#d6d3d1' : cor.border}`,
            }}>
              <img src={avatarSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontWeight: 700, fontSize: 15, lineHeight: 1.3,
                color: protegida ? '#a8a29e' : '#1c1917',
                fontStyle: protegida ? 'italic' : 'normal',
              }}>
                {nomeDisplay}
              </div>
              {(ano_nasc || ano_obit) && (
                <div style={{ fontSize: 13, color: '#78716c', marginTop: 3 }}>
                  {ano_nasc ?? '?'}{ano_obit ? ` — ${ano_obit}` : ''}
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              style={{
                alignSelf: 'flex-start', color: '#a8a29e', fontSize: 18, lineHeight: 1,
                background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px',
              }}
            >✕</button>
          </div>

          {/* Acções */}
          <div style={{ display: 'flex', gap: 8 }}>
            <a
              href={`/pessoas/${id}`}
              style={{
                flex: 1, display: 'block', textAlign: 'center',
                padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 600,
                background: '#f59e0b', color: '#fff', textDecoration: 'none',
              }}
            >
              Ver ficha
            </a>
            <button
              onClick={() => onSetRoot(id)}
              style={{
                flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 600,
                background: '#f5f5f4', border: '1.5px solid #e7e5e4', color: '#57534e',
                cursor: 'pointer',
              }}
            >
              Centrar aqui
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function TreeView({ defaultRootId = 'I0007', defaultRootName = '' }) {
  const [arvore, setArvore] = useState(null);
  const [indices, setIndices] = useState(null);
  const [rootId, setRootId] = useState(defaultRootId);
  const [mode, setMode] = useState('hourglass');
  const [depth, setDepth] = useState(3);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selected, setSelected] = useState(null); // { id, data }
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [panelOpen, setPanelOpen] = useState(() => typeof window !== 'undefined' ? window.innerWidth >= 640 : true);
  const rfInstance = useRef(null);

  // Carregar arvore.json; se URL tiver #I0001, usar esse ID como raiz inicial
  useEffect(() => {
    const hash = typeof window !== 'undefined' ? window.location.hash.replace('#', '') : '';
    if (hash && /^I\d+$/.test(hash)) setRootId(hash);
    fetch('/data/arvore.json')
      .then((r) => r.json())
      .then((data) => {
        setArvore(data);
        setIndices(buildIndices(data.familias));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Remover o placeholder estático do Astro assim que a árvore estiver pronta
  useEffect(() => {
    if (!loading) {
      document.getElementById('tree-placeholder')?.remove();
    }
  }, [loading]);

  // Reconstruir grafo
  useEffect(() => {
    if (!arvore || !indices) return;
    const { nodes: rawNodes, edges: rawEdges } = buildGraph(rootId, mode, depth, arvore.pessoas, arvore.familias, indices);
    const laid = applyLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    setSelected(null);
    // Centrar no nó raiz com zoom fixo em vez de fitView a todo o grafo
    setTimeout(() => {
      const rootNode = laid.find((n) => n.id === rootId);
      if (rootNode && rfInstance.current) {
        rfInstance.current.setCenter(
          rootNode.position.x + PERSON_W / 2,
          rootNode.position.y + PERSON_H / 2,
          { zoom: 1.1, duration: 400 }
        );
      }
    }, 80);
  }, [arvore, indices, rootId, mode, depth]);

  // Pesquisa
  useEffect(() => {
    if (!arvore || !search.trim()) { setSearchResults([]); return; }
    const q = search.toLowerCase();
    const results = Object.entries(arvore.pessoas)
      .filter(([, p]) => !p.protegida && p.nome?.toLowerCase().includes(q))
      .slice(0, 8)
      .map(([id, p]) => ({ id, nome: p.nome, ano_nasc: p.ano_nasc }));
    setSearchResults(results);
  }, [search, arvore]);

  const onNodeClick = useCallback((_, node) => {
    if (node.type !== 'person') return;
    setSelected({ id: node.id, data: node.data });
  }, []);

  const handleSetRoot = useCallback((id) => {
    setRootId(id);
    setSearch('');
    setSearchResults([]);
    setSelected(null);
  }, []);

  const rootPessoa = arvore?.pessoas[rootId];

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#78716c', fontSize: 14 }}>
      A carregar arvore...
    </div>
  );

  if (!arvore) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#ef4444', fontSize: 14 }}>
      Erro ao carregar dados da arvore.
    </div>
  );

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onInit={(inst) => { rfInstance.current = inst; }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d6d3d1" gap={20} size={0.8} />
        <Controls showInteractive={false} />
        {/* Painel de controlos */}
        <Panel position="top-left">
          {panelOpen ? (
            <div style={{
              background: '#fff', border: '1.5px solid #e7e5e4', borderRadius: 12,
              padding: 14, width: 220, boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
            }}>
              {/* Cabeçalho com botão fechar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Controlos
                </div>
                <button
                  onClick={() => setPanelOpen(false)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a8a29e', fontSize: 16, lineHeight: 1, padding: '0 2px' }}
                  aria-label="Fechar painel"
                >✕</button>
              </div>

              {/* Pessoa raiz */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                  Ponto de partida
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1c1917' }}>
                  {rootPessoa?.nome ?? rootId}
                </div>
                {(rootPessoa?.ano_nasc || rootPessoa?.ano_obit) && (
                  <div style={{ fontSize: 11, color: '#78716c' }}>
                    {rootPessoa.ano_nasc ?? '?'}{rootPessoa.ano_obit ? ` — ${rootPessoa.ano_obit}` : ''}
                  </div>
                )}
              </div>

              {/* Modo */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Modo</div>
                <div style={{ display: 'flex', gap: 4 }}>
                  {[
                    { id: 'ancestors',   label: 'Antepass.' },
                    { id: 'hourglass',   label: 'Ampulheta' },
                    { id: 'descendants', label: 'Descend.' },
                  ].map(({ id, label }) => (
                    <button
                      key={id}
                      onClick={() => setMode(id)}
                      style={{
                        flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 600,
                        borderRadius: 6, border: '1.5px solid',
                        cursor: 'pointer', transition: 'all 0.15s',
                        borderColor: mode === id ? '#f59e0b' : '#e7e5e4',
                        background: mode === id ? '#fef3c7' : '#fafaf9',
                        color: mode === id ? '#92400e' : '#78716c',
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Profundidade */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Gerações</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#92400e' }}>{depth}</span>
                </div>
                <input
                  type="range" min={1} max={6} value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))}
                  style={{ width: '100%', accentColor: '#f59e0b' }}
                />
              </div>

              {/* Pesquisa */}
              <div style={{ position: 'relative' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Navegar para</div>
                <input
                  type="text"
                  placeholder="Nome..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{
                    width: '100%', padding: '6px 10px', fontSize: 12,
                    border: '1.5px solid #e7e5e4', borderRadius: 7,
                    outline: 'none', boxSizing: 'border-box',
                    fontFamily: 'inherit',
                  }}
                />
                {searchResults.length > 0 && (
                  <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30,
                    background: '#fff', border: '1.5px solid #e7e5e4', borderRadius: 8,
                    marginTop: 2, boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {searchResults.map(({ id, nome, ano_nasc }) => (
                      <button
                        key={id}
                        onClick={() => handleSetRoot(id)}
                        style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          width: '100%', padding: '7px 10px', textAlign: 'left',
                          background: 'none', border: 'none', cursor: 'pointer',
                          borderBottom: '1px solid #f5f5f4', fontSize: 12,
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = '#fef9ee'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
                      >
                        <span style={{ color: '#1c1917', fontWeight: 500 }}>{nome}</span>
                        {ano_nasc && <span style={{ color: '#a8a29e', fontSize: 11 }}>{ano_nasc}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Contagem */}
              <div style={{ marginTop: 10, fontSize: 10, color: '#a8a29e', textAlign: 'right' }}>
                {nodes.filter(n => n.type === 'person').length} pessoas · {edges.length} ligações
              </div>
            </div>
          ) : (
            <button
              onClick={() => setPanelOpen(true)}
              style={{
                background: '#fff', border: '1.5px solid #e7e5e4', borderRadius: 10,
                width: 38, height: 38, display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.1)', fontSize: 18,
              }}
              aria-label="Abrir controlos"
            >
              ⚙
            </button>
          )}
        </Panel>
      </ReactFlow>

      {/* Painel do nó seleccionado */}
      {selected && (
        <InfoPanel
          id={selected.id}
          data={selected.data}
          onClose={() => setSelected(null)}
          onSetRoot={handleSetRoot}
        />
      )}
    </div>
  );
}

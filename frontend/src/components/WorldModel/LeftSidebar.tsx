/**
 * LeftSidebar.tsx — Perspectives, search, and node-type filters.
 */
import { useState, useRef } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { PERSPECTIVES, NODE_TYPE_FILTERS } from './graphConfig';
import type { SearchResult } from '../../api/graphApi';
import { graphApi } from '../../api/graphApi';

interface Props {
  activeView: string;
  onViewChange: (view: string) => void;
  activeFilters: Set<string>;
  onFilterToggle: (type: string) => void;
  onSearchSelect: (result: SearchResult) => void;
}

export default function LeftSidebar({
  activeView,
  onViewChange,
  activeFilters,
  onFilterToggle,
  onSearchSelect,
}: Props) {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearch = (val: string) => {
    setQuery(val);
    clearTimeout(debounceRef.current);
    if (val.length < 2) { setSearchResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await graphApi.search(val);
        setSearchResults(data.results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 350);
  };

  return (
    <aside
      className="w-64 flex-shrink-0 flex flex-col gap-4 p-3 overflow-y-auto"
      style={{ borderRight: '1px solid rgba(255,255,255,0.06)' }}
    >
      {/* ── Search ── */}
      <div className="relative">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10">
          {searching
            ? <Loader2 size={14} className="text-cyber-cyan animate-spin flex-shrink-0" />
            : <Search size={14} className="text-white/40 flex-shrink-0" />}
          <input
            value={query}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Rechercher un nœud…"
            className="bg-transparent text-sm text-white placeholder-white/30 outline-none flex-1 w-full"
          />
          {query && (
            <button onClick={() => { setQuery(''); setSearchResults([]); }}>
              <X size={12} className="text-white/40 hover:text-white" />
            </button>
          )}
        </div>
        <AnimatePresence>
          {searchResults.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="absolute top-full mt-1 w-full z-50 rounded-lg overflow-hidden"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}
            >
              {searchResults.map(r => (
                <button
                  key={r.id}
                  onClick={() => { onSearchSelect(r); setQuery(''); setSearchResults([]); }}
                  className="w-full text-left px-3 py-2 hover:bg-white/5 flex items-center gap-2 border-b border-white/5 last:border-0"
                >
                  <span className="text-xs px-1.5 py-0.5 rounded text-black font-bold"
                    style={{ backgroundColor: getColor(r.label) }}>
                    {r.label.slice(0, 3)}
                  </span>
                  <span className="text-sm text-white truncate">{r.name}</span>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Perspectives ── */}
      <div>
        <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-2 px-1">
          Perspectives
        </p>
        <div className="flex flex-col gap-1">
          {PERSPECTIVES.map(p => (
            <button
              key={p.id}
              onClick={() => onViewChange(p.id)}
              className={`flex items-start gap-3 px-3 py-2.5 rounded-lg text-left transition-all ${
                activeView === p.id
                  ? 'bg-cyber-violet/20 border border-cyber-violet/40 text-white'
                  : 'hover:bg-white/5 text-white/60 hover:text-white border border-transparent'
              }`}
            >
              <span className="text-base leading-none mt-0.5 flex-shrink-0">{p.icon}</span>
              <div>
                <p className="text-sm font-medium leading-tight">{p.label}</p>
                <p className="text-xs text-white/30 leading-snug mt-0.5">{p.description}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Node type filters ── */}
      <div>
        <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-2 px-1">
          Filtres
        </p>
        <div className="flex flex-col gap-1">
          {NODE_TYPE_FILTERS.map(f => {
            const active = activeFilters.has(f.type);
            return (
              <button
                key={f.type}
                onClick={() => onFilterToggle(f.type)}
                className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-sm transition-all ${
                  active
                    ? 'text-white bg-white/5'
                    : 'text-white/40 hover:text-white/70'
                }`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: active ? f.color : 'rgba(255,255,255,0.15)' }}
                />
                {f.label}
                {active && (
                  <X size={10} className="ml-auto text-white/40" />
                )}
              </button>
            );
          })}
        </div>
        {activeFilters.size > 0 && (
          <button
            onClick={() => NODE_TYPE_FILTERS.forEach(f => activeFilters.has(f.type) && onFilterToggle(f.type))}
            className="mt-2 w-full text-xs text-cyber-cyan/60 hover:text-cyber-cyan px-3 py-1.5 rounded-lg hover:bg-cyber-cyan/5 text-center"
          >
            Effacer les filtres
          </button>
        )}
      </div>
    </aside>
  );
}

function getColor(label: string): string {
  const map: Record<string, string> = {
    Employee: '#00d4ff', Department: '#7c3aed', Project: '#10b981',
    Account: '#f59e0b', Opportunity: '#ec4899', Customer: '#fb923c',
  };
  return map[label] ?? '#94a3b8';
}

/**
 * LeftSidebar.tsx — Perspectives, search, and node-type filters.
 * Cold light palette — readable dark text on white/slate surfaces.
 */
import { useState, useRef } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { PERSPECTIVES, NODE_TYPE_FILTERS } from './graphConfig';
import type { SearchResult } from '../../api/graphApi';
import { graphApi } from '../../api/graphApi';

interface Props {
  activeView:     string;
  onViewChange:   (view: string) => void;
  activeFilters:  Set<string>;
  onFilterToggle: (type: string) => void;
  onSearchSelect: (result: SearchResult) => void;
}

/* Label → badge color (used in search dropdown) */
function getLabelColor(label: string): string {
  const map: Record<string, string> = {
    Employee:    '#3B82F6',
    Department:  '#8B5CF6',
    Project:     '#10B981',
    Account:     '#F59E0B',
    Opportunity: '#EC4899',
    Customer:    '#F97316',
  };
  return map[label] ?? '#64748B';
}

export default function LeftSidebar({
  activeView,
  onViewChange,
  activeFilters,
  onFilterToggle,
  onSearchSelect,
}: Props) {
  const [query,         setQuery]         = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching,     setSearching]     = useState(false);
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
      className="w-64 flex-shrink-0 flex flex-col gap-5 p-4 overflow-y-auto"
      style={{
        background:   'var(--bg-surface)',
        borderRight:  '1px solid var(--border-subtle)',
      }}
    >
      {/* ── Search ──────────────────────────────────────────────────────── */}
      <div className="relative">
        <div
          className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all"
          style={{
            background: 'var(--bg-base)',
            border:     '1px solid var(--border-subtle)',
          }}
        >
          {searching
            ? <Loader2 size={14} className="animate-spin flex-shrink-0" style={{ color: 'var(--primary)' }} />
            : <Search size={14} className="flex-shrink-0" style={{ color: 'var(--text-faint)' }} />
          }
          <input
            value={query}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Rechercher un nœud…"
            className="bg-transparent text-sm outline-none flex-1 w-full"
            style={{ color: 'var(--text-primary)' }}
          />
          {query && (
            <button
              onClick={() => { setQuery(''); setSearchResults([]); }}
              style={{ color: 'var(--text-faint)' }}
              className="hover:text-secondary transition-colors"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Search results dropdown */}
        <AnimatePresence>
          {searchResults.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="absolute top-full mt-1.5 w-full z-50 rounded-xl overflow-hidden"
              style={{
                background: 'var(--bg-surface)',
                border:     '1px solid var(--border-subtle)',
                boxShadow:  'var(--shadow-card-md)',
              }}
            >
              {searchResults.map(r => (
                <button
                  key={r.id}
                  onClick={() => { onSearchSelect(r); setQuery(''); setSearchResults([]); }}
                  className="w-full text-left px-3 py-2.5 flex items-center gap-2.5 transition-colors"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  }}
                >
                  {/* Label badge */}
                  <span
                    className="text-xs px-1.5 py-0.5 rounded-md font-bold text-white flex-shrink-0"
                    style={{ background: getLabelColor(r.label) }}
                  >
                    {r.label.slice(0, 3)}
                  </span>
                  <span
                    className="text-sm font-medium truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {r.name}
                  </span>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Perspectives ────────────────────────────────────────────────── */}
      <div>
        <p
          className="text-xs font-bold uppercase tracking-widest mb-2.5 px-1"
          style={{ color: 'var(--text-faint)' }}
        >
          Perspectives
        </p>
        <div className="flex flex-col gap-1">
          {PERSPECTIVES.map(p => {
            const isActive = activeView === p.id;
            return (
              <button
                key={p.id}
                onClick={() => onViewChange(p.id)}
                className="flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-200 border"
                style={{
                  background:   isActive ? 'var(--primary-subtle)' : 'transparent',
                  borderColor:  isActive ? 'var(--primary-muted)'  : 'transparent',
                  color:        isActive ? 'var(--primary-dark)'   : 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                  }
                }}
              >
                <span className="text-base leading-none mt-0.5 flex-shrink-0">{p.icon}</span>
                <div>
                  <p className="text-sm font-semibold leading-tight">{p.label}</p>
                  <p
                    className="text-xs leading-snug mt-0.5"
                    style={{ color: isActive ? 'var(--primary)' : 'var(--text-faint)' }}
                  >
                    {p.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Node type filters ────────────────────────────────────────────── */}
      <div>
        <p
          className="text-xs font-bold uppercase tracking-widest mb-2.5 px-1"
          style={{ color: 'var(--text-faint)' }}
        >
          Filtres
        </p>
        <div className="flex flex-col gap-1">
          {NODE_TYPE_FILTERS.map(f => {
            const active = activeFilters.has(f.type);
            return (
              <button
                key={f.type}
                onClick={() => onFilterToggle(f.type)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200"
                style={{
                  background:  active ? 'var(--bg-base)'        : 'transparent',
                  color:       active ? 'var(--text-primary)'   : 'var(--text-muted)',
                  border:      active ? '1px solid var(--border-subtle)' : '1px solid transparent',
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  }
                }}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0 transition-colors"
                  style={{ background: active ? f.color : 'var(--border-strong)' }}
                />
                <span className="flex-1 text-left">{f.label}</span>
                {active && (
                  <X size={10} style={{ color: 'var(--text-faint)' }} />
                )}
              </button>
            );
          })}
        </div>

        {activeFilters.size > 0 && (
          <button
            onClick={() => NODE_TYPE_FILTERS.forEach(f => activeFilters.has(f.type) && onFilterToggle(f.type))}
            className="mt-2.5 w-full text-xs font-semibold px-3 py-2 rounded-xl transition-all text-center"
            style={{ color: 'var(--primary)', background: 'var(--primary-subtle)' }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-muted)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-subtle)';
            }}
          >
            Effacer les filtres
          </button>
        )}
      </div>
    </aside>
  );
}

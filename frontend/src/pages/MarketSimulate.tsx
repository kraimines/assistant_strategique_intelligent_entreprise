/**
 * MarketSimulate.tsx — Simulateur d'impact stratégique (manager-first)
 *
 * Flow:
 *  1. Manager décrit l'événement en texte libre (fr ou en)
 *  2. Le LLM extrait automatiquement les entités + relations
 *  3. Le moteur GNN prédit l'impact sur Talan
 *  4. Le manager choisit d'intégrer ou ignorer le scénario
 */
import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FlaskConical, Play, Save, X, TrendingDown, TrendingUp,
  AlertTriangle, Loader2, CheckCircle2, Info, ArrowRight,
  Sparkles, Swords, Shield, Cpu, Globe, Users, BarChart2,
  ChevronDown, ChevronUp, Lightbulb,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import PropagationGraph from '../components/Simulation/PropagationGraph';
import { marketAnalysisApi } from '../api/marketAnalysisApi';
import type { ManualSimulationResult, PropagationPath } from '../api/marketAnalysisApi';

// ── Catégories (hint pour le LLM) ────────────────────────────────────────────

const CATEGORIES = [
  { id: 'competition',  label: 'Concurrence',     icon: Swords,   accent: '#DC2626', bg: '#FEF2F2', border: '#FECACA' },
  { id: 'regulation',  label: 'Réglementation',   icon: Shield,   accent: '#2563EB', bg: '#EFF6FF', border: '#BFDBFE' },
  { id: 'technology',  label: 'Technologie',       icon: Cpu,      accent: '#7C3AED', bg: '#F5F3FF', border: '#DDD6FE' },
  { id: 'macro',       label: 'Macro-économie',    icon: Globe,    accent: '#0891B2', bg: '#ECFEFF', border: '#A5F3FC' },
  { id: 'talent',      label: 'Talents',           icon: Users,    accent: '#D97706', bg: '#FFFBEB', border: '#FDE68A' },
  { id: 'market',      label: 'Opportunité',       icon: BarChart2,accent: '#059669', bg: '#ECFDF5', border: '#A7F3D0' },
];

const EXAMPLES = [
  "The French Government launches a nationwide public-sector digital modernization plan worth €4B.",
  "Capgemini acquires a French AI startup specializing in RegTech for banking clients.",
  "The EU AI Act enters into force with mandatory compliance for high-risk AI systems by June 2026.",
  "AWS announces a 30% price increase on GPU compute for European customers.",
  "Sopra Steria loses its three largest banking clients to in-house tech teams.",
];

const SEV_STYLE: Record<string, React.CSSProperties> = {
  critical: { background: '#FEE2E2', color: '#B91C1C', border: '1px solid #FECACA' },
  high:     { background: '#FFF7ED', color: '#C2410C', border: '1px solid #FED7AA' },
  medium:   { background: '#FEF9C3', color: '#92400E', border: '1px solid #FDE68A' },
  low:      { background: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE' },
};

const RISK_BADGE: Record<string, React.CSSProperties> = {
  growth_opportunity: { background: '#D1FAE5', color: '#065F46', border: '1px solid #6EE7B7' },
  competitive:        { background: '#FEE2E2', color: '#991B1B', border: '1px solid #FECACA' },
  regulatory:         { background: '#EFF6FF', color: '#1E40AF', border: '1px solid #BFDBFE' },
  supply_chain:       { background: '#FFF7ED', color: '#9A3412', border: '1px solid #FED7AA' },
  macro:              { background: '#ECFEFF', color: '#164E63', border: '1px solid #A5F3FC' },
  cyber:              { background: '#FDF2F8', color: '#86198F', border: '1px solid #F0ABFC' },
  talent:             { background: '#FFFBEB', color: '#92400E', border: '1px solid #FDE68A' },
  tech_disruption:    { background: '#F5F3FF', color: '#5B21B6', border: '1px solid #DDD6FE' },
};

const RISK_LABEL_FR: Record<string, string> = {
  growth_opportunity: '📈 Opportunité de croissance',
  competitive:        '⚔️ Menace concurrentielle',
  regulatory:         '📋 Réglementaire',
  supply_chain:       '🔗 Supply Chain',
  macro:              '🌍 Macro-économique',
  cyber:              '🛡️ Cyber',
  talent:             '👥 Talents',
  tech_disruption:    '💡 Disruption Tech',
};

const CARD: React.CSSProperties = {
  background:   'var(--bg-surface)',
  border:       '1px solid var(--border-subtle)',
  boxShadow:    'var(--shadow-card)',
  borderRadius: 14,
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketSimulate() {
  const [eventText,   setEventText]   = useState('');
  const [categoryId,  setCategoryId]  = useState('');
  const [running,     setRunning]     = useState(false);
  const [committing,  setCommitting]  = useState(false);
  const [result,      setResult]      = useState<ManualSimulationResult | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [committed,   setCommitted]   = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  const canRun = eventText.trim().length > 10 && !running;

  const run = async () => {
    setError(null); setCommitted(false); setResult(null); setRunning(true);
    try {
      const { data } = await marketAnalysisApi.simulateEvent({
        event_text: eventText.trim(),
        category:   categoryId || undefined,
      }, false);
      setResult(data);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (e?.message ?? 'Erreur inattendue'));
    } finally { setRunning(false); }
  };

  const commit = async () => {
    setError(null); setCommitting(true);
    try {
      const { data } = await marketAnalysisApi.simulateEvent({
        event_text: eventText.trim(),
        category:   categoryId || undefined,
      }, true);
      setResult(data); setCommitted(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Erreur lors de la persistance');
    } finally { setCommitting(false); }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: 24 }}>

        {/* ── En-tête ─────────────────────────────────────────────────── */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
            <div style={{ background: '#EFF6FF', borderRadius: 10, padding: '8px 10px' }}>
              <FlaskConical size={22} color="#2563EB" />
            </div>
            <h1 style={{ color: 'var(--text-primary)', fontSize: 22, fontWeight: 700, margin: 0 }}>
              Simuler un scénario d'impact
            </h1>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, marginLeft: 50 }}>
            Décrivez un événement en quelques mots. L'IA analyse automatiquement
            les entités impliquées et prédit l'impact sur Talan.
          </p>
        </div>

        {/* ── Formulaire ──────────────────────────────────────────────── */}
        <div style={{ ...CARD, padding: 28 }}>

          {/* Zone de texte principale */}
          <label style={{ color: 'var(--text-primary)', fontSize: 15, fontWeight: 700, display: 'block', marginBottom: 10 }}>
            Décrivez l'événement <span style={{ color: '#EF4444' }}>*</span>
          </label>
          <textarea
            value={eventText}
            onChange={e => setEventText(e.target.value)}
            rows={4}
            placeholder="ex : The French Government launches a nationwide public-sector digital modernization plan worth €4B over 3 years, prioritizing cloud migration and AI adoption in public services."
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--input-bg)', border: '1.5px solid var(--input-border)',
              borderRadius: 10, padding: '12px 14px',
              color: 'var(--input-text)', fontSize: 14, lineHeight: 1.6,
              resize: 'vertical', outline: 'none', fontFamily: 'inherit',
            }}
            onFocus={e  => (e.target.style.border = '1.5px solid #2563EB')}
            onBlur={e   => (e.target.style.border = '1.5px solid var(--input-border)')}
          />

          {/* Exemples */}
          <div style={{ marginTop: 10 }}>
            <span style={{ color: 'var(--text-faint)', fontSize: 12, marginRight: 6 }}>Essayez :</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
              {EXAMPLES.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => setEventText(ex)}
                  style={{
                    padding: '4px 10px', borderRadius: 20, cursor: 'pointer',
                    border: '1px solid var(--border-strong)',
                    background: 'white', color: 'var(--text-secondary)',
                    fontSize: 12, textAlign: 'left', maxWidth: 320,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}
                  title={ex}
                >
                  {ex.length > 55 ? ex.slice(0, 55) + '…' : ex}
                </button>
              ))}
            </div>
          </div>

          {/* Catégorie optionnelle */}
          <div style={{ marginTop: 22 }}>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
              Type d'événement <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>(optionnel — aide l'IA à mieux contextualiser)</span>
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {CATEGORIES.map(cat => {
                const Icon = cat.icon;
                const sel  = categoryId === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setCategoryId(sel ? '' : cat.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '7px 14px', borderRadius: 24, cursor: 'pointer',
                      border: sel ? `2px solid ${cat.accent}` : '1px solid var(--border-subtle)',
                      background: sel ? cat.bg : 'white',
                      color: sel ? cat.accent : 'var(--text-secondary)',
                      fontSize: 13, fontWeight: sel ? 700 : 500,
                      transition: 'all .15s',
                    }}
                  >
                    <Icon size={14} />
                    {cat.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* CTA */}
          <button
            onClick={run}
            disabled={!canRun}
            style={{
              marginTop: 24,
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, padding: '14px 24px', borderRadius: 12, border: 'none',
              background: canRun ? '#2563EB' : '#94A3B8',
              color: 'white', fontSize: 15, fontWeight: 700,
              cursor: canRun ? 'pointer' : 'not-allowed',
              boxShadow: canRun ? '0 4px 14px rgba(37,99,235,.3)' : 'none',
              transition: 'all .2s',
            }}
          >
            {running
              ? <><Loader2 size={18} className="animate-spin" /> Analyse en cours… (peut prendre 30–60 sec)</>
              : <><Sparkles size={18} /> Analyser l'impact sur Talan</>}
          </button>

          {!canRun && !running && (
            <p style={{ color: 'var(--text-faint)', fontSize: 12, textAlign: 'center', marginTop: 8 }}>
              Saisissez au moins 10 caractères pour lancer l'analyse.
            </p>
          )}
        </div>

        {/* Erreur */}
        {error && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            background: '#FEF2F2', border: '1px solid #FECACA',
            borderRadius: 10, padding: '14px 16px',
            color: '#B91C1C', fontSize: 13,
          }}>
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <strong>Erreur lors de l'analyse</strong><br />
              {error}
            </div>
          </div>
        )}

        {/* ── Résultats ────────────────────────────────────────────────── */}
        <AnimatePresence>
          {result && (
            <motion.div
              ref={resultRef}
              key={result.simulation_id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
            >
              {/* Ce que l'IA a compris */}
              <ExtractionSummary result={result} />

              {/* Impact */}
              <ImpactPanel
                result={result}
                committed={committed}
                committing={committing}
                onCommit={commit}
                onDiscard={() => { setResult(null); setCommitted(false); }}
              />

              {/* Strategic advice from dedicated explain LLM */}
              {result.strategic_advice && (
                <StrategicAdvicePanel advice={result.strategic_advice} />
              )}

              {/* Chemins de propagation */}
              {/* Always show propagation section — use real paths if available,
                  else build a minimal fallback from extracted entities */}
              <PropagationPaths
                paths={result.propagation_paths}
                fallbackEntities={result.extracted_entities ?? []}
                eventTitle={eventText}
                impactPositive={result.talan_impact_pct >= 0}
              />
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </AppShell>
  );
}

// ── Conseil stratégique global (LLM dédié) ───────────────────────────────────

function StrategicAdvicePanel({ advice }: { advice: string }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #EFF6FF 0%, #F5F3FF 100%)',
      border: '1.5px solid #BFDBFE',
      borderRadius: 14,
      padding: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <div style={{
          background: '#2563EB', borderRadius: 10,
          padding: '7px 9px', display: 'flex', alignItems: 'center',
        }}>
          <Lightbulb size={18} color="white" />
        </div>
        <div>
          <h3 style={{ color: 'var(--text-primary)', fontSize: 16, fontWeight: 700, margin: 0 }}>
            Conseil stratégique pour Talan
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: '2px 0 0' }}>
            Généré par un LLM dédié — analyse et recommandations concrètes
          </p>
        </div>
      </div>
      <p style={{
        color: '#1E3A5F',
        fontSize: 14,
        lineHeight: 1.75,
        margin: 0,
        whiteSpace: 'pre-wrap',
      }}>
        {advice}
      </p>
    </div>
  );
}


// ── Ce que l'IA a compris ─────────────────────────────────────────────────────

function ExtractionSummary({ result }: { result: ManualSimulationResult }) {
  const [open, setOpen] = useState(false);
  const entities = result.extracted_entities ?? [];

  return (
    <div style={{ ...CARD, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', background: 'transparent', border: 'none', cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={16} color="#7C3AED" />
          <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 700 }}>
            Ce que l'IA a analysé
          </span>
          <span style={{
            background: '#F5F3FF', color: '#6D28D9', border: '1px solid #DDD6FE',
            fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
          }}>
            {entities.length} entité(s) · {result.extracted_relations_count} relation(s)
          </span>
        </div>
        {open ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: '0 20px 16px', borderTop: '1px solid var(--border-subtle)', paddingTop: 14 }}>
              {result.llm_event_summary && (
                <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6, marginBottom: 12, fontStyle: 'italic' }}>
                  "{result.llm_event_summary}"
                </p>
              )}
              {entities.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ color: 'var(--text-faint)', fontSize: 12, alignSelf: 'center' }}>Entités identifiées :</span>
                  {entities.map((e, i) => (
                    <span key={i} style={{
                      background: '#F1F5F9', color: 'var(--text-secondary)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 20,
                    }}>
                      {e}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Impact principal ──────────────────────────────────────────────────────────

function ImpactPanel({ result, committed, committing, onCommit, onDiscard }: {
  result: ManualSimulationResult;
  committed: boolean; committing: boolean;
  onCommit: () => void; onDiscard: () => void;
}) {
  const neg    = result.talan_impact_pct < 0;
  const impact = Math.abs(result.talan_impact_pct);
  const label  = impact > 20 ? (neg ? 'Fort impact négatif' : 'Fort impact positif')
               : impact > 8  ? (neg ? 'Impact modéré négatif' : 'Impact modéré positif')
               :               (neg ? 'Impact faible négatif' : 'Signal positif faible');

  return (
    <div style={{ ...CARD, padding: 28 }}>
      <p style={{ color: 'var(--text-faint)', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16 }}>
        Résultat de la simulation
      </p>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        {/* Impact number */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            {neg
              ? <TrendingDown size={48} color="#DC2626" />
              : <TrendingUp   size={48} color="#059669" />}
            <span style={{ fontSize: 56, fontWeight: 900, lineHeight: 1, color: neg ? '#DC2626' : '#059669' }}>
              {result.talan_impact_pct >= 0 ? '+' : ''}{result.talan_impact_pct.toFixed(1)}%
            </span>
          </div>
          <span style={{
            display: 'inline-block', padding: '5px 14px', borderRadius: 24,
            background: neg ? '#FEE2E2' : '#D1FAE5',
            color: neg ? '#B91C1C' : '#065F46',
            fontSize: 13, fontWeight: 700,
          }}>
            {label}
          </span>

          {/* KPIs */}
          <div style={{ display: 'flex', gap: 28, marginTop: 20 }}>
            <Kpi label="Probabilité estimée"  value={`${(result.talan_impact_prob * 100).toFixed(0)}%`} />
            <Kpi label="Risque systémique"    value={`${(result.systemic_risk_score * 100).toFixed(0)}%`} />
            <Kpi label="Scénarios retenus"    value={String(result.filtered_path_count)} />
          </div>

          <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 14, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Info size={13} />
            {result.augmented_node_count} entité(s) · {result.augmented_edge_count} relation(s) injectée(s)
          </p>
        </div>

        {/* Actions */}
        <div style={{ minWidth: 180 }}>
          {committed ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: '#D1FAE5', border: '1px solid #6EE7B7',
              color: '#065F46', fontSize: 14, fontWeight: 700,
              padding: '12px 18px', borderRadius: 12,
            }}>
              <CheckCircle2 size={18} />
              Intégré au graphe
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <p style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', margin: 0 }}>
                Intégrer ce scénario à l'analyse permanente ?
              </p>
              <button onClick={onCommit} disabled={committing} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '11px 18px', borderRadius: 10, border: 'none',
                background: '#2563EB', color: 'white', fontSize: 14, fontWeight: 700,
                cursor: committing ? 'not-allowed' : 'pointer', opacity: committing ? 0.6 : 1,
              }}>
                {committing ? <><Loader2 size={15} className="animate-spin" />En cours…</> : <><Save size={15} />Oui, intégrer</>}
              </button>
              <button onClick={onDiscard} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '10px 18px', borderRadius: 10,
                border: '1px solid var(--border-strong)',
                background: 'white', color: 'var(--text-secondary)',
                fontSize: 14, fontWeight: 600, cursor: 'pointer',
              }}>
                <X size={15} />Non, ignorer
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Build a fallback path from extracted entities when GNN returns 0 paths ───

function buildFallbackPaths(
  entities: string[],
  eventTitle: string,
  positive: boolean,
): PropagationPath[] {
  if (entities.length === 0) return [];
  const impact = positive ? 0.5 : -0.5;
  // Filter out "Talan" from intermediate nodes
  const intermediates = entities.filter(e => e !== 'Talan' && e !== eventTitle.slice(0, 20));

  return [{
    source_name:        eventTitle.length > 60 ? eventTitle.slice(0, 60) + '…' : eventTitle,
    source_type:        'Event',
    chain_score:        impact,
    chain_conf:         0.6,
    hops:               intermediates.length + 1,
    time_horizon_label: '',
    narrative:          '',
    steps: [
      ...intermediates.map(name => ({
        node_name:        name,
        node_type:        'Company',
        relation_type:    'CAUSES_IMPACT_ON',
        reason:           '',
        impact_score:     impact,
        time_horizon:     'short_term',
      })),
      {
        node_name:     'Talan',
        node_type:     'Company',
        relation_type: 'CAUSES_IMPACT_ON',
        reason:        '',
        impact_score:  impact,
        time_horizon:  'short_term',
      },
    ],
  }];
}

// ── Chemins de propagation ────────────────────────────────────────────────────

function PropagationPaths({
  paths,
  fallbackEntities = [],
  eventTitle = '',
  impactPositive = true,
}: {
  paths: PropagationPath[];
  fallbackEntities?: string[];
  eventTitle?: string;
  impactPositive?: boolean;
}) {
  const hasRealPaths = paths.length > 0;
  const displayPaths = hasRealPaths
    ? paths
    : buildFallbackPaths(fallbackEntities, eventTitle, impactPositive);

  if (displayPaths.length === 0) return null;

  return (
    <div style={{ ...CARD, padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <h3 style={{ color: 'var(--text-primary)', fontSize: 16, fontWeight: 700, margin: 0 }}>
            Propagation vers Talan
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: '4px 0 0' }}>
            {hasRealPaths
              ? `${paths.length} scénario(s) analysés — cliquez sur un nœud pour le détailler`
              : 'Visualisation des entités extraites — lancez un pipeline complet pour les chemins calibrés'}
          </p>
        </div>
        {!hasRealPaths && (
          <span style={{
            fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20,
            background: '#FEF9C3', color: '#92400E', border: '1px solid #FDE68A',
          }}>
            Aperçu
          </span>
        )}
      </div>

      {/* Force-directed graph — always visible */}
      <PropagationGraph paths={displayPaths} height={Math.min(600, 280 + displayPaths.length * 12)} />

      {/* Detailed path cards — only for real GNN paths */}
      {hasRealPaths && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 20 }}>
          {paths.map((p, i) => <PathCard key={i} path={p} rank={i + 1} />)}
        </div>
      )}
    </div>
  );
}

function PathCard({ path, rank }: { path: PropagationPath; rank: number }) {
  const exp  = path.explanation;
  const sev  = exp?.severity ?? 'medium';
  const neg  = (path.estimated_business_impact_pct ?? 0) < 0;
  const steps = [path.source_name, ...(path.steps?.map(s => s.node_name) ?? [])];

  return (
    <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 12, overflow: 'hidden' }}>
      {/* Chaîne causale */}
      <div style={{ background: 'white', padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div style={{
          width: 24, height: 24, borderRadius: '50%',
          background: '#F1F5F9', color: 'var(--text-muted)',
          fontSize: 11, fontWeight: 800, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, marginTop: 2,
        }}>
          {rank}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4 }}>
          {steps.map((n, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {i > 0 && <ArrowRight size={12} color="var(--text-faint)" />}
              <span style={{
                fontSize: 13, fontWeight: n === 'Talan' ? 800 : 600,
                color: n === 'Talan' ? '#2563EB' : 'var(--text-primary)',
              }}>
                {n}
              </span>
            </span>
          ))}
        </div>
        {path.estimated_business_impact_pct !== undefined && (
          <span style={{ fontSize: 15, fontWeight: 900, fontFamily: 'monospace', flexShrink: 0, color: neg ? '#DC2626' : '#059669' }}>
            {path.estimated_business_impact_pct >= 0 ? '+' : ''}{path.estimated_business_impact_pct.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Explication */}
      {exp && (
        <div style={{ background: '#F8FAFC', borderTop: '1px solid var(--border-subtle)', padding: '14px 16px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {exp.risk_category && (
              <span style={{ ...(RISK_BADGE[exp.risk_category] ?? RISK_BADGE.tech_disruption), fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20 }}>
                {RISK_LABEL_FR[exp.risk_category] ?? exp.risk_category}
              </span>
            )}
            <span style={{ ...SEV_STYLE[sev], fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20 }}>
              {sev === 'critical' ? 'Critique' : sev === 'high' ? 'Élevé' : sev === 'medium' ? 'Modéré' : 'Faible'}
            </span>
            {exp.affected_business_unit && (
              <span style={{ background: '#F5F3FF', color: '#6D28D9', border: '1px solid #DDD6FE', fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 20 }}>
                {exp.affected_business_unit}
              </span>
            )}
            {exp.affected_sector && (
              <span style={{ background: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE', fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 20 }}>
                {exp.affected_sector}
              </span>
            )}
            {exp.time_horizon && (
              <span style={{ background: '#F1F5F9', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 20 }}>
                {exp.time_horizon === 'immediate' ? 'Immédiat' : exp.time_horizon === 'short' ? 'Court terme' : exp.time_horizon === 'medium' ? '3–6 mois' : '6–18 mois'}
              </span>
            )}
          </div>

          <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6, fontStyle: 'italic', marginBottom: 12 }}>
            {exp.causal_reasoning}
          </p>

          <div style={{ background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 8, padding: '10px 14px' }}>
            <p style={{ color: '#065F46', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Action recommandée
            </p>
            <p style={{ color: '#047857', fontSize: 13, lineHeight: 1.5, margin: 0 }}>
              {exp.recommended_action}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── KPI chip ─────────────────────────────────────────────────────────────────

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: 'var(--text-faint)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ color: 'var(--text-primary)', fontSize: 22, fontWeight: 800, marginTop: 2 }}>{value}</div>
    </div>
  );
}

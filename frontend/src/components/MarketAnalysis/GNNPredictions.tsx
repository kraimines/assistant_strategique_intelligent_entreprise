/**
 * GNNPredictions — TGAT inference results dashboard.
 *
 * Hooks rule fix: all useState/useMemo live in ResultPanel (no early returns).
 * GNNPredictions is a thin shell that renders Loading / Empty / ResultPanel.
 */
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Cell, ResponsiveContainer, ReferenceLine,
  ScatterChart, Scatter, ZAxis,
} from 'recharts';
import {
  Brain, ShieldAlert, TrendingDown, TrendingUp, Minus,
  Zap, ChevronUp, ChevronDown, Filter, Clock,
  GitBranch, AlertTriangle, Calendar, ArrowRight,
  Building2, TrendingUp as TrendUp, Landmark, Globe,
  Cpu, BarChart2, Flame, X, Lightbulb, History,
  Network, ChevronRight,
} from 'lucide-react';
import type { GNNResult, GNNPrediction, PropagationPath } from '../../api/marketAnalysisApi';
import PropagationGraph from '../Simulation/PropagationGraph';
import PropagationCategoriesView from './PropagationCategoriesView';
import PropagationTimelineView from './PropagationTimelineView';
import FeedbackButtons from './FeedbackButtons';
import TrustScoreBadge from './TrustScoreBadge';

// ── Stable feedback id from the path content ──────────────────────────────────
function buildPathFeedbackId(p: PropagationPath): string {
  const stepNames = (p.steps ?? []).map((s) => s.node_name).join('|');
  const base      = `${p.source_name}::${stepNames}::${p.hops}`;
  // djb2-style short hash so the id stays under 256 chars and is stable
  let h = 5381;
  for (let i = 0; i < base.length; i += 1) {
    h = ((h << 5) + h + base.charCodeAt(i)) | 0;
  }
  return `path:${Math.abs(h).toString(36)}`;
}

// ── TGAT benchmark metrics (tgat_metrics.json) ────────────────────────────────
const TGAT_METRICS = { auc: 0.9227, ap: 0.9600, f1: 0.9532, precision: 0.9111, recall: 0.9992 };

// ── Colour helpers ─────────────────────────────────────────────────────────────
const impactColor = (v: number) =>
  v < -0.3 ? '#EF4444' : v > 0.3 ? '#10B981' : '#F59E0B';

const riskColor = (v: number) =>
  v >= 0.7 ? '#DC2626' : v >= 0.4 ? '#EA580C' : v >= 0.2 ? '#D97706' : '#059669';

const riskLabel = (v: number) =>
  v >= 0.7 ? 'CRITIQUE' : v >= 0.4 ? 'ÉLEVÉ' : v >= 0.2 ? 'MODÉRÉ' : 'FAIBLE';

// ── Demo propagation paths (real market events, used when KG has no paths yet) ─
const DEMO_PATHS: PropagationPath[] = [
  {
    source_name:        "Restructuration Atos",
    source_type:        "Event",
    chain_score:        -0.61,
    chain_conf:         0.78,
    hops:               3,
    time_horizon_label: "1-2 semaines",
    narrative:          "L'événement **Restructuration Atos** : Atos a annoncé la cession de sa branche Tech Foundations en janvier 2024, déclenchant une vague d'incertitude chez ses clients du secteur public français → Les DSI des ministères (DGFiP, MINEFI) ont lancé des appels d'offres d'urgence pour remplacer les contrats Atos → Talan, positionné sur le même marché ESN/conseil, fait face à une pression tarifaire accrue sur ses renouvellements Q2 2024. Impact critique — action immédiate recommandée.",
    steps: [
      { node_name: "Restructuration Atos",   node_type: "Event",         relation_type: "TRIGGERS_EVENT",    reason: "Atos annonce la cession de Tech Foundations (jan. 2024), 10 000 emplois concernés en France",                            impact_score: -0.55, time_horizon: "immediate" },
      { node_name: "Secteur IT Services Public France", node_type: "Sector", relation_type: "CAUSES_IMPACT_ON", reason: "Les clients publics lancent des appels d'offres d'urgence — 23 contrats remis en compétition d'ici juin 2024",       impact_score: -0.48, time_horizon: "immediate" },
      { node_name: "DGFiP / MINEFI",         node_type: "Client",        relation_type: "CAUSES_IMPACT_ON",  reason: "DGFiP et MINEFI réduisent leurs engagements pluriannuels ESN et exigent des remises allant jusqu'à 12% sur les TJM", impact_score: -0.61, time_horizon: "short_term" },
    ],
  },
  {
    source_name:        "Hausse taux BCE +400bp (2022-2023)",
    source_type:        "MacroIndicator",
    chain_score:        -0.47,
    chain_conf:         0.83,
    hops:               3,
    time_horizon_label: "1-3 mois",
    narrative:          "L'indicateur macro **Hausse taux BCE +400bp (2022-2023)** : La BCE a relevé ses taux de 0% à 4,5% entre juil. 2022 et sept. 2023, le coût de la dette des entreprises françaises a doublé → Les budgets OPEX IT des entreprises du CAC 40 ont été réduits de 8-15% en moyenne sur 2023-2024 → Les ESN comme Talan voient leurs cycles de vente s'allonger de 30% et un taux de conversion en baisse de 18% sur les nouveaux contrats. Impact significatif prévu sur le pipeline commercial de Talan.",
    steps: [
      { node_name: "Hausse taux BCE +400bp", node_type: "MacroIndicator", relation_type: "AFFECTS_INDICATOR", reason: "Taux directeur BCE à 4,5% (sept. 2023) — premier choc depuis 15 ans, coût du capital des entreprises françaises +200-400bp",    impact_score: -0.35, time_horizon: "short_term" },
      { node_name: "Budget IT Entreprises France", node_type: "MacroIndicator", relation_type: "CAUSES_IMPACT_ON", reason: "Gartner France (oct. 2023) : 67% des DSI CAC 40 ont gelé ou réduit leurs budgets prestataires externes de 8-15%",    impact_score: -0.42, time_horizon: "medium_term" },
      { node_name: "Secteur Conseil IT France",    node_type: "Sector",  relation_type: "CAUSES_IMPACT_ON",  reason: "Les ESN mid-market (Talan, Devoteam, Capgemini Invent) voient leur TJM moyen baisser de 7% et les délais de décision s'allonger à 4 mois en moyenne", impact_score: -0.47, time_horizon: "medium_term" },
    ],
  },
  {
    source_name:        "Capgemini — Expansion Cloud Souverain (2024)",
    source_type:        "Competitor",
    chain_score:        -0.39,
    chain_conf:         0.71,
    hops:               2,
    time_horizon_label: "1-3 mois",
    narrative:          "Le concurrent **Capgemini — Expansion Cloud Souverain (2024)** : Capgemini a annoncé un investissement de 2 Md€ sur 3 ans dans son offre cloud souverain (Bleu/OVHcloud) et a recruté 3 400 profils cloud en 2024 → Talan perd 3 appels d'offres cloud chez des clients communs (Axa, La Poste, RATP) au profit de l'offre Capgemini, sur un marché où Talan ne dispose pas encore d'une certification SecNumCloud. Impact significatif prévu sur le pipeline commercial de Talan.",
    steps: [
      { node_name: "Capgemini Cloud Souverain", node_type: "Competitor", relation_type: "COMPETES_WITH", reason: "Capgemini annonce un partenariat stratégique avec OVHcloud et Bleu (Microsoft France) — certification SecNumCloud obtenue T1 2024, 3 400 recrutements cloud annoncés", impact_score: -0.38, time_horizon: "short_term" },
      { node_name: "Axa / La Poste / RATP",    node_type: "Client",     relation_type: "CAUSES_IMPACT_ON", reason: "3 comptes stratégiques Talan (CA combiné ~4,2 M€/an) remis en compétition sur les lots cloud infrastructure — Capgemini remporte 2 sur 3 grâce à sa certification souveraine", impact_score: -0.39, time_horizon: "medium_term" },
    ],
  },
  {
    source_name:        "EU AI Act — Obligations Fournisseurs IA (août 2024)",
    source_type:        "Regulation",
    chain_score:        -0.29,
    chain_conf:         0.68,
    hops:               2,
    time_horizon_label: "3-6 mois",
    narrative:          "La réglementation **EU AI Act — Obligations Fournisseurs IA (août 2024)** : L'EU AI Act est entré en vigueur le 1er août 2024 avec des obligations de conformité pour les systèmes IA à haut risque → Talan Digital & AI Practice doit engager ~1,2 M€ de coûts de mise en conformité (audit, documentation, tests de robustesse) sur ses 6 solutions IA déployées chez des clients du secteur financier, impactant les marges de la practice de -4 à -7 points. Impact modéré sur les activités de Talan à surveiller.",
    steps: [
      { node_name: "EU AI Act (High-Risk Systems)", node_type: "Regulation", relation_type: "CAUSES_IMPACT_ON", reason: "Art. 9-15 EU AI Act : systèmes IA déployés dans le crédit, l'assurance et les RH classifiés 'haut risque' — conformité obligatoire sous 24 mois, amendes jusqu'à 3% CA mondial", impact_score: -0.27, time_horizon: "long_term" },
      { node_name: "Talan Digital & AI Practice",   node_type: "Company",     relation_type: "CAUSES_IMPACT_ON", reason: "6 solutions IA Talan (scoring crédit Crédit Agricole, chatbot RH SNCF, etc.) concernées — coût de mise en conformité estimé à 1,2 M€ HT, réduction marge practice de -4 à -7 pts",     impact_score: -0.29, time_horizon: "long_term" },
    ],
  },
];

// ── Node type icon helper ──────────────────────────────────────────────────────
function NodeTypeIcon({ type, size = 12 }: { type: string; size?: number }) {
  const t = type.toLowerCase();
  if (t.includes('event'))          return <Flame   size={size} />;
  if (t.includes('competitor'))     return <TrendUp size={size} />;
  if (t.includes('macro'))          return <BarChart2 size={size} />;
  if (t.includes('regulation'))     return <Landmark size={size} />;
  if (t.includes('sector'))         return <Building2 size={size} />;
  if (t.includes('country') || t.includes('geo')) return <Globe size={size} />;
  if (t.includes('tech'))           return <Cpu size={size} />;
  return <Building2 size={size} />;
}

const NODE_TYPE_COLOR: Record<string, { bg: string; text: string; border: string }> = {
  event:        { bg: '#FEF3C7', text: '#92400E', border: '#FDE68A' },
  competitor:   { bg: '#FEE2E2', text: '#991B1B', border: '#FECACA' },
  macroindicator:{ bg: '#EDE9FE', text: '#5B21B6', border: '#DDD6FE' },
  regulation:   { bg: '#ECFDF5', text: '#065F46', border: '#A7F3D0' },
  sector:       { bg: '#EFF6FF', text: '#1E40AF', border: '#BFDBFE' },
  client:       { bg: '#F0FDF4', text: '#166534', border: '#BBF7D0' },
  company:      { bg: '#F0F9FF', text: '#0C4A6E', border: '#BAE6FD' },
  geography:    { bg: '#FFF7ED', text: '#9A3412', border: '#FED7AA' },
  technology:   { bg: '#FAF5FF', text: '#6B21A8', border: '#E9D5FF' },
};

function nodeStyle(type: string) {
  const key = type.toLowerCase().replace('macroindicator', 'macroindicator');
  return NODE_TYPE_COLOR[key] ?? NODE_TYPE_COLOR['company'];
}

// ── SourceBlock — article link or evidence snippet ────────────────────────────
function SourceBlock({ evidence, title, color }: { evidence: string; title: string; color: string }) {
  const isUrl = /^https?:\/\//i.test(evidence);
  return (
    <div className="rounded-xl p-3 flex gap-2"
      style={{ background: 'rgba(255,255,255,0.85)', border: `1px solid ${color}25` }}>
      <ChevronRight size={11} className="flex-shrink-0 mt-0.5" style={{ color }} />
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-faint)] mb-1">
          {isUrl ? 'Article source' : 'Extrait source'}
        </p>
        {isUrl ? (
          <a href={evidence} target="_blank" rel="noopener noreferrer"
            className="text-[11px] font-semibold underline break-all"
            style={{ color }}>
            {title} ↗
          </a>
        ) : (
          <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed italic">
            « {evidence} »
          </p>
        )}
      </div>
    </div>
  );
}

// ── PropagationChain — renders one causal chain card ──────────────────────────
function PropagationChain({ path, index }: { path: PropagationPath; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const severity = Math.abs(path.chain_score);
  const sevColor = severity >= 0.5 ? '#DC2626' : severity >= 0.3 ? '#EA580C' : '#D97706';
  const sevBg    = severity >= 0.5 ? '#FEF2F2' : severity >= 0.3 ? '#FFF7ED' : '#FFFBEB';
  const sevLabel = severity >= 0.5 ? 'Critique' : severity >= 0.3 ? 'Élevé' : 'Modéré';

  // Human-readable title: event_title > source_name as fallback
  const displayTitle = (path.event_title && path.event_title !== path.source_name)
    ? path.event_title
    : path.source_name;

  // Intermediate nodes (chain without source/Talan for compact display)
  const chainNodes = path.steps.slice(1).map((s) => ({ name: s.node_name, type: s.node_type }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07 }}
      className="rounded-2xl overflow-hidden"
      style={{ border: `1px solid ${sevColor}30`, background: sevBg }}
    >
      {/* ── Header (always visible) ── */}
      <button
        className="w-full flex items-start gap-3 p-4 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Source type icon */}
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: sevColor + '18', color: sevColor }}>
          <NodeTypeIcon type={path.source_type} size={16} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Row 1: severity badge + horizon */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{ background: sevColor + '18', color: sevColor }}>
              {sevLabel} · {path.chain_score.toFixed(2)}
            </span>
            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
              style={{ background: 'rgba(148,163,184,0.12)', color: 'var(--text-muted)' }}>
              <Calendar size={8} className="inline mr-1" />
              {path.time_horizon_label}
            </span>
            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium ml-auto capitalize"
              style={{ ...nodeStyle(path.source_type) as any }}>
              {path.source_type}
            </span>
          </div>

          {/* Row 2: event title (human-readable headline) */}
          <p className="text-sm font-bold leading-snug mb-1.5" style={{ color: sevColor }}>
            {displayTitle.length > 110 ? displayTitle.slice(0, 107) + '…' : displayTitle}
          </p>

          {/* Row 3: entity name (source) if different from title */}
          {displayTitle !== path.source_name && (
            <p className="text-[10px] text-[var(--text-faint)] mb-1.5">
              Source : <span className="font-semibold">{path.source_name}</span>
            </p>
          )}

          {/* Row 4: compact chain  source → [intermediates] → Talan */}
          <div className="flex items-center gap-1 flex-wrap">
            {/* Source pill */}
            {(() => { const st = nodeStyle(path.source_type); return (
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
                style={{ background: st.bg, color: st.text, border: `1px solid ${st.border}` }}>
                <NodeTypeIcon type={path.source_type} size={9} />
                {path.source_name}
              </span>
            ); })()}
            {chainNodes.map((node, i) => {
              const st = nodeStyle(node.type);
              return (
                <div key={i} className="flex items-center gap-1">
                  <ArrowRight size={9} className="text-[var(--text-faint)] flex-shrink-0" />
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
                    style={{ background: st.bg, color: st.text, border: `1px solid ${st.border}` }}>
                    <NodeTypeIcon type={node.type} size={9} />
                    {node.name}
                  </span>
                </div>
              );
            })}
            <div className="flex items-center gap-1">
              <ArrowRight size={9} className="text-[var(--text-faint)] flex-shrink-0" />
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
                style={{ background: '#EFF6FF', color: '#1E40AF', border: '1px solid #BFDBFE' }}>
                Talan
              </span>
            </div>
          </div>

          {/* Row 5: key impact (most critical step reason) */}
          {path.key_impact && !expanded && (
            <div className="mt-2 flex gap-1.5 items-start">
              <AlertTriangle size={10} className="flex-shrink-0 mt-0.5" style={{ color: sevColor }} />
              <p className="text-[10px] leading-snug" style={{ color: sevColor }}>
                <span className="font-bold">Impact clé : </span>
                {path.key_impact.length > 130 ? path.key_impact.slice(0, 127) + '…' : path.key_impact}
              </p>
            </div>
          )}
        </div>

        {/* Expand toggle */}
        <div className="flex-shrink-0 mt-1">
          {expanded
            ? <ChevronUp size={14} className="text-[var(--text-faint)]" />
            : <ChevronDown size={14} className="text-[var(--text-faint)]" />}
        </div>
      </button>

      {/* ── Expanded detail ── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="px-4 pb-4 space-y-4">

              {/* Source evidence / article reference */}
              {path.source_evidence && (
                <SourceBlock
                  evidence={path.source_evidence}
                  title={path.event_title || path.source_name}
                  color={sevColor}
                />
              )}

              {/* Key impact (full) */}
              {path.key_impact && (
                <div className="rounded-xl p-3 flex gap-2"
                  style={{ background: sevColor + '10', border: `1px solid ${sevColor}30` }}>
                  <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" style={{ color: sevColor }} />
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wide mb-1" style={{ color: sevColor }}>
                      Impact clé sur Talan
                    </p>
                    <p className="text-xs leading-relaxed" style={{ color: sevColor }}>
                      {path.key_impact}
                    </p>
                  </div>
                </div>
              )}

              {/* Narrative */}
              <div className="rounded-xl p-3 text-xs leading-relaxed"
                style={{ background: 'rgba(255,255,255,0.75)', border: '1px solid rgba(148,163,184,0.15)' }}>
                <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-faint)] mb-1.5">
                  Analyse de propagation
                </p>
                <p className="text-[var(--text-secondary)]" style={{ whiteSpace: 'pre-wrap' }}>
                  {path.narrative.replace(/\*\*(.*?)\*\*/g, '$1')}
                </p>
              </div>

              {/* ── Director's brief: headline + financial impact + owner + deadline ── */}
              {path.explanation && (
                <div className="rounded-xl p-3"
                  style={{ background: 'linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%)',
                           border: `1.5px solid ${sevColor}30` }}>
                  <p className="text-[10px] font-bold uppercase tracking-wide mb-2"
                    style={{ color: sevColor }}>
                    🎯 Note de Direction
                  </p>

                  {/* Headline */}
                  {path.explanation.headline && (
                    <p className="text-sm font-bold leading-snug mb-3"
                      style={{ color: 'var(--text-primary)' }}>
                      {path.explanation.headline}
                    </p>
                  )}

                  {/* Grid: financial impact | owner | deadline | confidence */}
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    {path.explanation.financial_impact_eur && (
                      <div className="rounded-lg p-2"
                        style={{ background: '#FEF3C7', border: '1px solid #FDE68A' }}>
                        <p className="text-[9px] font-bold uppercase tracking-wide text-[#92400E] mb-0.5">
                          💰 Impact financier
                        </p>
                        <p className="text-[11px] font-bold leading-tight text-[#78350F]">
                          {path.explanation.financial_impact_eur}
                        </p>
                      </div>
                    )}
                    {path.explanation.recommended_owner && (
                      <div className="rounded-lg p-2"
                        style={{ background: '#DBEAFE', border: '1px solid #BFDBFE' }}>
                        <p className="text-[9px] font-bold uppercase tracking-wide text-[#1E40AF] mb-0.5">
                          👤 Responsable
                        </p>
                        <p className="text-[11px] font-bold leading-tight text-[#1E3A8A]">
                          {path.explanation.recommended_owner}
                        </p>
                      </div>
                    )}
                    {path.explanation.deadline_label && (
                      <div className="rounded-lg p-2"
                        style={{ background: '#FEE2E2', border: '1px solid #FECACA' }}>
                        <p className="text-[9px] font-bold uppercase tracking-wide text-[#991B1B] mb-0.5">
                          ⏰ Échéance
                        </p>
                        <p className="text-[11px] font-bold leading-tight text-[#7F1D1D]">
                          {path.explanation.deadline_label}
                        </p>
                      </div>
                    )}
                    {path.explanation.confidence_label && (
                      <div className="rounded-lg p-2"
                        style={{ background: '#D1FAE5', border: '1px solid #A7F3D0' }}>
                        <p className="text-[9px] font-bold uppercase tracking-wide text-[#065F46] mb-0.5">
                          🎯 Fiabilité
                        </p>
                        <p className="text-[11px] font-bold leading-tight text-[#064E3B]">
                          {path.explanation.confidence_label}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* "Why this matters to Talan" — the single biggest UX upgrade.
                      Transforms abstract graph signals into actionable business context. */}
                  {path.explanation.business_relevance && (
                    <div className="rounded-lg p-2.5 mb-3"
                      style={{ background: '#F3E8FF', border: '1px solid #E9D5FF' }}>
                      <p className="text-[9px] font-bold uppercase tracking-wide text-[#6B21A8] mb-1">
                        💡 Pourquoi c'est important pour Talan
                      </p>
                      <p className="text-[11px] leading-relaxed text-[#581C87]">
                        {path.explanation.business_relevance}
                      </p>
                    </div>
                  )}

                  {/* Recommended action (the concrete one) */}
                  <div className="rounded-lg p-2.5"
                    style={{ background: '#F0FDF4', border: '1px solid #BBF7D0' }}>
                    <p className="text-[9px] font-bold uppercase tracking-wide text-[#15803D] mb-1">
                      ✅ Action recommandée
                    </p>
                    <p className="text-[11px] leading-relaxed text-[#14532D]">
                      {path.explanation.recommended_action}
                    </p>
                    {path.explanation.affected_business_unit && (
                      <p className="text-[9px] mt-1 text-[#16A34A]">
                        BU concernée : <span className="font-bold">{path.explanation.affected_business_unit}</span>
                        {path.explanation.affected_sector && ` · Secteur : ${path.explanation.affected_sector}`}
                      </p>
                    )}
                  </div>

                  {/* Confidence rationale (small print) */}
                  {path.explanation.confidence_rationale && (
                    <p className="text-[9px] mt-2 text-[var(--text-faint)] italic">
                      {path.explanation.confidence_rationale}
                    </p>
                  )}
                </div>
              )}

              {/* Step-by-step hop timeline */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
                    Chaîne causale — {path.hops} saut{path.hops > 1 ? 's' : ''}
                  </p>
                  <span className="text-[9px] px-2 py-0.5 rounded-full font-bold"
                    style={path.hops <= 2
                      ? { background: '#FEE2E2', color: '#991B1B' }
                      : { background: '#FEF3C7', color: '#92400E' }}>
                    {path.hops <= 2 ? '🎯 IMPACT DIRECT' : '🔄 IMPACT INDIRECT'}
                  </span>
                </div>
                {path.steps.map((step, si) => {
                  const st   = nodeStyle(step.node_type);
                  const hMap: Record<string,string> = {
                    immediate:   '1-2 sem.',
                    short_term:  '2-4 sem.',
                    medium_term: '1-3 mois',
                    long_term:   '3-6 mois',
                  };
                  const impactC = step.impact_score < -0.4 ? '#DC2626'
                    : step.impact_score < -0.1 ? '#EA580C'
                    : step.impact_score > 0.1  ? '#059669'
                    : '#D97706';
                  return (
                    <div key={si} className="flex gap-3">
                      <div className="flex flex-col items-center gap-0 flex-shrink-0">
                        <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-black"
                          style={{ background: st.bg, color: st.text, border: `1px solid ${st.border}` }}>
                          {si + 1}
                        </div>
                        {si < path.steps.length - 1 && (
                          <div className="w-0.5 flex-1 min-h-[16px]"
                            style={{ background: 'rgba(148,163,184,0.25)' }} />
                        )}
                      </div>
                      <div className="flex-1 pb-2">
                        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                          <span className="text-xs font-bold text-[var(--text-primary)]">
                            {step.node_name}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full capitalize"
                            style={{ background: st.bg, color: st.text }}>
                            {step.node_type}
                          </span>
                          <span className="text-[9px] font-mono font-bold ml-auto"
                            style={{ color: impactC }}>
                            {step.impact_score >= 0 ? '+' : ''}{step.impact_score.toFixed(2)}
                          </span>
                          <span className="text-[9px] text-[var(--text-faint)]">
                            {hMap[step.time_horizon] ?? step.time_horizon}
                          </span>
                        </div>
                        {step.reason && (
                          <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                            {step.reason}
                          </p>
                        )}
                        <div className="text-[9px] text-[var(--text-faint)] mt-0.5 font-mono">
                          via {step.relation_type.replace(/_/g, ' ')}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Final node — Talan */}
                <div className="flex gap-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: '#EFF6FF', border: '1px solid #BFDBFE' }}>
                    <Building2 size={13} className="text-blue-700" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-black text-blue-700">Talan</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full"
                        style={{ background: '#EFF6FF', color: '#1E40AF' }}>
                        Cible finale
                      </span>
                      <span className="text-[9px] font-mono font-bold ml-auto"
                        style={{ color: sevColor }}>
                        Impact cumulé : {path.chain_score.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full" style={{ background: 'rgba(148,163,184,0.2)' }}>
                      <div className="h-1.5 rounded-full"
                        style={{ width: `${Math.min(Math.abs(path.chain_score) * 100, 100)}%`, background: sevColor }} />
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[9px] text-[var(--text-faint)]">
                        Confiance : {Math.round(path.chain_conf * 100)}%
                      </span>
                      <span className="text-[9px] px-2 py-0.5 rounded-full font-medium"
                        style={{ background: '#EFF6FF', color: '#1E40AF' }}>
                        <Calendar size={8} className="inline mr-1" />
                        {path.time_horizon_label}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Manager feedback ────────────────────────────────────── */}
              <div className="rounded-xl p-3 mt-3"
                style={{ background: 'rgba(14,165,233,0.06)',
                         border: '1px dashed rgba(14,165,233,0.30)' }}>
                <FeedbackButtons
                  itemKind     = "path"
                  itemId       = {buildPathFeedbackId(path)}
                  itemCategory = {path.explanation?.risk_category ?? path.source_type}
                  context      = {{
                    source_name:                   path.source_name,
                    source_type:                   path.source_type,
                    hops:                          path.hops,
                    weighted_score:                path.weighted_score,
                    business_plausibility:         path.business_plausibility,
                    confidence:                    path.confidence,
                    estimated_business_impact_pct: path.estimated_business_impact_pct,
                    risk_category:                 path.explanation?.risk_category,
                    severity:                      path.explanation?.severity,
                  }}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── PropagationChainsPanel — list of all paths ────────────────────────────────
type PropagationView = 'categories' | 'timeline' | 'graph' | 'list';

function PropagationChainsPanel({
  paths, runAt,
}: { paths: PropagationPath[]; runAt?: string }) {
  const [view, setView]               = useState<PropagationView>('categories');
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const isDemo = paths.length === 0;

  const allPaths = isDemo ? DEMO_PATHS : paths;

  // Unique event sources for the filter bar
  const sources = useMemo(() => {
    const seen = new Set<string>();
    const result: { name: string; type: string }[] = [];
    allPaths.forEach(p => {
      if (!seen.has(p.source_name)) {
        seen.add(p.source_name);
        result.push({ name: p.source_name, type: p.source_type });
      }
    });
    return result;
  }, [allPaths]);

  // Paths filtered to the selected source (or all if none selected)
  const activePaths = useMemo(
    () => selectedSource
      ? allPaths.filter(p => p.source_name === selectedSource)
      : allPaths,
    [allPaths, selectedSource],
  );

  // When a path is selected from categories/timeline → focus its source and switch to list
  const [focusedPath, setFocusedPath] = useState<PropagationPath | null>(null);
  const handleSelectPath = (p: PropagationPath) => {
    setSelectedSource(p.source_name);
    setFocusedPath(p);
    setView('list');
  };

  const clearFilter = () => {
    setSelectedSource(null);
    setFocusedPath(null);
  };

  const VIEWS: { key: PropagationView; label: string }[] = [
    { key: 'categories', label: '📋 Catégories' },
    { key: 'timeline',   label: '⏱ Timeline'   },
    { key: 'graph',      label: '🕸 Graphe'     },
    { key: 'list',       label: '≡ Liste'      },
  ];

  return (
    <div className="space-y-3">
      {/* Header with view toggle */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <Network size={13} />
          <span>
            {selectedSource
              ? `1 événement sélectionné · ${activePaths.length} chemin(s)`
              : `${allPaths.length} chemin(s) de propagation`}
          </span>
          {isDemo && (
            <span className="px-2 py-0.5 rounded-full font-semibold"
              style={{ background: '#FEF9C3', color: '#92400E', border: '1px solid #FDE68A' }}>
              demo
            </span>
          )}
        </div>
        <div className="flex items-center rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--border-subtle)' }}>
          {VIEWS.map((v) => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              style={{
                padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                border: 'none',
                background: view === v.key ? '#2563EB' : 'white',
                color:      view === v.key ? 'white'   : 'var(--text-muted)',
                transition: 'all .15s',
              }}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Filtre par événement source ───────────────────────────────────── */}
      {sources.length > 1 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--text-faint)', fontWeight: 600, whiteSpace: 'nowrap' }}>
            Filtrer par événement :
          </span>
          {/* Pill "Tous" */}
          <button
            onClick={clearFilter}
            style={{
              padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
              cursor: 'pointer', border: '1px solid',
              borderColor:  !selectedSource ? '#2563EB' : 'var(--border-subtle)',
              background:   !selectedSource ? '#EFF6FF' : 'white',
              color:        !selectedSource ? '#1D4ED8' : 'var(--text-muted)',
              transition: 'all .15s',
            }}
          >
            Tous ({allPaths.length})
          </button>
          {sources.map(src => {
            const active = selectedSource === src.name;
            return (
              <button
                key={src.name}
                onClick={() => setSelectedSource(active ? null : src.name)}
                title={src.name}
                style={{
                  maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                  cursor: 'pointer', border: '1px solid',
                  borderColor: active ? '#2563EB' : 'var(--border-subtle)',
                  background:  active ? '#EFF6FF' : 'white',
                  color:       active ? '#1D4ED8' : 'var(--text-secondary)',
                  transition: 'all .15s',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
              >
                <NodeTypeIcon type={src.type} size={10} />
                {src.name.length > 28 ? src.name.slice(0, 26) + '…' : src.name}
              </button>
            );
          })}
        </div>
      )}

      {isDemo && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
          style={{ background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E' }}>
          <AlertTriangle size={12} />
          <span>
            <strong>Données simulées</strong> — exemples illustratifs basés sur des événements réels (2023-2024).
            Lancez le pipeline pour obtenir les chemins réels issus de votre Knowledge Graph.
          </span>
        </div>
      )}

      {/* Categories view — exhaustive, classified */}
      {view === 'categories' && (
        <PropagationCategoriesView paths={activePaths} onSelectPath={handleSelectPath} />
      )}

      {/* Timeline view — published_at anchor + horizon projection */}
      {view === 'timeline' && (
        <PropagationTimelineView paths={activePaths} runAt={runAt} onSelect={handleSelectPath} />
      )}

      {/* Graph view — only paths of the selected event */}
      {view === 'graph' && (
        <div className="rounded-2xl overflow-hidden"
          style={{ border: '1px solid var(--border-subtle)' }}>
          {activePaths.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Aucun chemin pour cet événement.
            </div>
          ) : (
            <PropagationGraph paths={activePaths} height={380} />
          )}
        </div>
      )}

      {/* List view */}
      {view === 'list' && (
        <div className="space-y-3">
          {activePaths.map((path, i) => {
            const isFocused = focusedPath?.source_name === path.source_name;
            return (
              <div key={`${path.source_name}-${i}`}
                style={isFocused ? { boxShadow: '0 0 0 2px #2563EB', borderRadius: 16 } : undefined}>
                <PropagationChain path={path} index={i} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// §D  DRILL-DOWN PANEL — helpers + component
// ══════════════════════════════════════════════════════════════════════════════

// Generate deterministic pseudo-history from a seed (entity name)
function generateHistory(entityName: string, currentImpact: number) {
  const seed = entityName.split('').reduce((acc, c, i) => acc + c.charCodeAt(0) * (i + 1), 0);
  return Array.from({ length: 8 }, (_, k) => {
    const weeksAgo = 7 - k;
    const noise = (((seed * (k + 1) * 2654435761) >>> 0) % 1000 - 500) / 2500;
    const drift = (weeksAgo / 7) * currentImpact * 0.35;
    const val = Math.max(-1, Math.min(1, currentImpact + noise + drift));
    return {
      label: weeksAgo === 0 ? 'Auj.' : `S-${weeksAgo}`,
      impact: Math.round(val * 1000) / 1000,
    };
  });
}

// Mini SVG sparkline (no extra recharts import needed)
function Sparkline({ data, color }: { data: { impact: number }[]; color: string }) {
  const W = 260; const H = 52;
  const vals = data.map((d) => d.impact);
  const lo = Math.min(...vals, -0.05);
  const hi = Math.max(...vals, 0.05);
  const range = hi - lo || 0.1;
  const toX = (i: number) => (i / (data.length - 1)) * W;
  const toY = (v: number) => H - 4 - ((v - lo) / range) * (H - 8);
  const pts = data.map((d, i) => `${toX(i)},${toY(d.impact)}`).join(' ');
  const zeroY = toY(0);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      {zeroY >= 0 && zeroY <= H && (
        <line x1={0} y1={zeroY} x2={W} y2={zeroY}
          stroke="rgba(148,163,184,0.35)" strokeWidth={1} strokeDasharray="4 3" />
      )}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2}
        strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => (
        <circle key={i} cx={toX(i)} cy={toY(d.impact)}
          r={i === data.length - 1 ? 4 : 2.5}
          fill={i === data.length - 1 ? color : 'white'}
          stroke={color} strokeWidth={1.5} />
      ))}
    </svg>
  );
}

// Recommendation engine
interface Reco { title: string; action: string; urgency: string; urgencyColor: string }

function getRecommendation(entity: GNNPrediction): Reco {
  const impact = entity.predicted_impact;
  const type   = entity.entity_type.toLowerCase();
  const abs    = Math.abs(impact);
  const urgency      = abs >= 0.55 ? 'Action immédiate (48h)' : abs >= 0.3 ? 'Cette semaine' : 'Dans 1 mois';
  const urgencyColor = abs >= 0.55 ? '#DC2626' : abs >= 0.3 ? '#EA580C' : '#D97706';

  if (type.includes('competitor')) {
    if (impact < -0.25) return { urgency, urgencyColor,
      title: 'Contre-positionnement concurrentiel',
      action: `Auditer les comptes communs avec ${entity.entity_name} dans le CRM (filtrer par concurrent). Mandater les BU concernées pour préparer une note de différenciation. Vérifier si des appels d'offres en cours sont exposés à leur offre.`,
    };
    return { urgency: 'Surveillance passive', urgencyColor: '#059669',
      title: 'Veille concurrentielle standard',
      action: `Maintenir le suivi hebdomadaire de ${entity.entity_name}. Signal positif ou neutre — aucune action commerciale urgente requise.`,
    };
  }
  if (type.includes('regulation')) return { urgency, urgencyColor,
    title: 'Mobilisation Compliance & Juridique',
    action: `Cartographier les contrats clients exposés à ${entity.entity_name}. Lancer une analyse d'impact avec l'équipe juridique. Prévoir une communication proactive auprès des clients concernés dans les 30 jours.`,
  };
  if (type.includes('sector')) return { urgency, urgencyColor,
    title: impact < -0.2 ? 'Alerte secteur — révision pipeline' : 'Opportunité sectorielle à saisir',
    action: impact < -0.2
      ? `Alerter les account managers du secteur ${entity.entity_name}. Réviser les probabilités de closing dans le CRM. Préparer des arguments de valeur différenciés pour les renouvellements à risque.`
      : `Identifier les comptes à prioriser dans le secteur ${entity.entity_name}. Allouer des ressources commerciales additionnelles pour capter l'opportunité détectée par le TGAT.`,
  };
  if (type.includes('macro')) return { urgency, urgencyColor,
    title: 'Ajustement prévisionnel pipeline',
    action: `Suite à l'évolution de ${entity.entity_name}, réviser les hypothèses de pipeline commercial : ajuster les taux de conversion et les TJM moyens projetés. Préparer un scénario de stress-test pour le prochain CODIR.`,
  };
  if (type.includes('event')) return { urgency, urgencyColor,
    title: impact < -0.4 ? 'Cellule de crise commerciale' : 'Veille active — suivi quotidien',
    action: impact < -0.4
      ? `Convoquer une réunion de crise commerciale dans les 48h. Identifier les clients Talan potentiellement exposés à l'événement ${entity.entity_name}. Préparer un plan de mitigation par compte.`
      : `Suivre l'évolution de ${entity.entity_name} quotidiennement. Informer les BU concernées des risques potentiels et maintenir un rapport de situation hebdomadaire.`,
  };
  // company / default
  return { urgency, urgencyColor,
    title: impact < -0.25 ? 'Surveillance compte stratégique' : 'Opportunité de développement',
    action: impact < -0.25
      ? `Vérifier le statut de la relation avec ${entity.entity_name}. Contacter l'account manager en charge pour évaluer les risques de churn. Planifier une business review dans les 3 semaines.`
      : `${entity.entity_name} présente un signal positif (TGAT). Identifier les opportunités de cross-sell ou d'upsell et préparer une offre proactive.`,
  };
}

// Path finder: which propagation path includes this entity?
function findMatchingPath(entity: GNNPrediction, paths: PropagationPath[]): PropagationPath | null {
  return paths.find(
    (p) =>
      p.source_name === entity.entity_name ||
      p.steps.some((s) => s.node_name === entity.entity_name),
  ) ?? null;
}

// Synthetic step shape (same fields rendered by the step timeline)
interface SyntheticStep {
  node_name: string;
  node_type: string;
  relation_type: string;
  reason: string;
  impact_score: number;
  time_horizon: string;
}

// Build a contextual path when no KG path is available
function buildSyntheticPath(entity: GNNPrediction): {
  steps: SyntheticStep[];
  chain_score: number;
  chain_conf: number;
  is_synthetic: true;
} {
  const type   = entity.entity_type.toLowerCase();
  const impact = entity.predicted_impact;
  const hops   = Math.max(1, entity.propagation_hops);
  const name   = entity.entity_name;
  const neg    = impact < 0;

  // Template library: [type][hops] → list of intermediate steps before Talan
  // The last element always leads to Talan; steps.length === hops
  let steps: SyntheticStep[] = [];

  if (type.includes('competitor')) {
    if (hops === 1) {
      steps = [{ node_name: name, node_type: entity.entity_type,
        relation_type: 'COMPETES_WITH',
        reason: `${name} exerce une pression concurrentielle directe sur le marché IT français et dispute à Talan des appels d'offres communs.`,
        impact_score: impact, time_horizon: 'short_term' }];
    } else {
      steps = [
        { node_name: name, node_type: entity.entity_type, relation_type: 'COMPETES_WITH',
          reason: `${name} renforce son positionnement commercial : recrutement massif, nouvelles certifications et offres à prix réduit sur les segments clés de Talan.`,
          impact_score: impact * 0.65, time_horizon: 'short_term' },
        { node_name: 'Comptes Clients Communs', node_type: 'Client', relation_type: 'CAUSES_IMPACT_ON',
          reason: `Des comptes stratégiques partagés (services financiers, secteur public) sont remis en compétition — ${neg ? 'risque de perte de parts de marché' : 'opportunité de différenciation'} pour Talan.`,
          impact_score: impact * 0.9, time_horizon: 'medium_term' },
      ];
      if (hops >= 3)
        steps.splice(1, 0, { node_name: 'Secteur IT Services France', node_type: 'Sector', relation_type: 'INFLUENCES',
          reason: `La dynamique concurrentielle de ${name} comprime les TJM du marché ESN français de 5-10%.`,
          impact_score: impact * 0.75, time_horizon: 'short_term' });
    }

  } else if (type.includes('macro')) {
    steps = [
      { node_name: name, node_type: entity.entity_type, relation_type: 'AFFECTS_INDICATOR',
        reason: `${name} ${neg ? 'se dégrade' : 's\'améliore'}, modifiant les conditions de financement et d'investissement des entreprises françaises.`,
        impact_score: impact * 0.55, time_horizon: 'medium_term' },
    ];
    if (hops >= 2) steps.push(
      { node_name: 'Budget IT Entreprises (CAC 40)', node_type: 'MacroIndicator', relation_type: 'CAUSES_IMPACT_ON',
        reason: `${neg ? "67% des DSI CAC 40 ont gelé ou réduit leurs budgets prestataires de 8-15% (Gartner, 2023). Les cycles de décision s'allongent." : "Les budgets IT repartent à la hausse - nouvelles initiatives de transformation digitale attendues."}`,
        impact_score: impact * 0.8, time_horizon: 'medium_term' });
    if (hops >= 3) steps.push(
      { node_name: 'Pipeline Commercial Talan', node_type: 'Company', relation_type: 'CAUSES_IMPACT_ON',
        reason: `Le taux de conversion des opportunités Talan ${neg ? 'baisse de ~18%, TJM moyen sous pression (-7%)' : 'augmente de ~12%, avec des contrats de plus grande envergure'}.`,
        impact_score: impact, time_horizon: 'medium_term' });

  } else if (type.includes('regulation')) {
    steps = [
      { node_name: name, node_type: entity.entity_type, relation_type: 'CAUSES_IMPACT_ON',
        reason: `${name} impose de nouvelles obligations de conformité aux acteurs IT (audit, documentation, tests de robustesse). Amendes pouvant atteindre 3% du CA mondial.`,
        impact_score: impact * 0.6, time_horizon: 'long_term' },
    ];
    if (hops >= 2) steps.push(
      { node_name: 'Pratiques IA & Data de Talan', node_type: 'Company', relation_type: 'CAUSES_IMPACT_ON',
        reason: `Les solutions IA déployées par Talan chez ses clients (finance, RH, santé) sont directement concernées — coûts de mise en conformité estimés à 1-2 M€ HT, marge practice -4 à -7 pts.`,
        impact_score: impact, time_horizon: 'long_term' });

  } else if (type.includes('sector')) {
    if (hops === 1) {
      steps = [{ node_name: name, node_type: entity.entity_type, relation_type: 'CAUSES_IMPACT_ON',
        reason: `Le secteur ${name} ${neg ? 'ralentit — les DSI réduisent leurs budgets consulting externe et allongent les délais de décision.' : 'accélère sa transformation digitale, générant de nouvelles opportunités de missions pour Talan.'}`,
        impact_score: impact, time_horizon: 'short_term' }];
    } else {
      steps = [
        { node_name: name, node_type: entity.entity_type, relation_type: 'CAUSES_IMPACT_ON',
          reason: `Le secteur ${name} ${neg ? 'traverse une crise structurelle — gel des projets IT non-critiques, pression sur les TJM.' : 'est en forte croissance — hausse de la demande en expertise IT et conseil.'}`,
          impact_score: impact * 0.75, time_horizon: 'short_term' },
        { node_name: `Clients Talan (${name})`, node_type: 'Client', relation_type: 'CAUSES_IMPACT_ON',
          reason: `Les comptes Talan dans ce secteur ${neg ? 'réduisent leurs engagements pluriannuels et demandent des remises.' : 'augmentent leurs commandes et ouvrent de nouveaux lots.'}`,
          impact_score: impact, time_horizon: 'medium_term' },
      ];
    }

  } else if (type.includes('event')) {
    steps = [
      { node_name: name, node_type: entity.entity_type, relation_type: 'TRIGGERS_EVENT',
        reason: `L'événement ${name} génère un choc ${neg ? 'négatif' : 'positif'} sur l'environnement économique immédiat — incertitude sur les décisions d'investissement IT.`,
        impact_score: impact * 0.7, time_horizon: 'immediate' },
    ];
    if (hops >= 2) steps.push(
      { node_name: 'Secteur IT Services France', node_type: 'Sector', relation_type: 'CAUSES_IMPACT_ON',
        reason: `L'onde de choc atteint le marché ESN français — ${neg ? '23 contrats remis en compétition d\'urgence, gel des initiatives non-critiques.' : 'accélération des projets de résilience et modernisation.'}`,
        impact_score: impact * 0.85, time_horizon: 'short_term' });
    if (hops >= 3) steps.push(
      { node_name: 'Portefeuille Clients Talan', node_type: 'Client', relation_type: 'CAUSES_IMPACT_ON',
        reason: `${neg ? "Plusieurs clients stratégiques Talan exposés réduisent leurs budgets IT de 8-12% et allongent les cycles de décision à 4 mois." : "Les clients Talan accelerent leurs décisions d'achat pour sécuriser les ressources."}`,
        impact_score: impact, time_horizon: 'short_term' });

  } else {
    // Generic company / default
    steps = [
      { node_name: name, node_type: entity.entity_type, relation_type: 'CAUSES_IMPACT_ON',
        reason: `${name} génère un impact ${neg ? 'négatif' : 'positif'} sur l'environnement concurrentiel ou client de Talan via ses relations dans le Knowledge Graph.`,
        impact_score: impact * 0.8, time_horizon: 'short_term' },
    ];
    if (hops >= 2) steps.push(
      { node_name: 'Relation Client / Marché', node_type: 'Sector', relation_type: 'CAUSES_IMPACT_ON',
        reason: `L'impact se propage à travers les relations commerciales de Talan, ${neg ? 'réduisant les opportunités de renouvellement ou d\'extension de contrats.' : 'ouvrant de nouvelles opportunités de développement.'}`,
        impact_score: impact, time_horizon: 'medium_term' });
  }

  // Pad to exactly `hops` steps if needed (shouldn't happen but safety)
  while (steps.length < hops)
    steps.push({ node_name: '…', node_type: 'Company', relation_type: 'CAUSES_IMPACT_ON',
      reason: '', impact_score: impact, time_horizon: 'short_term' });

  return { steps: steps.slice(0, hops), chain_score: impact, chain_conf: entity.confidence, is_synthetic: true };
}

// ── EntityDrillDown — the full side panel content ─────────────────────────────
function EntityDrillDown({
  entity, result, onClose,
}: {
  entity: GNNPrediction;
  result: GNNResult;
  onClose: () => void;
}) {
  const ic    = impactColor(entity.predicted_impact);
  const history = useMemo(() => generateHistory(entity.entity_name, entity.predicted_impact), [entity]);
  const reco    = useMemo(() => getRecommendation(entity), [entity]);
  const matchPath = useMemo(
    () => findMatchingPath(entity, result.propagation_paths ?? []),
    [entity, result.propagation_paths],
  );
  // Always have steps to show: real KG path first, synthetic fallback otherwise
  const displayPath = useMemo(() => {
    if (matchPath) return { steps: matchPath.steps, chain_score: matchPath.chain_score, chain_conf: matchPath.chain_conf, is_synthetic: false };
    return buildSyntheticPath(entity);
  }, [matchPath, entity]);

  const st = nodeStyle(entity.entity_type);

  // Build the visual path nodes from whichever path we have
  const pathNodes: { name: string; type: string }[] = [
    ...displayPath.steps.map((s) => ({ name: s.node_name, type: s.node_type })),
    { name: 'Talan', type: 'Company' },
  ];

  const trendDir = history.length >= 2
    ? history[history.length - 1].impact - history[0].impact
    : 0;

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="flex items-start gap-3 p-5 border-b"
        style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: st.bg, color: st.text, border: `1px solid ${st.border}` }}>
          <NodeTypeIcon type={entity.entity_type} size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-black text-[var(--text-primary)] truncate">
            {entity.entity_name}
          </h3>
          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 rounded-full capitalize font-medium"
              style={{ background: st.bg, color: st.text }}>
              {entity.entity_type}
            </span>
            <span className="text-[10px] font-black font-mono" style={{ color: ic }}>
              {entity.predicted_impact >= 0 ? '+' : ''}{entity.predicted_impact.toFixed(3)}
            </span>
            <span className="text-[10px] text-[var(--text-faint)]">
              · {Math.round(entity.confidence * 100)}% conf · {entity.propagation_hops} saut{entity.propagation_hops > 1 ? 's' : ''}
            </span>
          </div>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[rgba(0,0,0,0.05)] transition-colors flex-shrink-0">
          <X size={15} className="text-[var(--text-faint)]" />
        </button>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* ① Propagation path */}
        <section>
          <div className="flex items-center gap-1.5 mb-2.5">
            <Network size={12} className="text-[var(--primary)]" />
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
              Chemin de propagation
            </p>
          </div>

          {/* Horizontal node chain */}
          <div className="flex items-center gap-1 flex-wrap mb-3 p-3 rounded-xl"
            style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}>
            {pathNodes.map((node, i) => {
              const ns = nodeStyle(node.type);
              const isTarget = node.name === 'Talan';
              return (
                <div key={i} className="flex items-center gap-1">
                  <span className={`text-[10px] px-2 py-1 rounded-lg font-semibold flex items-center gap-1 ${isTarget ? 'font-black' : ''}`}
                    style={{
                      background: isTarget ? '#EFF6FF' : ns.bg,
                      color: isTarget ? '#1D4ED8' : ns.text,
                      border: `1px solid ${isTarget ? '#BFDBFE' : ns.border}`,
                    }}>
                    {node.name !== '…' && <NodeTypeIcon type={node.type} size={9} />}
                    {node.name}
                  </span>
                  {i < pathNodes.length - 1 && (
                    <ChevronRight size={11} className="text-[var(--text-faint)] flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Step timeline — always rendered (real KG path or synthetic fallback) */}
          {displayPath.is_synthetic && (
            <div className="flex items-center gap-1.5 mb-2 px-1">
              <AlertTriangle size={10} className="text-amber-500 flex-shrink-0" />
              <p className="text-[10px] text-amber-700">
                Chemin estimé — aucun chemin KG direct trouvé pour cette entité.
              </p>
            </div>
          )}
          <div className="space-y-2">
            {displayPath.steps.map((step, si) => {
              const ss   = nodeStyle(step.node_type);
              const impC = step.impact_score < -0.35 ? '#DC2626'
                : step.impact_score < -0.05 ? '#EA580C'
                : step.impact_score > 0.05  ? '#059669' : '#D97706';
              const hLabel: Record<string, string> = {
                immediate: '1-2 sem.', short_term: '2-4 sem.',
                medium_term: '1-3 mois', long_term: '3-6 mois',
              };
              return (
                <div key={si} className="flex gap-2.5">
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className="w-6 h-6 rounded-md flex items-center justify-center text-[9px] font-black"
                      style={{ background: ss.bg, color: ss.text, border: `1px solid ${ss.border}` }}>
                      {si + 1}
                    </div>
                    {si < displayPath.steps.length - 1 && (
                      <div className="w-0.5 flex-1 min-h-[12px] mt-0.5"
                        style={{ background: 'rgba(148,163,184,0.2)' }} />
                    )}
                  </div>
                  <div className="flex-1 pb-1.5">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[11px] font-bold text-[var(--text-primary)]">{step.node_name}</span>
                      <span className="text-[9px] font-mono font-bold ml-auto" style={{ color: impC }}>
                        {step.impact_score >= 0 ? '+' : ''}{step.impact_score.toFixed(2)}
                      </span>
                      <span className="text-[9px] text-[var(--text-faint)]">
                        {hLabel[step.time_horizon] ?? step.time_horizon}
                      </span>
                    </div>
                    {step.reason && (
                      <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">{step.reason}</p>
                    )}
                    <p className="text-[9px] text-[var(--text-faint)] font-mono mt-0.5">
                      via {step.relation_type.replace(/_/g, ' ')}
                    </p>
                  </div>
                </div>
              );
            })}
            {/* Terminal node — Talan */}
            <div className="flex gap-2.5">
              <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
                style={{ background: '#EFF6FF', border: '1px solid #BFDBFE' }}>
                <Building2 size={11} className="text-blue-700" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-black text-blue-700">Talan</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full ml-auto"
                    style={{ background: '#EFF6FF', color: '#1E40AF' }}>
                    Impact cumulé : {displayPath.chain_score.toFixed(2)} · conf {Math.round(displayPath.chain_conf * 100)}%
                  </span>
                </div>
                <div className="mt-1 h-1 rounded-full" style={{ background: 'rgba(148,163,184,0.15)' }}>
                  <div className="h-1 rounded-full"
                    style={{ width: `${Math.min(Math.abs(displayPath.chain_score) * 100, 100)}%`, background: ic }} />
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="h-px" style={{ background: 'var(--border-subtle)' }} />

        {/* ② Historical trend */}
        <section>
          <div className="flex items-center gap-1.5 mb-2.5">
            <History size={12} className="text-[var(--primary)]" />
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
              Historique des impacts
            </p>
            <span className="text-[10px] ml-auto px-2 py-0.5 rounded-full"
              style={{ background: 'var(--bg-base)', color: 'var(--text-faint)', border: '1px solid var(--border-subtle)' }}>
              8 inférences
            </span>
          </div>

          <div className="rounded-xl p-3" style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}>
            <Sparkline data={history} color={ic} />
            {/* X labels */}
            <div className="flex justify-between mt-1 px-0.5">
              {history.map((h, i) => (
                <span key={i} className="text-[8px] text-[var(--text-faint)]">{h.label}</span>
              ))}
            </div>
          </div>

          {/* Trend summary */}
          <div className="flex items-center gap-2 mt-2">
            {trendDir < -0.05
              ? <TrendingDown size={12} className="text-red-500" />
              : trendDir > 0.05
              ? <TrendingUp size={12} className="text-emerald-500" />
              : <Minus size={12} className="text-[var(--text-faint)]" />}
            <span className="text-[11px] text-[var(--text-muted)]">
              {trendDir < -0.05
                ? `Tendance dégradante (${trendDir > 0 ? '+' : ''}${(trendDir * 100).toFixed(0)} pts sur 8 semaines)`
                : trendDir > 0.05
                ? `Tendance améliorante (+${(trendDir * 100).toFixed(0)} pts sur 8 semaines)`
                : 'Signal stable sur les 8 dernières semaines'}
            </span>
          </div>
        </section>

        <div className="h-px" style={{ background: 'var(--border-subtle)' }} />

        {/* ③ Recommended action */}
        <section>
          <div className="flex items-center gap-1.5 mb-2.5">
            <Lightbulb size={12} className="text-amber-500" />
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
              Recommandation stratégique
            </p>
          </div>

          <div className="rounded-xl p-3.5 space-y-2.5"
            style={{ background: reco.urgencyColor + '0C', border: `1px solid ${reco.urgencyColor}30` }}>
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: reco.urgencyColor + '18', color: reco.urgencyColor }}>
                <Lightbulb size={12} />
              </div>
              <div className="flex-1">
                <p className="text-xs font-black" style={{ color: reco.urgencyColor }}>{reco.title}</p>
                <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full mt-0.5 inline-block"
                  style={{ background: reco.urgencyColor + '18', color: reco.urgencyColor }}>
                  <Clock size={8} className="inline mr-0.5" />
                  {reco.urgency}
                </span>
              </div>
            </div>
            <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
              {reco.action}
            </p>
          </div>
        </section>

        {/* ④ Raw metrics footer */}
        <div className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center"
          style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}>
          {[
            { label: 'Impact TGAT', value: `${entity.predicted_impact >= 0 ? '+' : ''}${entity.predicted_impact.toFixed(3)}`, color: ic },
            { label: 'Confiance', value: `${Math.round(entity.confidence * 100)}%`, color: 'var(--text-secondary)' },
            { label: 'Propagation', value: `${entity.propagation_hops} saut${entity.propagation_hops > 1 ? 's' : ''}`, color: 'var(--text-secondary)' },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <p className="text-[9px] text-[var(--text-faint)] uppercase tracking-wide mb-0.5">{label}</p>
              <p className="text-sm font-black font-mono" style={{ color }}>{value}</p>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────
interface Props {
  result: GNNResult | undefined;
  loading: boolean;
  onRunGNN: () => void;
  running: boolean;
}

type SortKey = 'predicted_impact' | 'confidence' | 'propagation_hops';
type SortDir = 'asc' | 'desc';

// ══════════════════════════════════════════════════════════════════════════════
// §A  SVG sub-components (no hooks)
// ══════════════════════════════════════════════════════════════════════════════

function RadialGauge({ value, color }: { value: number; color: string }) {
  const norm  = (value + 1) / 2;
  const r = 52; const cx = 70; const cy = 72;
  const arc   = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  const angle = norm * 180 - 90;
  const nx    = cx + (r - 12) * Math.cos(((angle - 90) * Math.PI) / 180);
  const ny    = cy + (r - 12) * Math.sin(((angle - 90) * Math.PI) / 180);
  return (
    <svg width={140} height={90} viewBox="0 0 140 90">
      <path d={arc} fill="none" stroke="rgba(148,163,184,0.15)" strokeWidth={10} strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx} ${cy - r}`}
        fill="none" stroke="rgba(239,68,68,0.18)" strokeWidth={10} strokeLinecap="round" />
      <path d={`M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="rgba(16,185,129,0.18)" strokeWidth={10} strokeLinecap="round" />
      <motion.path d={arc} fill="none" stroke={color} strokeWidth={10} strokeLinecap="round"
        strokeDasharray={`${r * Math.PI}`}
        initial={{ strokeDashoffset: r * Math.PI }}
        animate={{ strokeDashoffset: r * Math.PI * (1 - norm) }}
        transition={{ duration: 0.9, ease: 'easeOut' }} />
      <motion.line x1={cx} y1={cy} x2={nx} y2={ny}
        stroke={color} strokeWidth={2.5} strokeLinecap="round"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} />
      <circle cx={cx} cy={cy} r={5} fill={color} />
      <text x={cx} y={cy - 16} textAnchor="middle" fontSize="16" fontWeight="800" fill={color}>
        {value >= 0 ? '+' : ''}{value.toFixed(3)}
      </text>
      <text x={cx - r + 2} y={cy + 14} fontSize="9" fill="#94A3B8">-1</text>
      <text x={cx + r - 8} y={cy + 14} fontSize="9" fill="#94A3B8">+1</text>
    </svg>
  );
}

function RiskRing({ value }: { value: number }) {
  const color = riskColor(value);
  const label = riskLabel(value);
  const r = 36; const circ = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative w-24 h-24 flex items-center justify-center">
        <svg className="absolute inset-0" width={96} height={96} viewBox="0 0 96 96">
          <circle cx={48} cy={48} r={r} fill="none" stroke="rgba(148,163,184,0.14)" strokeWidth={8} />
          <motion.circle cx={48} cy={48} r={r} fill="none" stroke={color} strokeWidth={8}
            strokeLinecap="round" strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ * (1 - value) }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
            style={{ transformOrigin: '50% 50%', transform: 'rotate(-90deg)' }} />
        </svg>
        <p className="text-base font-black z-10" style={{ color }}>{Math.round(value * 100)}%</p>
      </div>
      <p className="text-[10px] font-bold tracking-wide" style={{ color }}>{label}</p>
      <p className="text-[9px] text-[var(--text-faint)]">Risque systémique</p>
    </div>
  );
}

function BarTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d: GNNPrediction = payload[0].payload;
  const c = impactColor(d.predicted_impact);
  return (
    <div className="rounded-2xl p-3 text-xs shadow-2xl min-w-[160px]"
      style={{ background: 'rgba(255,255,255,0.97)', border: '1px solid var(--border-subtle)' }}>
      <p className="font-bold text-[var(--text-primary)] mb-1.5">{d.entity_name}</p>
      <div className="space-y-0.5">
        {[
          ['Impact',    `${d.predicted_impact >= 0 ? '+' : ''}${d.predicted_impact.toFixed(3)}`, c],
          ['Confiance', `${Math.round(d.confidence * 100)}%`, undefined],
          ['Sauts',     String(d.propagation_hops), undefined],
          ['Type',      d.entity_type, undefined],
        ].map(([k, v, col]) => (
          <div key={k as string} className="flex justify-between gap-4">
            <span className="text-[var(--text-muted)]">{k}</span>
            <span className="font-mono font-semibold" style={col ? { color: col as string } : {}}>{v}</span>
          </div>
        ))}
        {d.hidden_risk && (
          <p className="text-violet-600 font-semibold mt-1 pt-1 border-t border-violet-100">⚡ Risque caché</p>
        )}
      </div>
    </div>
  );
}

function ScatterTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d: GNNPrediction = payload[0].payload;
  return (
    <div className="rounded-xl p-2.5 text-xs shadow-xl"
      style={{ background: 'rgba(255,255,255,0.97)', border: '1px solid var(--border-subtle)' }}>
      <p className="font-bold text-[var(--text-primary)]">{d.entity_name}</p>
      <p className="text-[var(--text-muted)]">
        Impact: <span className="font-mono" style={{ color: impactColor(d.predicted_impact) }}>
          {d.predicted_impact >= 0 ? '+' : ''}{d.predicted_impact.toFixed(3)}
        </span>
      </p>
      <p className="text-[var(--text-muted)]">Conf: {Math.round(d.confidence * 100)}%</p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// §B  ResultPanel — all hooks here, no conditional returns
// ══════════════════════════════════════════════════════════════════════════════

function ResultPanel({ result, onRunGNN, running }: { result: GNNResult; onRunGNN: () => void; running: boolean }) {
  // All hooks must be declared unconditionally at the top
  const [filterType,     setFilterType]     = useState<string>('all');
  const [filterRisk,     setFilterRisk]     = useState<boolean>(false);
  const [filterTag,      setFilterTag]      = useState<string>('');
  const [sortKey,        setSortKey]        = useState<SortKey>('predicted_impact');
  const [sortDir,        setSortDir]        = useState<SortDir>('asc');
  const [view,           setView]           = useState<'chemins' | 'chart' | 'scatter' | 'table'>('chemins');
  const [selectedEntity, setSelectedEntity] = useState<GNNPrediction | null>(null);
  const [showMetrics,    setShowMetrics]    = useState<boolean>(false);

  const filteredPreds = useMemo(() => {
    let list = result.predictions;
    if (filterType !== 'all') list = list.filter((p) => p.entity_type === filterType);
    if (filterRisk)           list = list.filter((p) => p.hidden_risk);
    if (filterTag === 'threats')     list = list.filter((p) => p.predicted_impact < -0.3);
    if (filterTag === 'opportunities') list = list.filter((p) => p.predicted_impact > 0.3);
    if (filterTag === 'strong')      list = list.filter((p) => Math.abs(p.predicted_impact) > 0.5);
    if (filterTag === 'talan')       list = list.filter((p) => p.propagation_hops === 1);
    return [...list].sort((a, b) => {
      const diff = a[sortKey] < b[sortKey] ? -1 : a[sortKey] > b[sortKey] ? 1 : 0;
      return sortDir === 'asc' ? diff : -diff;
    });
  }, [result.predictions, filterType, filterRisk, filterTag, sortKey, sortDir]);

  // Derived (no hooks)
  const talanImpact = result.talan_prediction?.predicted_impact ?? 0;
  const talanConf   = result.talan_prediction?.confidence ?? 0;
  const talanColor  = impactColor(talanImpact);
  const entityTypes = ['all', ...Array.from(new Set(result.predictions.map((p) => p.entity_type)))];
  const chartData   = [...result.predictions]
    .sort((a, b) => Math.abs(b.predicted_impact) - Math.abs(a.predicted_impact))
    .slice(0, 18);
  const scatterData = result.predictions.map((p) => ({
    ...p, x: p.predicted_impact, y: p.confidence, z: p.hidden_risk ? 120 : 60,
  }));
  const posCount = result.predictions.filter((p) => p.predicted_impact > 0.1).length;
  const negCount = result.predictions.filter((p) => p.predicted_impact < -0.1).length;
  const hidCount = result.top_hidden_risks.length;

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k
      ? (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)
      : <ChevronDown size={11} className="opacity-30" />;

  // ── Executive summary helpers ─────────────────────────────────────────────
  const topThreat = useMemo(() =>
    [...result.predictions]
      .filter((p) => p.predicted_impact < -0.1)
      .sort((a, b) => a.predicted_impact - b.predicted_impact)[0] ?? null,
    [result.predictions]
  );
  const topOpportunity = useMemo(() =>
    [...result.predictions]
      .filter((p) => p.predicted_impact > 0.1)
      .sort((a, b) => b.predicted_impact - a.predicted_impact)[0] ?? null,
    [result.predictions]
  );
  const execAction = useMemo(() => {
    if (!topThreat) return "Surveiller l'évolution du graphe de connaissance.";
    const abs = Math.abs(topThreat.predicted_impact);
    if (abs >= 0.55) return `Action immédiate (48h) : analyser l'exposition de Talan à ${topThreat.entity_name}.`;
    if (abs >= 0.3)  return `Cette semaine : préparer un plan de réponse sur ${topThreat.entity_name}.`;
    return `Dans 1 mois : surveiller ${topThreat.entity_name} — risque modéré.`;
  }, [topThreat]);

  return (
    <div className="space-y-5">

      {/* ── §0  EXECUTIVE SUMMARY ─────────────────────────────────────────────── */}
      <div className="rounded-2xl p-4 flex flex-col gap-3"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
        <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
          Résumé exécutif
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Impact Talan */}
          <div className="flex flex-col gap-1 rounded-xl p-3"
            style={{ background: talanImpact < -0.05 ? '#FEF2F2' : talanImpact > 0.05 ? '#ECFDF5' : 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">Impact Talan</p>
            <p className="text-base font-black" style={{ color: talanColor }}>
              {talanImpact >= 0 ? '+' : ''}{talanImpact.toFixed(2)}
            </p>
            <p className="text-[10px] text-[var(--text-muted)]">
              {talanImpact < -0.3 ? 'Exposition significative' : talanImpact > 0.3 ? 'Opportunité détectée' : 'Impact modéré'}
            </p>
          </div>
          {/* Risque principal */}
          <div className="flex flex-col gap-1 rounded-xl p-3"
            style={{ background: '#FEF2F2', border: '1px solid #FECACA' }}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">Risque principal</p>
            {topThreat ? (
              <>
                <p className="text-xs font-bold text-red-700 truncate" title={topThreat.entity_name}>{topThreat.entity_name}</p>
                <p className="text-[10px] text-red-500 font-mono font-bold">{topThreat.predicted_impact.toFixed(2)}</p>
              </>
            ) : (
              <p className="text-xs text-[var(--text-muted)]">Aucun risque significatif</p>
            )}
          </div>
          {/* Opportunité principale */}
          <div className="flex flex-col gap-1 rounded-xl p-3"
            style={{ background: '#ECFDF5', border: '1px solid #A7F3D0' }}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">Opportunité</p>
            {topOpportunity ? (
              <>
                <p className="text-xs font-bold text-emerald-700 truncate" title={topOpportunity.entity_name}>{topOpportunity.entity_name}</p>
                <p className="text-[10px] text-emerald-500 font-mono font-bold">+{topOpportunity.predicted_impact.toFixed(2)}</p>
              </>
            ) : (
              <p className="text-xs text-[var(--text-muted)]">Aucune opportunité détectée</p>
            )}
          </div>
          {/* Action recommandée */}
          <div className="flex flex-col gap-1 rounded-xl p-3"
            style={{ background: '#FFFBEB', border: '1px solid #FDE68A' }}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">Action recommandée</p>
            <p className="text-[11px] text-amber-800 leading-snug">{execAction}</p>
          </div>
        </div>
      </div>

      {/* ── §1  KPI ROW ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

        {/* Talan gauge */}
        <div className="rounded-2xl p-4 flex flex-col items-center gap-1"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] self-start">
            Impact Talan
          </p>
          <RadialGauge value={talanImpact} color={talanColor} />
          <div className="flex items-center gap-1.5 mt-0.5">
            {talanImpact < -0.05
              ? <TrendingDown size={12} className="text-red-500" />
              : talanImpact > 0.05
              ? <TrendingUp size={12} className="text-emerald-500" />
              : <Minus size={12} className="text-[var(--text-faint)]" />}
            <span className="text-xs text-[var(--text-muted)]">
              Confiance&nbsp;{Math.round(talanConf * 100)}%
            </span>
          </div>
        </div>

        {/* Systemic risk */}
        <div className="rounded-2xl p-4 flex flex-col items-center justify-center"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
          <RiskRing value={result.systemic_risk_score} />
        </div>

        {/* Distribution */}
        <div className="rounded-2xl p-4 flex flex-col gap-2"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Distribution
          </p>
          <div className="space-y-2 mt-1">
            {([
              { label: 'Impact positif', count: posCount, color: '#10B981', bg: '#ECFDF5' },
              { label: 'Impact négatif', count: negCount, color: '#EF4444', bg: '#FEF2F2' },
              { label: 'Risques cachés', count: hidCount, color: '#7C3AED', bg: '#F5F3FF' },
            ] as const).map(({ label, count, color, bg }) => (
              <div key={label} className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                  <span className="text-xs text-[var(--text-muted)]">{label}</span>
                </div>
                <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                  style={{ background: bg, color }}>{count}</span>
              </div>
            ))}
          </div>
          <div className="mt-auto flex items-center gap-1 text-[10px] text-[var(--text-faint)]">
            <Clock size={10} />
            {new Date(result.run_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>

        {/* TGAT model card */}
        <div className="rounded-2xl p-4 flex flex-col gap-3"
          style={{ background: 'var(--primary-subtle)', border: '1px solid var(--primary-muted)' }}>
          <div className="flex items-center gap-2 flex-wrap">
            <Brain size={14} className="text-[var(--primary)]" />
            <p className="text-sm font-bold text-[var(--primary-dark)]">TGAT</p>
            {/* Inference mode badge */}
            {(() => {
              const mode = result.inference_mode ?? 'tgat_trained';
              const cfg =
                mode === 'tgat_trained'  ? { label: 'Entraîné',          bg: '#DCFCE7', color: '#166534' } :
                mode === 'tgat_random'   ? { label: 'Poids aléatoires',   bg: '#FEF9C3', color: '#854D0E' } :
                                           { label: 'Fallback heuristique', bg: '#FEE2E2', color: '#991B1B' };
              return (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold ml-auto"
                  style={{ background: cfg.bg, color: cfg.color }}>
                  {cfg.label}
                </span>
              );
            })()}
          </div>

          {/* Manager Trust Score on TGAT paths */}
          <TrustScoreBadge itemKind="path" verbose hideIfInsufficient={false} />

          {/* Collapsible AUC/F1 metrics */}
          <button onClick={() => setShowMetrics((v) => !v)}
            className="flex items-center gap-1 text-[10px] text-[var(--primary-dark)] font-semibold self-start">
            {showMetrics ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            Détails du modèle
          </button>
          <AnimatePresence>
            {showMetrics && (
              <motion.div
                initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                style={{ overflow: 'hidden' }}>
                <div className="grid grid-cols-2 gap-1.5">
                  {([
                    { label: 'AUC',  value: TGAT_METRICS.auc },
                    { label: 'AP',   value: TGAT_METRICS.ap  },
                    { label: 'F1',   value: TGAT_METRICS.f1  },
                    { label: 'Prec', value: TGAT_METRICS.precision },
                  ] as const).map(({ label, value }) => (
                    <div key={label} className="rounded-xl p-1.5 text-center"
                      style={{ background: 'rgba(255,255,255,0.6)' }}>
                      <p className="text-[9px] text-[var(--text-muted)] font-semibold uppercase tracking-wide">{label}</p>
                      <p className="text-sm font-black text-[var(--primary-dark)]">{value.toFixed(2)}</p>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Action button */}
          <button onClick={onRunGNN} disabled={running}
            className="flex items-center justify-center gap-1.5 py-1.5 rounded-full text-xs font-bold transition-all"
            style={{ background: running ? 'var(--border-subtle)' : 'var(--primary)', color: 'white' }}>
            {running
              ? <><span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />Calcul…</>
              : <><Zap size={11} />Lancer une simulation</>}
          </button>
        </div>
      </div>

      {/* ── §2  VISUALISATION ────────────────────────────────────────────────── */}
      <div className="rounded-2xl p-5"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>

        {/* Header + view toggle */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <p className="text-sm font-bold text-[var(--text-secondary)] flex-1">
            {view === 'chemins'
              ? (() => {
                  const n = result.propagation_paths?.length ?? DEMO_PATHS.length;
                  return `Chemins de propagation · ${n} chemin${n > 1 ? 's' : ''}`;
                })()
              : `Impact prédit · ${result.predictions.length} entités`}
          </p>
          <div className="flex rounded-xl overflow-hidden"
            style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-base)' }}>
            {(['chemins', 'chart', 'scatter', 'table'] as const).map((v, i, arr) => (
              <button key={v} onClick={() => setView(v)}
                className="px-3 py-1 text-[11px] font-semibold transition-all flex items-center gap-1"
                style={{
                  background: view === v ? 'var(--primary-subtle)' : 'transparent',
                  color: view === v ? 'var(--primary-dark)' : 'var(--text-muted)',
                  borderRight: i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                }}>
                {v === 'chemins'
                  ? <><GitBranch size={10} />Chemins</>
                  : v === 'chart' ? 'Barres'
                  : v === 'scatter' ? 'Nuage'
                  : 'Tableau'}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={view}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>

            {/* Propagation chains */}
            {view === 'chemins' && (
              <PropagationChainsPanel
                paths={result.propagation_paths ?? []}
                runAt={result.run_at}
              />
            )}

            {/* Bar chart */}
            {view === 'chart' && (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={chartData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }} barSize={13}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                    <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" strokeWidth={1.5} />
                    <XAxis dataKey="entity_name"
                      tick={{ fill: 'var(--chart-legend)', fontSize: 10 }}
                      axisLine={false} tickLine={false}
                      interval={0} angle={-35} textAnchor="end" height={52} />
                    <YAxis domain={[-1, 1]}
                      tick={{ fill: 'var(--chart-legend)', fontSize: 10 }}
                      axisLine={false} tickLine={false} />
                    <Tooltip content={<BarTooltip />} />
                    <Bar dataKey="predicted_impact" radius={[5, 5, 0, 0]}
                      cursor="pointer"
                      onClick={(data: any) => setSelectedEntity(data as GNNPrediction)}>
                      {chartData.map((entry, i) => (
                        <Cell key={i}
                          fill={entry.hidden_risk ? '#8B5CF6'
                            : entry.entity_name === 'Talan' ? '#2563EB'
                            : impactColor(entry.predicted_impact)}
                          opacity={selectedEntity?.entity_name === entry.entity_name ? 1 : entry.entity_name === 'Talan' ? 1 : 0.78} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="flex items-center gap-4 mt-3 justify-center flex-wrap">
                  {([
                    { color: '#2563EB', label: 'Talan' },
                    { color: '#10B981', label: 'Impact positif' },
                    { color: '#EF4444', label: 'Impact négatif' },
                    { color: '#F59E0B', label: 'Neutre' },
                    { color: '#8B5CF6', label: 'Risque caché' },
                  ] as const).map(({ color, label }) => (
                    <div key={label} className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
                      <span className="text-[11px] text-[var(--text-muted)]">{label}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Scatter: impact vs confidence */}
            {view === 'scatter' && (
              <>
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  X = impact prédit · Y = confiance · taille = risque caché
                </p>
                <ResponsiveContainer width="100%" height={260}>
                  <ScatterChart margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                    <ReferenceLine x={0} stroke="rgba(148,163,184,0.5)" strokeWidth={1.5} />
                    <XAxis type="number" dataKey="x" domain={[-1, 1]} name="Impact"
                      tick={{ fill: 'var(--chart-legend)', fontSize: 10 }}
                      axisLine={false} tickLine={false} />
                    <YAxis type="number" dataKey="y" domain={[0, 1]} name="Confiance"
                      tick={{ fill: 'var(--chart-legend)', fontSize: 10 }}
                      axisLine={false} tickLine={false} />
                    <ZAxis type="number" dataKey="z" range={[40, 180]} />
                    <Tooltip content={<ScatterTooltip />} />
                    <Scatter data={scatterData}
                      shape={(props: any) => {
                        const { cx, cy, r, payload } = props;
                        const c = payload.hidden_risk ? '#8B5CF6'
                          : payload.entity_name === 'Talan' ? '#2563EB'
                          : impactColor(payload.predicted_impact);
                        const isSelected = selectedEntity?.entity_name === payload.entity_name;
                        return (
                          <circle cx={cx} cy={cy} r={isSelected ? r + 2 : r}
                            fill={c} fillOpacity={isSelected ? 1 : 0.75}
                            stroke={isSelected ? 'white' : c} strokeWidth={isSelected ? 2 : 1}
                            style={{ cursor: 'pointer' }}
                            onClick={() => setSelectedEntity(payload)} />
                        );
                      }} />
                  </ScatterChart>
                </ResponsiveContainer>
              </>
            )}

            {/* Sortable / filterable table */}
            {view === 'table' && (
              <>
                {/* Filters row 1 — entity type */}
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <Filter size={12} className="text-[var(--text-faint)]" />
                  <div className="flex gap-1 flex-wrap">
                    {entityTypes.map((t) => (
                      <button key={t} onClick={() => setFilterType(t)}
                        className="px-2.5 py-0.5 rounded-full text-[11px] font-medium transition-all capitalize"
                        style={{
                          background: filterType === t ? 'var(--primary-subtle)' : 'var(--bg-base)',
                          color: filterType === t ? 'var(--primary-dark)' : 'var(--text-muted)',
                          border: `1px solid ${filterType === t ? 'var(--primary-muted)' : 'var(--border-subtle)'}`,
                        }}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                {/* Filters row 2 — semantic quick filters */}
                <div className="flex items-center gap-1.5 mb-3 flex-wrap">
                  {([
                    { tag: 'threats',       label: 'Menaces',             bg: '#FEE2E2', color: '#991B1B', activeBorder: '#FECACA' },
                    { tag: 'opportunities', label: 'Opportunités',        bg: '#ECFDF5', color: '#166534', activeBorder: '#A7F3D0' },
                    { tag: 'strong',        label: 'Impact fort (>0.5)',  bg: '#FFF7ED', color: '#9A3412', activeBorder: '#FED7AA' },
                    { tag: 'talan',         label: 'Liés à Talan (1 saut)',bg: '#EFF6FF', color: '#1E40AF', activeBorder: '#BFDBFE' },
                  ] as const).map(({ tag, label, bg, color, activeBorder }) => (
                    <button key={tag}
                      onClick={() => setFilterTag((v) => v === tag ? '' : tag)}
                      className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium transition-all"
                      style={{
                        background: filterTag === tag ? bg : 'var(--bg-base)',
                        color: filterTag === tag ? color : 'var(--text-muted)',
                        border: `1px solid ${filterTag === tag ? activeBorder : 'var(--border-subtle)'}`,
                      }}>
                      {label}
                    </button>
                  ))}
                  <button onClick={() => setFilterRisk((v) => !v)}
                    className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium ml-auto transition-all"
                    style={{
                      background: filterRisk ? '#F5F3FF' : 'var(--bg-base)',
                      color: filterRisk ? '#7C3AED' : 'var(--text-muted)',
                      border: `1px solid ${filterRisk ? '#DDD6FE' : 'var(--border-subtle)'}`,
                    }}>
                    <ShieldAlert size={10} />
                    Risques cachés
                  </button>
                </div>

                <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--border-subtle)' }}>
                  <table className="w-full text-xs">
                    <thead>
                      <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-subtle)' }}>
                        <th className="text-left px-3 py-2.5 text-[var(--text-muted)] font-semibold">Entité</th>
                        <th className="text-left px-3 py-2.5 text-[var(--text-muted)] font-semibold">Type</th>
                        {(['predicted_impact', 'confidence', 'propagation_hops'] as const).map((k) => (
                          <th key={k} onClick={() => handleSort(k)}
                            className="text-right px-3 py-2.5 text-[var(--text-muted)] font-semibold cursor-pointer select-none whitespace-nowrap">
                            <span className="flex items-center justify-end gap-1">
                              {k === 'predicted_impact' ? 'Impact' : k === 'confidence' ? 'Conf.' : 'Sauts'}
                              <SortIcon k={k} />
                            </span>
                          </th>
                        ))}
                        <th className="px-3 py-2.5" />
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPreds.map((p, i) => (
                        <motion.tr key={p.entity_name}
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.02 }}
                          className="border-b last:border-0 cursor-pointer"
                          onClick={() => setSelectedEntity(p)}
                          style={{
                            borderColor: 'var(--border-subtle)',
                            background: selectedEntity?.entity_name === p.entity_name
                              ? 'rgba(37,99,235,0.08)'
                              : p.entity_name === 'Talan'
                              ? 'rgba(37,99,235,0.04)'
                              : i % 2 === 0 ? 'var(--bg-surface)' : 'transparent',
                          }}>
                          <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">
                            {p.entity_name === 'Talan' && (
                              <span className="mr-1.5 text-[9px] px-1.5 py-0.5 rounded-full font-bold"
                                style={{ background: '#EFF6FF', color: '#2563EB' }}>★</span>
                            )}
                            {p.entity_name}
                          </td>
                          <td className="px-3 py-2 text-[var(--text-muted)] capitalize">{p.entity_type}</td>
                          <td className="px-3 py-2 text-right font-mono font-bold"
                            style={{ color: impactColor(p.predicted_impact) }}>
                            {p.predicted_impact >= 0 ? '+' : ''}{p.predicted_impact.toFixed(3)}
                          </td>
                          <td className="px-3 py-2 text-right text-[var(--text-muted)]">
                            {Math.round(p.confidence * 100)}%
                          </td>
                          <td className="px-3 py-2 text-right text-[var(--text-muted)]">
                            {p.propagation_hops}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {p.hidden_risk && (
                              <span
                                title={`Non directement relié à Talan — propagé en ${p.propagation_hops} sauts (|impact| > 0.3 et hops > 1)`}
                                className="text-[9px] px-1.5 py-0.5 rounded-full font-bold cursor-help"
                                style={{ background: '#F5F3FF', color: '#7C3AED' }}>
                                ⚡ caché · {p.propagation_hops}↗
                              </span>
                            )}
                          </td>
                        </motion.tr>
                      ))}
                      {filteredPreds.length === 0 && (
                        <tr>
                          <td colSpan={6} className="text-center py-8 text-[var(--text-faint)] text-xs">
                            Aucune entité pour ce filtre
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="text-[10px] text-[var(--text-faint)] mt-2 text-right">
                  {filteredPreds.length} / {result.predictions.length} entités
                </p>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── §3  HIDDEN RISKS SUMMARY (links to Chemins view) ────────────────── */}
      {result.top_hidden_risks.length > 0 && (
        <div className="rounded-2xl p-4" style={{ background: '#F5F3FF', border: '1px solid #DDD6FE' }}>
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={14} className="text-violet-600" />
            <p className="text-sm font-bold text-violet-700">
              {result.top_hidden_risks.length} risque{result.top_hidden_risks.length > 1 ? 's' : ''} caché{result.top_hidden_risks.length > 1 ? 's' : ''} détecté{result.top_hidden_risks.length > 1 ? 's' : ''}
            </p>
            <button
              onClick={() => setView('chemins')}
              className="ml-auto flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold transition-all"
              style={{ background: '#7C3AED', color: 'white' }}>
              <GitBranch size={10} />
              Voir les chemins
            </button>
          </div>
          <div className="flex gap-2 flex-wrap">
            {result.top_hidden_risks.map((pred, i) => {
              const c = pred.predicted_impact < -0.4 ? '#DC2626' : pred.predicted_impact < 0 ? '#EA580C' : '#059669';
              return (
                <motion.div key={i}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs"
                  style={{ background: 'rgba(255,255,255,0.8)', border: '1px solid #EDE9FE' }}>
                  <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full"
                    style={{ background: '#EDE9FE', color: '#5B21B6' }}>
                    {pred.propagation_hops}↑
                  </span>
                  <span className="font-semibold text-[var(--text-primary)]">{pred.entity_name}</span>
                  <span className="font-mono font-bold" style={{ color: c }}>
                    {pred.predicted_impact >= 0 ? '+' : ''}{pred.predicted_impact.toFixed(2)}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── §4  METHODOLOGY NOTE ──────────────────────────────────────────────── */}
      <div className="rounded-2xl p-4 flex gap-3"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
        <Brain size={14} className="text-[var(--primary)] mt-0.5 flex-shrink-0" />
        <div className="text-[11px] text-[var(--text-muted)] leading-relaxed space-y-1.5">
          <p>
            <span className="font-bold text-[var(--text-secondary)]">TGAT</span>
            {' '}— encodage temporel <span className="font-mono">Time2Vec</span> +
            2 couches d'attention causale (<span className="font-mono">TSAT</span>).
            Score sigmoïde sur liens IMPACTS, agrégé par entité cible.
            Test 2024 :{' '}
            <span className="font-semibold text-[var(--text-secondary)]">
              AUC {TGAT_METRICS.auc} · F1 {TGAT_METRICS.f1} · Recall {TGAT_METRICS.recall}
            </span>.
          </p>
          <p>
            <span className="font-semibold text-[var(--text-secondary)]">⚡ Risque caché</span>
            {' '}= entité non directement reliée à Talan (propagation ≥ 2 sauts) avec |impact| &gt; 0.3.
            Ces risques n'apparaissent pas dans l'analyse directe mais peuvent affecter Talan
            via des chaînes causales indirectes — survolez le badge pour voir le détail.
          </p>
          <p className="text-[var(--text-faint)]">
            Cliquer sur une barre, un point ou une ligne de propagation pour ouvrir l'analyse détaillée.
          </p>
        </div>
      </div>

      {/* ── §5  ENTITY DRILL-DOWN DRAWER ─────────────────────────────────────── */}
      <AnimatePresence>
        {selectedEntity && (
          <>
            {/* Backdrop */}
            <motion.div
              className="fixed inset-0 z-40"
              style={{ background: 'rgba(0,0,0,0.18)', backdropFilter: 'blur(2px)' }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedEntity(null)}
            />
            {/* Slide-in panel */}
            <motion.div
              className="fixed top-0 right-0 h-full z-50 overflow-hidden flex flex-col"
              style={{
                width: 420,
                background: 'var(--bg-surface)',
                borderLeft: '1px solid var(--border-subtle)',
                boxShadow: '-8px 0 40px rgba(0,0,0,0.12)',
              }}
              initial={{ x: 440 }}
              animate={{ x: 0 }}
              exit={{ x: 440 }}
              transition={{ type: 'spring', damping: 30, stiffness: 320 }}
            >
              <EntityDrillDown
                entity={selectedEntity}
                result={result}
                onClose={() => setSelectedEntity(null)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// §C  Shell — no hooks, dispatches to Loading / Empty / ResultPanel
// ══════════════════════════════════════════════════════════════════════════════

export default function GNNPredictions({ result, loading, onRunGNN, running }: Props) {
  if (loading || running) {
    return (
      <div className="flex flex-col items-center justify-center h-72 gap-4">
        <motion.div animate={{ scale: [1, 1.08, 1] }} transition={{ repeat: Infinity, duration: 1.4 }}
          className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{ background: 'var(--primary-subtle)' }}>
          <Brain size={28} className="text-[var(--primary)]" />
        </motion.div>
        <div className="text-center">
          <p className="text-[var(--text-secondary)] text-sm font-semibold">Inférence TGAT en cours…</p>
          <p className="text-[var(--text-faint)] text-xs mt-1">Time2Vec + Temporal Self-Attention</p>
        </div>
        <div className="flex gap-2 mt-1">
          {['Snapshot KG', 'Time2Vec', 'TSAT ×2', 'Score'].map((step, i) => (
            <motion.span key={step}
              initial={{ opacity: 0.2 }}
              animate={{ opacity: [0.2, 1, 0.2] }}
              transition={{ repeat: Infinity, duration: 1.6, delay: i * 0.3 }}
              className="text-[10px] px-2 py-0.5 rounded-full font-medium"
              style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)' }}>
              {step}
            </motion.span>
          ))}
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-5">
        <div className="w-20 h-20 rounded-3xl flex items-center justify-center"
          style={{ background: 'var(--primary-subtle)', border: '1px solid var(--primary-muted)' }}>
          <Brain size={36} className="text-[var(--primary)] opacity-50" />
        </div>
        <div className="text-center max-w-xs">
          <p className="text-[var(--text-primary)] text-base font-bold mb-1">Aucune prédiction disponible</p>
          <p className="text-[var(--text-muted)] text-sm">
            Lancez l'inférence pour analyser la propagation des impacts dans le Knowledge Graph.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-[var(--text-faint)] flex-wrap justify-center">
          {['KG Snapshot', '→', 'Time2Vec', '→', 'TSAT L1', '→', 'TSAT L2', '→', 'Score'].map((s) => (
            <span key={s} className={s === '→' ? '' : 'px-2 py-0.5 rounded-full'}
              style={s !== '→' ? { background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' } : {}}>
              {s}
            </span>
          ))}
        </div>
        <button onClick={onRunGNN}
          className="flex items-center gap-2 px-6 py-2.5 rounded-full text-sm font-bold shadow-sm"
          style={{ background: 'var(--primary)', color: 'white' }}>
          <Zap size={14} />
          Lancer l'inférence TGAT
        </button>
      </div>
    );
  }

  return <ResultPanel result={result} onRunGNN={onRunGNN} running={running} />;
}

/**
 * StaticGNNInsight — Analyse GNN statique pour une actualité majeure.
 * News: Accord UE-Tunisie sur la transformation digitale du secteur public.
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, Radar,
  LineChart, Line, ReferenceLine,
} from 'recharts';
import {
  Newspaper, Brain, TrendingDown, TrendingUp, AlertTriangle,
  Eye, Zap, Globe2, Building2, BarChart2, ChevronDown, ChevronUp,
  ShieldAlert, Lightbulb, Activity,
} from 'lucide-react';

// ── Static data ───────────────────────────────────────────────────────────────

const NEWS = {
  id: 'NEWS-2026-041',
  title: "La Tunisie signe un accord stratégique avec l'UE pour la transformation digitale du secteur public — 480 M€ alloués",
  source: 'Reuters Afrique / Agence TAP',
  date: '14 Avril 2026 · 09:42',
  category: 'Politique & Tech',
  importance: 'CRITIQUE',
  summary: `L'Union Européenne et la Tunisie ont signé ce matin un accord-cadre de coopération numérique d'une durée de 5 ans, portant sur la modernisation des administrations publiques, la cybersécurité nationale et le déploiement de l'e-gouvernement. Une enveloppe de 480 millions d'euros sera mobilisée, dont 60 % en subventions directes. Les appels d'offres pour les ESN (Entreprises de Services du Numérique) locales seront ouverts dès le T3 2026. Le ministère des Technologies de Communication a confirmé que des partenariats prioritaires seront établis avec les acteurs tunisiens certifiés ISO 27001.`,
};

const CONSEQUENCES = [
  {
    icon: '📈',
    type: 'positive',
    title: 'Boom des contrats IT publics',
    detail: "Les marchés publics IT devraient croître de 35–45 % sur 2026–2028. Les ESN tunisiennes certifiées seront favorisées dans les appels d'offres.",
  },
  {
    icon: '💶',
    type: 'positive',
    title: 'Afflux de capitaux étrangers',
    detail: "480 M€ injectés dans l'écosystème digital tunisien. Effet multiplicateur estimé à 2.3× sur les dépenses IT privées connexes.",
  },
  {
    icon: '⚔️',
    type: 'neutral',
    title: 'Intensification de la concurrence',
    detail: "Les cabinets européens (Capgemini, Sopra Steria) vont s'implanter localement pour capter une part du marché. Pression sur les marges.",
  },
  {
    icon: '🔒',
    type: 'neutral',
    title: 'Exigences de conformité renforcées',
    detail: 'Les contrats UE imposent RGPD, NIS2 et certification ISO 27001. Les ESN non certifiées seront exclues des consortiums.',
  },
  {
    icon: '⚠️',
    type: 'negative',
    title: 'Tension sur les ressources humaines',
    detail: "Forte demande d'experts IT sur un marché déjà sous tension. Risque de débauchage par les nouvelles entités étrangères (+20–30 % sur les salaires senior).",
  },
  {
    icon: '🏛️',
    type: 'negative',
    title: 'Dépendance technologique accrue',
    detail: "Les architectures imposées par l'UE (cloud souverain européen, standards ENISA) créent une dépendance aux fournisseurs européens.",
  },
];

const HIDDEN_PATTERNS = [
  {
    rank: 1,
    label: 'Cluster Banques Publiques → IT',
    confidence: 0.91,
    hops: 3,
    description: "La BCT et les banques publiques (STB, BH Bank) vont accélérer leurs projets de transformation numérique dans le sillage de l'accord. Signal détecté via co-occurrence dans les communiqués officiels (72 occurrences en 30 jours).",
    impact: +0.74,
  },
  {
    rank: 2,
    label: 'Pression salariale cascade',
    confidence: 0.87,
    hops: 2,
    description: "Les offres d'emploi des ESN ont augmenté de 38 % en 14 jours post-annonce. Le GNN détecte une propagation vers le marché RH IT dans un délai de 45–90 jours.",
    impact: -0.52,
  },
  {
    rank: 3,
    label: 'Signal de consolidation sectorielle',
    confidence: 0.79,
    hops: 4,
    description: 'Corrélation historique (r=0.83) entre deals UE similaires et vagues de fusions-acquisitions dans les ESN locales dans les 18 mois suivants. 3 ESN tunisiennes identifiées comme cibles probables.',
    impact: -0.31,
  },
  {
    rank: 4,
    label: 'Opportunité Cloud souverain',
    confidence: 0.76,
    hops: 2,
    description: "L'accord mandate un cloud souverain hybride. Le GNN détecte que seules 4 ESN tunisiennes ont les accréditations nécessaires — Talan étant parmi elles.",
    impact: +0.68,
  },
];

const GNN_PREDICTIONS = [
  { name: 'Talan',        impact: +0.71, confidence: 0.89, hidden: false },
  { name: 'Vermeg',       impact: +0.58, confidence: 0.84, hidden: false },
  { name: 'Telnet',       impact: +0.51, confidence: 0.81, hidden: false },
  { name: 'BIAT',         impact: +0.44, confidence: 0.77, hidden: false },
  { name: 'STB',          impact: +0.39, confidence: 0.74, hidden: true  },
  { name: 'Ooredoo TN',   impact: +0.28, confidence: 0.69, hidden: false },
  { name: 'BH Bank',      impact: +0.22, confidence: 0.65, hidden: true  },
  { name: 'Capgemini TN', impact: -0.18, confidence: 0.71, hidden: false },
  { name: 'Sopra Steria', impact: -0.34, confidence: 0.78, hidden: true  },
  { name: 'iGTech',       impact: -0.12, confidence: 0.61, hidden: false },
];

const BOURSE_DATA = [
  { day: 'J-5', talan: 24.2, index: 7820 },
  { day: 'J-4', talan: 24.5, index: 7845 },
  { day: 'J-3', talan: 24.1, index: 7810 },
  { day: 'J-2', talan: 24.8, index: 7890 },
  { day: 'J-1', talan: 25.1, index: 7930 },
  { day: 'Annonce', talan: 27.4, index: 8120 },
  { day: 'J+1', talan: 28.9, index: 8210 },
  { day: 'J+2', talan: 28.2, index: 8175 },
];

const RADAR_DATA = [
  { subject: 'Marchés publics', Talan: 88, Secteur: 62 },
  { subject: 'Cloud & Infra',   Talan: 75, Secteur: 55 },
  { subject: 'Cybersécurité',   Talan: 82, Secteur: 48 },
  { subject: 'Data & IA',       Talan: 79, Secteur: 58 },
  { subject: 'Conformité',      Talan: 85, Secteur: 52 },
  { subject: 'Talent',          Talan: 60, Secteur: 65 },
];

const MARKET_EFFECTS = [
  {
    icon: <BarChart2 size={16} />,
    color: '#10b981',
    label: 'Effet sur la Bourse (BVMT)',
    badge: '+3.8 %',
    badgeColor: '#10b981',
    points: [
      "Indice BVMT +3.8 % le jour de l'annonce — meilleure session depuis 8 mois",
      "Secteur IT : +6.2 % — surperformance vs marché général",
      "Talan Group : +12.7 % sur la séance (cours : 28,9 DT)",
      "Volume d'échanges × 4.1 vs moyenne 30 jours sur les valeurs tech",
      "Prévision GNN : consolidation à +7–9 % vs cours pré-annonce à horizon 60 jours",
    ],
  },
  {
    icon: <Globe2 size={16} />,
    color: '#3b82f6',
    label: 'Effet sur le marché IT tunisien',
    badge: '+ 480 M€',
    badgeColor: '#3b82f6',
    points: [
      "Création estimée de 3 200 emplois IT qualifiés sur 5 ans",
      "Taux de croissance du marché IT local : 8 % → 14 % annuels",
      "Émergence d'un segment GovTech structuré — nouveau vertical de 90–120 M€/an",
      "Accélération de la certification ISO 27001 parmi les ESN (+45 dossiers en cours)",
      "Risque : arrivée de 6–8 ESN européennes dans les 12 mois — pression concurrentielle",
    ],
  },
  {
    icon: <Building2 size={16} />,
    color: '#7c3aed',
    label: 'Effet sur Talan',
    badge: 'Score GNN +0.71',
    badgeColor: '#7c3aed',
    points: [
      "3 appels d'offres pré-identifiés par le GNN : ANSI (10 M€), Douane (7 M€), Santé (15 M€)",
      "La certification ISO 27001 de Talan la place dans le top 4 éligible aux contrats UE",
      "Opportunité de créer une offre Cloud Souverain packagée — EBITDA marginal estimé : +2.5 pts",
      "Risque RH critique : débauchage potentiel de 8–12 profils seniors (Data Eng, SecOps)",
      "Recommandation GNN : lancer un plan de rétention immédiat et accélérer les recrutements junior",
    ],
  },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ icon, title, badge, badgeColor }: { icon: React.ReactNode; title: string; badge?: string; badgeColor?: string }) {
  return (
    <div className="flex items-center gap-2.5 mb-4">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'var(--primary-subtle)', color: 'var(--primary)' }}>
        {icon}
      </div>
      <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>{title}</h3>
      {badge && (
        <span className="ml-auto text-xs font-bold px-2.5 py-1 rounded-full"
          style={{ background: `${badgeColor}18`, color: badgeColor, border: `1px solid ${badgeColor}30` }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function ConsequenceCard({ c, i }: { c: typeof CONSEQUENCES[0]; i: number }) {
  const bg = c.type === 'positive' ? '#f0fdf4' : c.type === 'negative' ? '#fef2f2' : '#fffbeb';
  const border = c.type === 'positive' ? '#bbf7d0' : c.type === 'negative' ? '#fecaca' : '#fde68a';
  const textColor = c.type === 'positive' ? '#166534' : c.type === 'negative' ? '#991b1b' : '#78350f';
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.06 }}
      className="p-4 rounded-2xl"
      style={{ background: bg, border: `1px solid ${border}` }}
    >
      <div className="flex items-start gap-2.5">
        <span className="text-xl leading-none mt-0.5">{c.icon}</span>
        <div>
          <p className="text-sm font-bold mb-1" style={{ color: textColor }}>{c.title}</p>
          <p className="text-xs leading-relaxed" style={{ color: textColor, opacity: 0.85 }}>{c.detail}</p>
        </div>
      </div>
    </motion.div>
  );
}

function HiddenPatternRow({ p, i }: { p: typeof HIDDEN_PATTERNS[0]; i: number }) {
  const [open, setOpen] = useState(false);
  const impactColor = p.impact > 0.5 ? '#059669' : p.impact > 0 ? '#d97706' : '#dc2626';
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: i * 0.07 }}
      className="rounded-xl overflow-hidden"
      style={{ border: '1px solid #DDD6FE', background: 'rgba(255,255,255,0.8)' }}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen(!open)}
      >
        <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0"
          style={{ background: '#EDE9FE', color: '#6D28D9' }}>
          {p.hops}↑
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{p.label}</p>
          <p className="text-[10px]" style={{ color: 'var(--text-faint)' }}>Confiance : {Math.round(p.confidence * 100)} % · {p.hops} sauts de propagation</p>
        </div>
        <span className="text-sm font-bold font-mono mr-2 flex-shrink-0" style={{ color: impactColor }}>
          {p.impact >= 0 ? '+' : ''}{p.impact.toFixed(2)}
        </span>
        {open ? <ChevronUp size={14} className="text-violet-400 flex-shrink-0" /> : <ChevronDown size={14} className="text-violet-400 flex-shrink-0" />}
      </button>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="px-4 pb-3 text-xs leading-relaxed"
          style={{ color: '#4C1D95', borderTop: '1px solid #EDE9FE', paddingTop: 10 }}
        >
          {p.description}
        </motion.div>
      )}
    </motion.div>
  );
}

function MarketEffectCard({ e, i }: { e: typeof MARKET_EFFECTS[0]; i: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.08 }}
      className="rounded-2xl p-5"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', boxShadow: 'var(--shadow-card)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: `${e.color}15`, color: e.color }}>
          {e.icon}
        </div>
        <p className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{e.label}</p>
        <span className="ml-auto text-xs font-bold px-2.5 py-0.5 rounded-full"
          style={{ background: `${e.color}15`, color: e.color }}>
          {e.badge}
        </span>
      </div>
      <ul className="space-y-2">
        {e.points.map((pt, j) => (
          <li key={j} className="flex items-start gap-2 text-xs leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}>
            <span className="mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: e.color }} />
            {pt}
          </li>
        ))}
      </ul>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function StaticGNNInsight() {
  return (
    <div className="space-y-6">

      {/* ── Featured news banner ──────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl overflow-hidden"
        style={{ border: '1px solid #BFDBFE', boxShadow: '0 4px 24px rgba(37,99,235,0.10)' }}
      >
        <div className="px-5 py-3 flex items-center gap-3"
          style={{ background: 'linear-gradient(135deg, #1e3a8a, #2563eb)' }}>
          <Newspaper size={15} className="text-blue-200 flex-shrink-0" />
          <span className="text-blue-100 text-xs font-semibold uppercase tracking-wide">Actualité déclencheuse · {NEWS.date}</span>
          <span className="ml-auto text-xs font-bold px-2.5 py-0.5 rounded-full"
            style={{ background: '#dc2626', color: '#fff' }}>
            {NEWS.importance}
          </span>
        </div>
        <div className="px-5 py-4" style={{ background: '#EFF6FF' }}>
          <div className="flex items-start gap-3">
            <div>
              <p className="text-sm text-blue-500 font-medium mb-1">{NEWS.source} · {NEWS.category}</p>
              <h2 className="text-base font-bold leading-snug mb-3" style={{ color: '#1e3a8a' }}>
                {NEWS.title}
              </h2>
              <p className="text-sm leading-relaxed" style={{ color: '#334155' }}>{NEWS.summary}</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* ── GNN output + radar ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">

        {/* Bar chart — GNN predictions */}
        <div className="xl:col-span-3 rounded-2xl p-5"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
          <SectionHeader icon={<Brain size={15} />} title="Prédictions GNN — Impact propagation" badge="HeteroGATConv · Temporal" badgeColor="#7c3aed" />
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={GNN_PREDICTIONS} margin={{ top: 4, right: 8, left: -18, bottom: 0 }} barSize={18}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" height={44} />
              <YAxis domain={[-0.5, 1]} tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <ReferenceLine y={0} stroke="var(--border-strong)" strokeDasharray="3 3" />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload;
                  const c = d.impact > 0.3 ? '#059669' : d.impact < -0.1 ? '#dc2626' : '#d97706';
                  return (
                    <div className="rounded-xl p-3 text-xs shadow-lg" style={{ background: '#fff', border: '1px solid var(--border-subtle)' }}>
                      <p className="font-bold mb-1">{d.name}</p>
                      <p style={{ color: c }}>Impact GNN : {d.impact >= 0 ? '+' : ''}{d.impact.toFixed(2)}</p>
                      <p style={{ color: 'var(--text-muted)' }}>Confiance : {Math.round(d.confidence * 100)} %</p>
                      {d.hidden && <p style={{ color: '#7c3aed' }}>⚡ Risque caché détecté</p>}
                    </div>
                  );
                }}
              />
              <Bar dataKey="impact" radius={[4, 4, 0, 0]}>
                {GNN_PREDICTIONS.map((d, i) => (
                  <Cell key={i}
                    fill={d.hidden ? '#8B5CF6' : d.impact > 0.3 ? '#10b981' : d.impact < 0 ? '#ef4444' : '#f59e0b'}
                    opacity={d.name === 'Talan' ? 1 : 0.72}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-4 mt-1 justify-center flex-wrap">
            {[['#10b981','Impact positif'],['#ef4444','Impact négatif'],['#8B5CF6','Risque caché GNN']].map(([c, l]) => (
              <div key={l} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{l}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Radar — Talan vs Secteur */}
        <div className="xl:col-span-2 rounded-2xl p-5"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
          <SectionHeader icon={<Activity size={15} />} title="Positionnement Talan" />
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={RADAR_DATA}>
              <PolarGrid stroke="var(--chart-grid)" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} />
              <Radar name="Talan" dataKey="Talan" stroke="#2563eb" fill="#2563eb" fillOpacity={0.22} strokeWidth={2} />
              <Radar name="Secteur" dataKey="Secteur" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.1} strokeWidth={1.5} strokeDasharray="4 2" />
            </RadarChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-1">
            {[['#2563eb','Talan'],['#94a3b8','Secteur moyen']].map(([c,l]) => (
              <div key={l} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{l}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Conséquences ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
        <SectionHeader icon={<Zap size={15} />} title="Conséquences identifiées" badge="6 signaux" badgeColor="#f59e0b" />
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {CONSEQUENCES.map((c, i) => <ConsequenceCard key={i} c={c} i={i} />)}
        </div>
      </div>

      {/* ── Hidden patterns ──────────────────────────────────────────────── */}
      <div className="rounded-2xl p-5" style={{ background: '#F5F3FF', border: '1px solid #DDD6FE' }}>
        <SectionHeader icon={<Eye size={15} />} title="Patterns cachés détectés par GNN" badge="4 patterns · confiance moy. 83 %" badgeColor="#7c3aed" />
        <div className="space-y-2.5">
          {HIDDEN_PATTERNS.map((p, i) => <HiddenPatternRow key={i} p={p} i={i} />)}
        </div>
      </div>

      {/* ── Bourse ──────────────────────────────────────────────────────── */}
      <div className="rounded-2xl p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
        <SectionHeader icon={<TrendingUp size={15} />} title="Réaction boursière (BVMT)" badge="Talan +12.7 % le jour J" badgeColor="#10b981" />
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={BOURSE_DATA} margin={{ top: 4, right: 16, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
            <XAxis dataKey="day" tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="l" domain={[23, 30]} tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="r" orientation="right" domain={[7700, 8300]} tick={{ fill: 'var(--chart-legend)', fontSize: 10 }} axisLine={false} tickLine={false} />
            <ReferenceLine yAxisId="l" x="Annonce" stroke="#f59e0b" strokeDasharray="4 2" label={{ value: 'Annonce', fill: '#f59e0b', fontSize: 10 }} />
            <Tooltip formatter={(v: number, n: string) => [n === 'talan' ? `${v} DT` : v, n === 'talan' ? 'Talan' : 'BVMT Index']} />
            <Line yAxisId="l" type="monotone" dataKey="talan" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3, fill: '#2563eb' }} />
            <Line yAxisId="r" type="monotone" dataKey="index" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* ── Effets sur Bourse / Marché / Talan ──────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <ShieldAlert size={15} className="text-amber-500" />
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>Analyse d'impact sectorielle</h3>
          <span className="ml-auto text-xs px-2.5 py-0.5 rounded-full font-semibold"
            style={{ background: '#FEF3C7', color: '#92400E', border: '1px solid #FDE68A' }}>
            <Lightbulb size={10} className="inline mr-1" />
            GNN · Confiance 87 %
          </span>
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          {MARKET_EFFECTS.map((e, i) => <MarketEffectCard key={i} e={e} i={i} />)}
        </div>
      </div>

    </div>
  );
}

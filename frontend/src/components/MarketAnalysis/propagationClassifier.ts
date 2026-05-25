/**
 * propagationClassifier — heuristic mapping of TGAT propagation paths to one of
 * 9 strategic categories. Frontend-only, runs in O(paths). Every path gets
 * exactly one category — uncertain matches fall through to "Unclassified /
 * Ambiguous Signals".
 *
 * Rules order: node_type (canonical) first, then keyword match on source_name
 * and intermediate node names. Keywords are case-insensitive.
 */
import type { PropagationPath } from '../../api/marketAnalysisApi';

export type EventCategory =
  | 'Market Trend'
  | 'Competitor Action'
  | 'Technology Shift'
  | 'Economic Signal'
  | 'Company Internal Signal'
  | 'Regulation / Policy'
  | 'Sector Evolution'
  | 'Financial Indicator'
  | 'External Shock'
  | 'Unclassified / Ambiguous Signals';

export interface CategoryMeta {
  key:    EventCategory;
  color:  string;
  bg:     string;
  border: string;
  emoji:  string;
  short:  string;
}

export const CATEGORY_META: Record<EventCategory, CategoryMeta> = {
  'Market Trend':             { key: 'Market Trend',             color: '#0F766E', bg: '#F0FDFA', border: '#99F6E4', emoji: '📈', short: 'Trend' },
  'Competitor Action':        { key: 'Competitor Action',        color: '#DC2626', bg: '#FEE2E2', border: '#FECACA', emoji: '⚔️',  short: 'Comp.' },
  'Technology Shift':         { key: 'Technology Shift',         color: '#7C3AED', bg: '#F5F3FF', border: '#DDD6FE', emoji: '⚙️',  short: 'Tech' },
  'Economic Signal':          { key: 'Economic Signal',          color: '#6D28D9', bg: '#EDE9FE', border: '#DDD6FE', emoji: '📊', short: 'Macro' },
  'Company Internal Signal':  { key: 'Company Internal Signal',  color: '#0C4A6E', bg: '#F0F9FF', border: '#BAE6FD', emoji: '🏢', short: 'Co.' },
  'Regulation / Policy':      { key: 'Regulation / Policy',      color: '#065F46', bg: '#ECFDF5', border: '#A7F3D0', emoji: '📜', short: 'Reg.' },
  'Sector Evolution':         { key: 'Sector Evolution',         color: '#1E40AF', bg: '#EFF6FF', border: '#BFDBFE', emoji: '🏭', short: 'Sect.' },
  'Financial Indicator':      { key: 'Financial Indicator',      color: '#92400E', bg: '#FEF3C7', border: '#FDE68A', emoji: '💰', short: 'Fin.' },
  'External Shock':           { key: 'External Shock',           color: '#9A3412', bg: '#FFF7ED', border: '#FED7AA', emoji: '⚡', short: 'Shock' },
  'Unclassified / Ambiguous Signals': { key: 'Unclassified / Ambiguous Signals', color: '#64748B', bg: '#F1F5F9', border: '#E2E8F0', emoji: '❓', short: 'Other' },
};

const KEYWORDS: { [K in EventCategory]?: RegExp } = {
  'Market Trend':            /\b(trend|demand|growth|adoption|market share|tendance|demande|croissance|adoption|part de march)/i,
  'Competitor Action':       /\b(competitor|concurrent|capgemini|atos|sopra|accenture|wavestone|deloitte|ibm|expansion|recruit|acquisition|partner)/i,
  'Technology Shift':        /\b(ai|ia|cloud|saas|llm|gen.?ai|kubernetes|aws|azure|gcp|chip|gpu|edge|quantum|cyber|data ?engineering)/i,
  'Economic Signal':         /\b(gdp|pib|inflation|interest|taux|bce|fed|recession|unemployment|ch[oô]mage|growth rate|macro)/i,
  'Company Internal Signal': /\b(talan|hiring|layoff|restructur|reorg|earnings|results|r[ée]sultats|internal|interne)/i,
  'Regulation / Policy':     /\b(eu ai act|gdpr|rgpd|regulation|r[ée]glement|policy|directive|compliance|loi|d[ée]cret|cnil|dora)/i,
  'Sector Evolution':        /\b(sector|secteur|industry|industrie|vertical|banking|insurance|assurance|public|retail|sant[ée])/i,
  'Financial Indicator':     /\b(stock|equity|valuation|revenue|chiffre d.affaires|margin|ebitda|cash|cours|action)/i,
  'External Shock':          /\b(crisis|crise|war|guerre|pandemic|pandemie|disaster|cyberattack|hack|breach|outage|panne|sanction)/i,
};

// Canonical node-type → category. node_type wins over keyword when set.
const NODE_TYPE_MAP: Record<string, EventCategory> = {
  competitor:     'Competitor Action',
  regulation:     'Regulation / Policy',
  macroindicator: 'Economic Signal',
  sector:         'Sector Evolution',
  technology:     'Technology Shift',
  event:          'External Shock',
  client:         'Company Internal Signal',
  company:        'Company Internal Signal',
};

function tryKeyword(text: string): EventCategory | null {
  for (const [cat, rx] of Object.entries(KEYWORDS) as [EventCategory, RegExp][]) {
    if (rx.test(text)) return cat;
  }
  return null;
}

export function classifyPath(path: PropagationPath): { category: EventCategory; confidence: number } {
  const type = (path.source_type || '').toLowerCase();

  // 1. node_type maps directly — high confidence (0.9)
  if (NODE_TYPE_MAP[type]) {
    // But if it's a generic "company"/"client" AND source_name looks macro/regulation/etc, prefer keyword
    if (type === 'company' || type === 'client') {
      const kw = tryKeyword(path.source_name);
      if (kw && kw !== 'Company Internal Signal') return { category: kw, confidence: 0.75 };
    }
    return { category: NODE_TYPE_MAP[type], confidence: 0.9 };
  }

  // 2. Keyword on source_name + first step name — medium confidence (0.7)
  const haystack = [path.source_name, ...(path.steps ?? []).slice(0, 2).map((s) => s.node_name)].join(' ');
  const kw = tryKeyword(haystack);
  if (kw) return { category: kw, confidence: 0.7 };

  // 3. Sign-of-impact fallback: strong negative chain → External Shock
  if (path.chain_score <= -0.5) return { category: 'External Shock', confidence: 0.4 };

  // 4. Truly ambiguous
  return { category: 'Unclassified / Ambiguous Signals', confidence: 0.2 };
}

export interface ClassifiedPath {
  path:       PropagationPath;
  category:   EventCategory;
  confidence: number;
}

export interface CategoryBucket {
  category: EventCategory;
  meta:     CategoryMeta;
  paths:    ClassifiedPath[];
}

const CATEGORY_ORDER: EventCategory[] = [
  'External Shock',
  'Competitor Action',
  'Regulation / Policy',
  'Economic Signal',
  'Sector Evolution',
  'Technology Shift',
  'Market Trend',
  'Financial Indicator',
  'Company Internal Signal',
  'Unclassified / Ambiguous Signals',
];

export function classifyAndGroup(paths: PropagationPath[]): CategoryBucket[] {
  const buckets = new Map<EventCategory, ClassifiedPath[]>();
  for (const path of paths) {
    const { category, confidence } = classifyPath(path);
    if (!buckets.has(category)) buckets.set(category, []);
    buckets.get(category)!.push({ path, category, confidence });
  }
  // Each bucket sorted by chain severity (most impactful first)
  for (const list of buckets.values()) {
    list.sort((a, b) => Math.abs(b.path.chain_score) - Math.abs(a.path.chain_score));
  }
  return CATEGORY_ORDER
    .filter((c) => buckets.has(c))
    .map((c) => ({
      category: c,
      meta:     CATEGORY_META[c],
      paths:    buckets.get(c)!,
    }));
}

// ── Time-horizon helpers (used by timeline view) ──────────────────────────────

export type HorizonBucket = 'immediate' | 'short' | 'medium' | 'long';

const HORIZON_DAYS: Record<HorizonBucket, number> = {
  immediate: 7,
  short:     30,
  medium:    90,
  long:      180,
};

export function normalizeHorizon(raw: string | undefined): HorizonBucket {
  const r = (raw || '').toLowerCase();
  if (r.includes('immediate') || r.includes('48h') || r.includes('1-2 sem')) return 'immediate';
  if (r.includes('short')     || r.includes('2-4 sem'))                       return 'short';
  if (r.includes('medium')    || r.includes('1-3 mois'))                      return 'medium';
  if (r.includes('long')      || r.includes('3-6 mois') || r.includes('6+'))  return 'long';
  return 'medium';
}

export function horizonToOffsetDays(raw: string | undefined): number {
  return HORIZON_DAYS[normalizeHorizon(raw)];
}

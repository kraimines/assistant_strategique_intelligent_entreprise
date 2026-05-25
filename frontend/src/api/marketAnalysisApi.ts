import api from './client';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PipelineStatus {
  running: boolean;           // scheduler alive
  cycle_running: boolean;     // a cycle is actively executing right now
  last_run_at: string | null;
  next_run_at: string | null;
  articles_in_db: number;
  kg_nodes: number;
  kg_relations: number;
  last_report_id: string | null;
  errors_last_run: string[];
}

export interface MarketAlert {
  alert_id?: string;
  id?: string;
  generated_at: string;
  level: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  summary: string;
  affected_entities: string[];
  talan_impact_score: number;
  talan_recommended_action: string | null;
  source_articles: string[];
  gnn_hidden_risks: string[];
}

export interface NewsEntity {
  id?: string;
  name: string;
  label?: string;   // 'Company' | 'Technology' | 'Regulation' | 'Competitor' | 'Country' | 'Event' | 'Sector' | 'Person' | 'MarketTrend' | 'MacroIndicator'
  type: string;
  ticker?: string | null;
  aliases?: string[];
  properties?: Record<string, unknown>;
}

export interface CausalRelation {
  from_entity: string;
  from_type?: string;
  to_entity: string;
  to_type?: string;
  relation_type?: string;   // canonical enum value e.g. CAUSES_IMPACT_ON
  type?: string;            // alias returned by some backends
  impact_score: number;
  sentiment?: number;
  confidence: number;
  causality_score?: number;
  reason: string;
  evidence?: string;
  time_horizon: string;
  talan_relevant: boolean;
}

export interface NewsAnalysis {
  id: string;
  article_title: string;
  event_summary: string;
  event_type: string;
  severity: number;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  detected_category?: string;
  extraction_confidence?: number;
  overall_sentiment?: number;
  talan_impact_score: number;
  talan_impact_reason: string;
  talan_action_recommended: string | null;
  affected_tickers: string[];
  macro_indicators_affected?: string[];
  analysis_timestamp: string;
  article_url?: string | null;
  article_source?: string | null;
  article_published_at?: string | null;
  entities?: NewsEntity[];
  causal_relations?: CausalRelation[];
}

export interface KGSnapshot {
  nodes: {
    id: string;
    name: string;
    slug?: string;
    labels: string[];
    ticker?: string;
    properties?: Record<string, unknown>;
  }[];
  edges: {
    from: string;
    to: string;
    type: string;
    impact_score?: number;
    confidence?: number;
    reason?: string;
    timestamp?: string;
  }[];
  center: string;
}

export interface KGStats {
  available: boolean;
  total_nodes: number;
  total_relations: number;
  nodes_by_label: Record<string, number>;
}

export interface HiddenRisk {
  source: string;
  source_type: string;
  chain_score: number;
  hops: number;
  reasons: string[];
}

export interface GNNPrediction {
  entity_name: string;
  entity_type: string;
  predicted_impact: number;
  confidence: number;
  propagation_hops: number;
  hidden_risk: boolean;
}

export interface PropagationStep {
  node_name: string;
  node_type: string;
  relation_type: string;
  reason: string;
  impact_score: number;
  time_horizon: string;
  /** v3 — edge α from the compatibility matrix (0..1) */
  relation_strength?: number;
  /** v3 — derived from PlausibilityScorer rule features */
  business_relevance?: number;
  /** v3 — exp half-life decay factor (0..1, fresher → 1) */
  freshness_score?: number;
  /** v3 — confidence on the underlying causal edge */
  edge_confidence?: number;
  is_generic_hub_step?: boolean;
}

export type RiskCategory =
  | 'competitive' | 'regulatory' | 'supply_chain' | 'macro'
  | 'cyber' | 'talent' | 'tech_disruption';

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type TimeHorizon = 'immediate' | 'short' | 'medium' | 'long';
export type Uncertainty = 'low' | 'medium' | 'high';

export interface PropagationExplanation {
  // Executive header
  headline?: string;                 // one-line takeaway for cards / lists
  // Reasoning
  causal_reasoning: string;
  affected_business_unit: string;
  affected_sector: string;
  risk_category: RiskCategory;
  severity: Severity;
  // Action package
  recommended_action: string;
  recommended_owner?: string;        // e.g. "Direction Commerciale BU"
  // Time + money + reliability (director-grade)
  time_horizon: TimeHorizon;
  deadline_label?: string;           // e.g. "avant Q2 2026"
  financial_impact_eur?: string;     // e.g. "+€297k à +€551k de revenu additionnel"
  confidence_label?: string;         // "Forte" | "Moyenne" | "Limitée" | "Spéculative"
  confidence_rationale?: string;
  business_relevance?: string;       // "Why this matters to Talan" — concrete business reason
}

export interface PropagationPath {
  source_name: string;
  source_type: string;
  steps: PropagationStep[];
  chain_score: number;
  chain_conf: number;
  hops: number;
  time_horizon_label: string;
  narrative: string;
  event_title?: string;
  key_impact?: string;
  source_evidence?: string;
  // ── v3 ranking outputs ───────────────────────────────────────────
  business_plausibility?: number;
  causal_coherence?: number;
  path_specificity?: number;
  weighted_score?: number;
  impact_probability?: number;
  estimated_business_impact_pct?: number;
  confidence?: number;
  uncertainty?: Uncertainty;
  explanation?: PropagationExplanation | null;
}

export interface GNNResult {
  run_at: string;
  trigger_event: string;
  predictions: GNNPrediction[];
  talan_prediction: GNNPrediction | null;
  systemic_risk_score: number;
  top_hidden_risks: GNNPrediction[];
  propagation_paths: PropagationPath[];
  /** tgat_trained | tgat_random | heuristic */
  inference_mode?: string;
  /** v3 calibration / filter metadata */
  calibration_method?: 'platt' | 'isotonic' | 'none';
  filtered_path_count?: number;
  rejected_path_count?: number;
}

export interface ForecastResult {
  forecast_7d: number | null;
  forecast_30d: number | null;
  trend: 'improving' | 'deteriorating' | 'stable';
  confidence: number;
  data_points: number;
  method: string;
  generated_at: string;
}

export interface StrategicRecommendation {
  title: string;
  action: string;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  horizon: '7_days' | '30_days' | '90_days';
  domain: 'commercial' | 'rh' | 'financier' | 'technologique' | 'risque';
}

export interface RecommendationResult {
  recommendations: StrategicRecommendation[];
  trigger_event: string;
  talan_impact: number;
  systemic_risk: number;
  forecast_7d: number | null;
  forecast_30d: number | null;
  model_used: string;
  generated_at: string;
}

export interface PriceSnapshot {
  [ticker: string]: {
    price: number;
    change_pct: number;
    volume: number;
    volatility_annualised_pct: number;
  };
}

export interface RunResult {
  status: string;
  message: string;
  report?: unknown;
  alerts?: MarketAlert[];
}

// ── Enriched article (new classifier pipeline) ─────────────────────────────────

export type ArticleCategory =
  | 'regulatory_changes'
  | 'competitor_moves'
  | 'tech_launches'
  | 'financial_market_impact'
  | 'geopolitical_events'
  | 'talent_market_signals';

export interface EnrichedArticle {
  title: string;
  source: string;
  date: string | null;
  url: string;
  summary: string;
  impact_score: number;           // 1–10
  categories: ArticleCategory[];
  key_entities: string[];
  potential_impact_on_talent_or_competition: string;
}

// ── API calls ──────────────────────────────────────────────────────────────────

export const marketAnalysisApi = {
  // Pipeline
  getStatus: () =>
    api.get<PipelineStatus>('/market/status'),

  runPipeline: (tickers: string[] = [], force_gnn = false) =>
    api.post<RunResult>('/market/run', { tickers, force_gnn }),

  // Alerts
  getAlerts: (limit = 30, level?: string) =>
    api.get<MarketAlert[]>('/market/alerts', { params: { limit, level } }),

  // Analyses
  getAnalyses: (hours = 24, min_impact = 0, limit = 30) =>
    api.get<NewsAnalysis[]>('/market/analyses', {
      params: { hours, min_impact, limit },
    }),

  // Knowledge Graph
  getKGSnapshot: (company = 'Talan', hops = 2) =>
    api.get<KGSnapshot>('/market/kg/snapshot', { params: { company, hops } }),

  getKGStats: () =>
    api.get<KGStats>('/market/kg/stats'),

  getKGFull: (limit = 1200) =>
    api.get<KGSnapshot>('/market/kg/full', { params: { limit } }),

  getKGRisks: () =>
    api.get<HiddenRisk[]>('/market/kg/risks'),

  getHiddenRisks: (max_hops = 3) =>
    api.get<HiddenRisk[]>('/market/kg/hidden', { params: { max_hops } }),

  // GNN
  gnnPredict: (trigger = 'on_demand') =>
    api.get<GNNResult>('/market/gnn/predict', { params: { trigger }, timeout: 120_000 }),

  // Prices
  getPrices: () =>
    api.get<PriceSnapshot>('/market/prices'),

  // Reports
  listReports: (limit = 10) =>
    api.get('/market/reports', { params: { limit } }),

  getReport: (id: string) =>
    api.get(`/market/reports/${id}`),

  // Enriched news (new classifier pipeline)
  getEnrichedNews: (min_impact = 5, tier1_only = false, live = false) =>
    api.get<EnrichedArticle[]>('/market/news/enriched', {
      params: { min_impact, tier1_only, live },
    }),

  // Knowledge Graph — PageRank centrality
  getPageRank: (top_n = 40) =>
    api.get<Array<{ name: string; slug: string; label: string; score: number }>>(
      '/market/kg/pagerank',
      { params: { top_n } },
    ),

  // Knowledge Graph — temporal impact evolution
  getTemporalEvolution: (entity = 'Talan', hours = 168) =>
    api.get<Array<{ timestamp: string; impact_score: number; source_article: string }>>(
      '/market/kg/temporal',
      { params: { entity, hours } },
    ),

  // Forecast (LSTM 7d / 30d)
  getForecast: () =>
    api.get<ForecastResult>('/market/forecast'),

  // Strategic recommendations
  getRecommendations: () =>
    api.post<RecommendationResult>('/market/recommend', {}),

  getRecommendationHistory: (limit = 5) =>
    api.get<RecommendationResult[]>('/market/recommend/history', { params: { limit } }),

  // Human-in-the-loop: natural-language what-if simulation
  simulateEvent: (payload: QuickSimulationRequest, commit = false) =>
    api.post<ManualSimulationResult>('/market/simulate', payload, {
      params: { commit },
      timeout: 120_000,   // 2 min — LLM extraction + GNN inference
    }),

  // ── Manager feedback ────────────────────────────────────────────────
  submitFeedback: (payload: ManagerFeedbackCreate) =>
    api.post<ManagerFeedback>('/market/feedback', payload),

  listFeedback: (params: {
    item_kind?: FeedbackItemKind;
    item_id?: string;
    rating?: FeedbackRating;
    days?: number;
    limit?: number;
  } = {}) =>
    api.get<ManagerFeedback[]>('/market/feedback', { params }),

  getTrustScores: (days = 90) =>
    api.get<TrustScoresResponse>('/market/feedback/trust-scores', { params: { days } }),

  // ── Comex brief PDF export ──────────────────────────────────────────
  exportBrief: (payload: BriefExportRequest = {}) =>
    api.post<Blob>('/market/brief/export', payload, {
      responseType: 'blob',
      timeout: 120_000,
    }),
};

// ── Feedback & Brief types ─────────────────────────────────────────────────────

export type FeedbackRating  = 'relevant' | 'off_topic' | 'nuanced';
export type FeedbackItemKind = 'path' | 'recommendation' | 'alert' | 'simulation';

export interface ManagerFeedbackCreate {
  item_kind: FeedbackItemKind;
  item_id: string;
  item_category?: string;
  rating: FeedbackRating;
  comment?: string;
  context?: Record<string, unknown>;
}

export interface ManagerFeedback {
  id: string;
  submitted_at: string;
  user_id: string;
  user_role: string;
  item_kind: FeedbackItemKind;
  item_id: string;
  item_category: string;
  rating: FeedbackRating;
  comment: string;
  context: Record<string, unknown>;
}

export interface TrustScoreBucket {
  item_kind: FeedbackItemKind;
  item_category: string;
  total: number;
  relevant: number;
  off_topic: number;
  nuanced: number;
  trust_score: number;       // 0..1
  label: 'high' | 'medium' | 'low' | 'insufficient';
}

export interface TrustScoresResponse {
  generated_at: string;
  window_days: number;
  total_feedback: number;
  buckets: TrustScoreBucket[];
  overall: TrustScoreBucket | null;
}

export interface BriefExportRequest {
  period_days?: number;
  include_paths?: boolean;
  include_alerts?: boolean;
  include_recommendations?: boolean;
  include_forecast?: boolean;
  max_paths?: number;
  max_alerts?: number;
}

// ── Manual simulation types ────────────────────────────────────────────────────

export interface ManualEntity {
  name: string;
  type: string;            // Company | Competitor | Sector | Country | Event | Regulation | Supplier | Client | Concept | Technology | MacroIndicator
  sector?: string | null;
  country?: string | null;
  ticker?: string | null;
  aliases?: string[];
}

export interface ManualRelation {
  from_entity: string;
  to_entity: string;
  relation_type?: string;   // default CAUSES_IMPACT_ON
  impact_score: number;     // −1..1
  confidence: number;       // 0..1
  reason?: string;
  time_horizon?: string;    // immediate|short_term|medium_term|long_term
  evidence?: string;
}

/** Natural-language request — the LLM extracts entities + relations automatically */
export interface QuickSimulationRequest {
  event_text: string;
  category?: string;   // optional hint: 'competition' | 'regulation' | 'technology' | etc.
}

export interface ManualSimulationRequest {
  title: string;
  summary?: string;
  severity?: number;
  urgency?: 'low' | 'medium' | 'high' | 'critical';
  source?: string;
  entities: ManualEntity[];
  relations: ManualRelation[];
}

export interface EventGraphNode {
  name: string;
  type: string;
  sector?: string;
  country?: string;
  ticker?: string;
}

export interface EventGraphEdge {
  from_entity: string;
  to_entity: string;
  relation_type: string;
  impact_score: number;
}

export interface EventGraph {
  nodes: EventGraphNode[];
  edges: EventGraphEdge[];
}

export interface ManualSimulationResult {
  simulation_id: string;
  committed: boolean;
  talan_impact_pct: number;
  talan_impact_prob: number;
  systemic_risk_score: number;
  propagation_paths: PropagationPath[];
  filtered_path_count: number;
  rejected_path_count: number;
  augmented_node_count: number;
  augmented_edge_count: number;
  // LLM extraction metadata
  extracted_entities: string[];
  extracted_relations_count: number;
  llm_event_summary: string;
  // Strategic advice from dedicated explain LLM
  strategic_advice: string;
  // Raw LLM-extracted causal graph (only event entities, no KG data)
  event_graph: EventGraph;
}

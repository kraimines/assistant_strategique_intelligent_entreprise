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

export interface NewsAnalysis {
  id: string;
  article_title: string;
  event_summary: string;
  event_type: string;
  severity: number;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  talan_impact_score: number;
  talan_impact_reason: string;
  talan_action_recommended: string | null;
  affected_tickers: string[];
  analysis_timestamp: string;
  article_url?: string | null;
  article_source?: string | null;
  article_published_at?: string | null;
  entities?: { name: string; type: string; ticker?: string }[];
  causal_relations?: {
    from_entity: string;
    to_entity: string;
    impact_score: number;
    confidence: number;
    reason: string;
    time_horizon: string;
    talan_relevant: boolean;
  }[];
}

export interface KGSnapshot {
  nodes: {
    id: string;
    name: string;
    labels: string[];
    ticker?: string;
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

export interface GNNResult {
  run_at: string;
  trigger_event: string;
  predictions: GNNPrediction[];
  talan_prediction: GNNPrediction | null;
  systemic_risk_score: number;
  top_hidden_risks: GNNPrediction[];
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

  getKGRisks: () =>
    api.get<HiddenRisk[]>('/market/kg/risks'),

  getHiddenRisks: (max_hops = 3) =>
    api.get<HiddenRisk[]>('/market/kg/hidden', { params: { max_hops } }),

  // GNN
  gnnPredict: (trigger = 'on_demand') =>
    api.get<GNNResult>('/market/gnn/predict', { params: { trigger } }),

  // Prices
  getPrices: () =>
    api.get<PriceSnapshot>('/market/prices'),

  // Reports
  listReports: (limit = 10) =>
    api.get('/market/reports', { params: { limit } }),

  getReport: (id: string) =>
    api.get(`/market/reports/${id}`),
};

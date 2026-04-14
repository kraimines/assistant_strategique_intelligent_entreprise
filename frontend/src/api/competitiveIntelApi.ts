import api from './client';

export interface NewsArticle {
  title: string;
  url: string;
  published: string;
  summary: string;
  source: string;
  company?: string;
}

export interface SkillCount {
  skill: string;
  count: number;
}

export interface JobPosting {
  title: string;
  company: string;
  location: string;
  date_posted: string;
  skills: string[];
  description_snippet: string;
  url: string;
}

export interface JobsData {
  company: string;
  total_jobs_found: number;
  jobs: JobPosting[];
  top_skills_recruited: SkillCount[];
  strategic_signals: string[];
  scraped_at: string;
}

export interface KeyMove {
  company: string;
  move: string;
  date: string;
  source: string;
  url: string;
}

export interface RecommendedAction {
  priority: 'haute' | 'moyenne' | 'basse';
  action: string;
  axis: string;
}

export interface RadarScores {
  IA_Générative: number;
  Cloud: number;
  Recrutement: number;
  Partenariats: number;
  Innovation_Produit: number;
}

export interface AnticipatedMove {
  horizon: string;
  prediction: string;
  confidence: number;
  axis: string;
  rationale: string;
}

export interface CompetitiveAnalysis {
  companies_analyzed: string[];
  topic: string;
  threat_level: number;
  threat_label: string;
  radar_scores: RadarScores;
  key_moves: KeyMove[];
  anticipated_moves: AnticipatedMove[];
  hiring_signals: string[];
  recommended_actions: RecommendedAction[];
  summary: string;
  total_news: number;
  total_jobs: number;
  analyzed_at: string;
}

export interface ScanResult {
  companies: string[];
  topic: string;
  news: NewsArticle[];
  jobs: JobsData;
  analysis: CompetitiveAnalysis;
}

export const competitiveIntelApi = {
  scan: (companies: string[], topic: string, maxNews = 8) =>
    api.get<ScanResult>('/competitive-intel/scan', {
      params: { companies: companies.join(','), topic, max_news: maxNews },
    }),

  getNews: (company: string, limit = 10) =>
    api.get<NewsArticle[]>('/competitive-intel/news', {
      params: { company, limit },
    }),

  getJobs: (company: string, keywords = '') =>
    api.get<JobsData>('/competitive-intel/jobs', {
      params: { company, keywords },
    }),

  clearCache: () =>
    api.delete<{ cleared: number; message: string }>('/competitive-intel/cache/clear'),
};

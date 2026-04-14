/**
 * graphApi.ts — API client for the Neo4j World Model endpoints.
 */
import api from './client';

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  props: Record<string, unknown>;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface TimelineEvent {
  type: string;
  date: string;
  description: string;
  entity_id: string;
  entity_label: string;
}

export interface SearchResult {
  id: string;
  label: string;
  name: string;
  props: Record<string, unknown>;
}

export interface NodeDetail {
  label: string;
  props: Record<string, unknown>;
  relations: Array<{ type: string; direction: string; label: string; name: string }>;
}

export const graphApi = {
  getWorld: (view: string): Promise<GraphData> =>
    api.get(`/graph/world?view=${view}`).then(r => r.data),

  getTimeline: (): Promise<{ events: TimelineEvent[] }> =>
    api.get('/graph/timeline').then(r => r.data),

  search: (q: string): Promise<{ results: SearchResult[] }> =>
    api.get(`/graph/search?q=${encodeURIComponent(q)}`).then(r => r.data),

  getNodeDetail: (nodeId: string): Promise<NodeDetail> =>
    api.get(`/graph/node/${encodeURIComponent(nodeId)}`).then(r => r.data),
};

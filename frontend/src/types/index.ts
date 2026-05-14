export type Role = 'employee' | 'manager' | 'admin';
export type AgentType = 'hr' | 'crm' | 'erp' | 'rag' | 'orchestrator';
export type Domain = 'hr' | 'crm' | 'erp';

// Auth
export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  token: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role: Role;
}

// Chat
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agent?: AgentType;
  timestamp: Date;
  isStreaming?: boolean;
  toolResults?: ToolResult[];
  isReport?: boolean;
  meetingData?: import('./meetingTypes').MeetingData;

}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ToolResult {
  tool: string;
  result: string;
}

export interface StreamEvent {
  type: 'token' | 'agent' | 'tool_result' | 'done' | 'error';
  content?: string;
  agent?: AgentType;
  tool?: string;
  message?: string;
}

// Dashboard KPIs
export interface KPI {
  label: string;
  value: string | number;
  trend?: number;
  unit?: string;
  color?: 'cyan' | 'violet' | 'emerald' | 'amber' | 'pink';
}

export interface ChartDataPoint {
  label: string;
  value: number;
  [key: string]: string | number;
}

// Digital Twin graph
export interface GraphNode {
  id: string;
  label: string;
  type: 'employee' | 'department' | 'project' | 'client' | 'opportunity' | 'supplier';
  metrics?: Record<string, number | string>;
  color: string;
  size: number;
  x?: number;
  y?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
  weight?: number;
  color?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphEdge[];
}

// AI Insight
export interface AIInsight {
  id: string;
  title: string;
  description: string;
  severity: 'info' | 'warning' | 'critical';
  affectedEntities: string[];
  category: 'hr' | 'crm' | 'erp' | 'strategic';
  trend?: 'up' | 'down' | 'stable';
  value?: string;
}

// Department
export interface Department {
  id: string;
  name: string;
  manager: string;
  employeeCount: number;
  activeProjects: number;
  budget?: number;
  kpis?: Record<string, number | string>;
}

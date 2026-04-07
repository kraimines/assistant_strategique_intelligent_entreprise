import type { KPI, ChartDataPoint } from '../types';

// Employee dashboard mock data
export const employeeKPIs: KPI[] = [
  { label: 'Projets Actifs', value: 4, trend: 0, color: 'cyan' },
  { label: 'Solde Congés', value: 18, unit: 'jours', trend: -2, color: 'violet' },
  { label: 'Heures ce Mois', value: 162, unit: 'h', trend: 5, color: 'emerald' },
  { label: 'Score Performance', value: '8.4', unit: '/10', trend: 3, color: 'amber' },
];

export const hoursPerWeek: ChartDataPoint[] = [
  { label: 'S-8', value: 38 },
  { label: 'S-7', value: 42 },
  { label: 'S-6', value: 35 },
  { label: 'S-5', value: 44 },
  { label: 'S-4', value: 40 },
  { label: 'S-3', value: 45 },
  { label: 'S-2', value: 38 },
  { label: 'S-1', value: 41 },
];

export const projectProgress = [
  { name: 'Migration Cloud', progress: 72, status: 'Active', color: '#00d4ff' },
  { name: 'API Integration', progress: 45, status: 'Active', color: '#7c3aed' },
  { name: 'Dashboard v2', progress: 90, status: 'Active', color: '#10b981' },
  { name: 'Data Pipeline', progress: 20, status: 'Active', color: '#f59e0b' },
];

export const leaveRequests = [
  { id: 'LR001', type: 'Annual Leave', from: '2026-04-15', to: '2026-04-18', status: 'Approved', days: 3 },
  { id: 'LR002', type: 'Training Leave', from: '2026-05-02', to: '2026-05-03', status: 'Pending', days: 2 },
  { id: 'LR003', type: 'Sick Leave', from: '2026-03-10', to: '2026-03-11', status: 'Approved', days: 2 },
];

// Manager dashboard mock data
export const managerKPIs: KPI[] = [
  { label: 'Taille Équipe', value: 12, color: 'cyan' },
  { label: 'Approbations Pendantes', value: 3, trend: 1, color: 'amber' },
  { label: 'Projets en Cours', value: 7, color: 'emerald' },
  { label: 'Perf. Moyenne Équipe', value: '7.8', unit: '/10', trend: 2, color: 'violet' },
];

export const teamWorkload: ChartDataPoint[] = [
  { label: 'Alice B.', value: 45, overflow: 5 },
  { label: 'Mohamed K.', value: 38, overflow: 0 },
  { label: 'Sara H.', value: 52, overflow: 12 },
  { label: 'Yassine T.', value: 30, overflow: 0 },
  { label: 'Nour M.', value: 42, overflow: 2 },
  { label: 'Khaled B.', value: 35, overflow: 0 },
];

export const projectStatusDist = [
  { name: 'En Cours', value: 7, color: '#00d4ff' },
  { name: 'Planification', value: 2, color: '#7c3aed' },
  { name: 'Terminé', value: 4, color: '#10b981' },
  { name: 'En Retard', value: 1, color: '#ef4444' },
];

export const pendingApprovals = [
  { id: 'LR045', employee: 'Sara Hamdi', type: 'Annual Leave', from: '2026-04-20', to: '2026-04-25', days: 5 },
  { id: 'LR046', employee: 'Yassine Touati', type: 'Training Leave', from: '2026-04-28', to: '2026-04-29', days: 2 },
  { id: 'LR047', employee: 'Nour Mansouri', type: 'Sick Leave', from: '2026-04-08', to: '2026-04-08', days: 1 },
];

// Admin/Direction dashboard mock data
export const adminKPIs: KPI[] = [
  { label: 'Chiffre d\'Affaires', value: '2.4M', unit: 'TND', trend: 12, color: 'cyan' },
  { label: 'Clients Actifs', value: 47, trend: 3, color: 'violet' },
  { label: 'Opportunités Ouvertes', value: '890K', unit: 'TND', trend: 8, color: 'emerald' },
  { label: 'ROI Moyen Projets', value: '138', unit: '%', trend: 5, color: 'amber' },
];

export const monthlyRevenue: ChartDataPoint[] = [
  { label: 'Avr 25', value: 180000 },
  { label: 'Mai 25', value: 195000 },
  { label: 'Jun 25', value: 210000 },
  { label: 'Jul 25', value: 185000 },
  { label: 'Aoû 25', value: 170000 },
  { label: 'Sep 25', value: 225000 },
  { label: 'Oct 25', value: 240000 },
  { label: 'Nov 25', value: 215000 },
  { label: 'Déc 25', value: 230000 },
  { label: 'Jan 26', value: 198000 },
  { label: 'Fév 26', value: 245000 },
  { label: 'Mar 26', value: 260000 },
];

export const revenueBySegment: ChartDataPoint[] = [
  { label: 'Finance', value: 620000, target: 700000 },
  { label: 'Telecom', value: 480000, target: 500000 },
  { label: 'Retail', value: 310000, target: 350000 },
  { label: 'Industrie', value: 290000, target: 300000 },
  { label: 'Public', value: 200000, target: 250000 },
];

export const strategicAlerts = [
  { type: 'warning', message: '3 projets à risque de dépassement de délai', entity: 'Département Delivery' },
  { type: 'critical', message: 'Client Tunisie Telecom: signaux de désengagement détectés', entity: 'CRM' },
  { type: 'info', message: 'Opportunité pipeline: +18% vs Q3 2025', entity: 'Sales' },
];

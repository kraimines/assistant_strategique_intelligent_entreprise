import type { GraphData, AIInsight } from '../types';

export const mockGraphData: GraphData = {
  nodes: [
    // Departments
    { id: 'dept-rh', label: 'RH', type: 'department', color: '#7c3aed', size: 18 },
    { id: 'dept-it', label: 'IT', type: 'department', color: '#7c3aed', size: 18 },
    { id: 'dept-finance', label: 'Finance', type: 'department', color: '#7c3aed', size: 16 },
    { id: 'dept-commercial', label: 'Commercial', type: 'department', color: '#7c3aed', size: 18 },
    { id: 'dept-delivery', label: 'Delivery', type: 'department', color: '#7c3aed', size: 20 },
    { id: 'dept-management', label: 'Direction', type: 'department', color: '#7c3aed', size: 22 },

    // Key employees
    { id: 'emp-001', label: 'Ahmed Karim', type: 'employee', color: '#00d4ff', size: 12, metrics: { performance: 9.2, projects: 3 } },
    { id: 'emp-002', label: 'Sara Ben Ali', type: 'employee', color: '#00d4ff', size: 10, metrics: { performance: 8.5, projects: 2 } },
    { id: 'emp-003', label: 'Mohamed Trabelsi', type: 'employee', color: '#00d4ff', size: 11, metrics: { performance: 7.8, projects: 4 } },
    { id: 'emp-004', label: 'Nour Mansouri', type: 'employee', color: '#00d4ff', size: 10, metrics: { performance: 8.9, projects: 3 } },
    { id: 'emp-005', label: 'Yassine Toumi', type: 'employee', color: '#00d4ff', size: 9, metrics: { performance: 7.2, projects: 2 } },
    { id: 'emp-006', label: 'Ines Hamdi', type: 'employee', color: '#00d4ff', size: 11, metrics: { performance: 9.0, projects: 4 } },
    { id: 'emp-007', label: 'Khaled Bouzid', type: 'employee', color: '#00d4ff', size: 10, metrics: { performance: 8.1, projects: 3 } },
    { id: 'emp-008', label: 'Rim Chaabane', type: 'employee', color: '#00d4ff', size: 9, metrics: { performance: 7.5, projects: 2 } },
    { id: 'emp-009', label: 'Amine Jelassi', type: 'employee', color: '#00d4ff', size: 10, metrics: { performance: 8.7, projects: 3 } },
    { id: 'emp-010', label: 'Fatma Ouali', type: 'employee', color: '#00d4ff', size: 9, metrics: { performance: 8.3, projects: 2 } },

    // Projects
    { id: 'proj-001', label: 'Migration Cloud', type: 'project', color: '#10b981', size: 14, metrics: { progress: 72, budget: 150000 } },
    { id: 'proj-002', label: 'CRM Platform', type: 'project', color: '#10b981', size: 13, metrics: { progress: 45, budget: 200000 } },
    { id: 'proj-003', label: 'API Gateway', type: 'project', color: '#10b981', size: 12, metrics: { progress: 90, budget: 80000 } },
    { id: 'proj-004', label: 'Data Pipeline', type: 'project', color: '#10b981', size: 11, metrics: { progress: 20, budget: 60000 } },
    { id: 'proj-005', label: 'Mobile App', type: 'project', color: '#10b981', size: 12, metrics: { progress: 60, budget: 120000 } },

    // Clients
    { id: 'cli-001', label: 'Tunisie Telecom', type: 'client', color: '#f59e0b', size: 16, metrics: { revenue: 480000, contracts: 3 } },
    { id: 'cli-002', label: 'BNA Bank', type: 'client', color: '#f59e0b', size: 15, metrics: { revenue: 320000, contracts: 2 } },
    { id: 'cli-003', label: 'STEG', type: 'client', color: '#f59e0b', size: 14, metrics: { revenue: 250000, contracts: 2 } },
    { id: 'cli-004', label: 'Attijari Bank', type: 'client', color: '#f59e0b', size: 14, metrics: { revenue: 290000, contracts: 2 } },
    { id: 'cli-005', label: 'Office National', type: 'client', color: '#f59e0b', size: 13, metrics: { revenue: 180000, contracts: 1 } },

    // Opportunities
    { id: 'opp-001', label: 'Cloud Migration 2', type: 'opportunity', color: '#ec4899', size: 10, metrics: { value: 200000 } },
    { id: 'opp-002', label: 'AI Analytics', type: 'opportunity', color: '#ec4899', size: 11, metrics: { value: 350000 } },
    { id: 'opp-003', label: 'Cybersecurity', type: 'opportunity', color: '#ec4899', size: 10, metrics: { value: 150000 } },

    // Suppliers
    { id: 'sup-001', label: 'AWS Partner', type: 'supplier', color: '#6b7280', size: 11 },
    { id: 'sup-002', label: 'Oracle License', type: 'supplier', color: '#6b7280', size: 10 },
    { id: 'sup-003', label: 'Microsoft Azure', type: 'supplier', color: '#6b7280', size: 11 },
  ],
  links: [
    // Employees to departments
    { source: 'emp-001', target: 'dept-it', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-002', target: 'dept-rh', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-003', target: 'dept-delivery', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-004', target: 'dept-it', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-005', target: 'dept-commercial', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-006', target: 'dept-delivery', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-007', target: 'dept-finance', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-008', target: 'dept-rh', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-009', target: 'dept-it', label: 'WORKS_IN', weight: 3 },
    { source: 'emp-010', target: 'dept-delivery', label: 'WORKS_IN', weight: 3 },

    // Employees to projects
    { source: 'emp-001', target: 'proj-001', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-001', target: 'proj-003', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-003', target: 'proj-001', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-003', target: 'proj-002', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-004', target: 'proj-004', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-006', target: 'proj-002', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-006', target: 'proj-005', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-009', target: 'proj-003', label: 'ASSIGNED_TO', weight: 2 },
    { source: 'emp-010', target: 'proj-005', label: 'ASSIGNED_TO', weight: 2 },

    // Projects to clients
    { source: 'proj-001', target: 'cli-001', label: 'FOR_CLIENT', weight: 4 },
    { source: 'proj-002', target: 'cli-002', label: 'FOR_CLIENT', weight: 4 },
    { source: 'proj-003', target: 'cli-001', label: 'FOR_CLIENT', weight: 3 },
    { source: 'proj-004', target: 'cli-003', label: 'FOR_CLIENT', weight: 3 },
    { source: 'proj-005', target: 'cli-004', label: 'FOR_CLIENT', weight: 3 },

    // Clients to opportunities
    { source: 'cli-001', target: 'opp-001', label: 'HAS_OPPORTUNITY', weight: 2 },
    { source: 'cli-002', target: 'opp-002', label: 'HAS_OPPORTUNITY', weight: 2 },
    { source: 'cli-003', target: 'opp-003', label: 'HAS_OPPORTUNITY', weight: 2 },

    // Projects to suppliers
    { source: 'proj-001', target: 'sup-001', label: 'USES', weight: 1 },
    { source: 'proj-001', target: 'sup-003', label: 'USES', weight: 1 },
    { source: 'proj-002', target: 'sup-002', label: 'USES', weight: 1 },

    // Departments under direction
    { source: 'dept-management', target: 'dept-rh', label: 'MANAGES', weight: 2 },
    { source: 'dept-management', target: 'dept-it', label: 'MANAGES', weight: 2 },
    { source: 'dept-management', target: 'dept-finance', label: 'MANAGES', weight: 2 },
    { source: 'dept-management', target: 'dept-commercial', label: 'MANAGES', weight: 2 },
    { source: 'dept-management', target: 'dept-delivery', label: 'MANAGES', weight: 2 },

    // Employee to employee collaborations
    { source: 'emp-001', target: 'emp-004', label: 'COLLABORATES', weight: 1 },
    { source: 'emp-003', target: 'emp-006', label: 'COLLABORATES', weight: 1 },
    { source: 'emp-005', target: 'cli-001', label: 'MANAGES_ACCOUNT', weight: 3 },
    { source: 'emp-005', target: 'cli-002', label: 'MANAGES_ACCOUNT', weight: 3 },
  ],
};

export const mockInsights: AIInsight[] = [
  {
    id: 'ins-001',
    title: 'Surcharge détectée — Équipe Delivery',
    description: "3 membres de l'équipe Delivery dépassent 45h/semaine depuis 3 semaines consécutives. Risque de burnout et de départ élevé.",
    severity: 'critical',
    affectedEntities: ['emp-003', 'emp-006', 'emp-010', 'dept-delivery'],
    category: 'hr',
    trend: 'up',
    value: '+22% charge vs mois dernier',
  },
  {
    id: 'ins-002',
    title: 'Signaux de désengagement — Tunisie Telecom',
    description: "Le client Tunisie Telecom présente 3 indicateurs de risque: délai de paiement +30j, réduction des réunions -60%, retour négatif sur le projet Migration Cloud.",
    severity: 'critical',
    affectedEntities: ['cli-001', 'proj-001'],
    category: 'crm',
    trend: 'down',
    value: 'Probabilité churn: 68%',
  },
  {
    id: 'ins-003',
    title: 'Opportunité pipeline en croissance',
    description: "Le pipeline commercial a augmenté de 18% ce trimestre. L'opportunité AI Analytics (350K TND) est la plus prometteuse avec une probabilité de conversion à 75%.",
    severity: 'info',
    affectedEntities: ['opp-002', 'dept-commercial'],
    category: 'crm',
    trend: 'up',
    value: '+18% vs Q3 2025',
  },
  {
    id: 'ins-004',
    title: 'Délai de paiement factures ERP',
    description: "12 factures en statut 'Overdue' représentant 180K TND. Les clients STEG et Office National cumulent 70% des retards.",
    severity: 'warning',
    affectedEntities: ['cli-003', 'cli-005'],
    category: 'erp',
    trend: 'up',
    value: '180 000 TND en souffrance',
  },
  {
    id: 'ins-005',
    title: 'Compétences clés à renforcer',
    description: "Seulement 2 employés ont le niveau Expert en Cloud Architecture. Avec 3 projets cloud planifiés, un recrutement ou une formation urgente est recommandée.",
    severity: 'warning',
    affectedEntities: ['dept-it', 'dept-delivery'],
    category: 'hr',
    trend: 'stable',
    value: '2/12 employés IT certifiés Cloud',
  },
];

export const departments = [
  { id: 'dept-management', name: 'Direction', manager: 'Directeur Général', employeeCount: 3, activeProjects: 0, budget: 500000, x: 400, y: 80 },
  { id: 'dept-rh', name: 'RH', manager: 'Sara Ben Ali', employeeCount: 8, activeProjects: 1, budget: 200000, x: 150, y: 220 },
  { id: 'dept-it', name: 'IT', manager: 'Ahmed Karim', employeeCount: 15, activeProjects: 4, budget: 450000, x: 310, y: 260 },
  { id: 'dept-finance', name: 'Finance', manager: 'Khaled Bouzid', employeeCount: 6, activeProjects: 0, budget: 150000, x: 490, y: 260 },
  { id: 'dept-commercial', name: 'Commercial', manager: 'Yassine Toumi', employeeCount: 10, activeProjects: 2, budget: 300000, x: 640, y: 220 },
  { id: 'dept-delivery', name: 'Delivery', manager: 'Ines Hamdi', employeeCount: 20, activeProjects: 5, budget: 600000, x: 400, y: 320 },
];

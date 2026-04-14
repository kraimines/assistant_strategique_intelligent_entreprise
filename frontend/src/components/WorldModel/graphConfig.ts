/**
 * graphConfig.ts — Node styling, perspectives, and colour palette.
 */

// ── Node colours per label ────────────────────────────────────────────────────
export const NODE_COLORS: Record<string, string> = {
  Company:      '#00d4ff',  // cyan  — root
  Department:   '#7c3aed',  // violet
  Employee:     '#00d4ff',  // cyan-blue
  Project:      '#10b981',  // emerald
  Skill:        '#34d399',  // emerald-light
  Account:      '#f59e0b',  // amber
  Contact:      '#fbbf24',  // amber-light
  Opportunity:  '#ec4899',  // pink
  Customer:     '#fb923c',  // orange
  Invoice:      '#ef4444',  // red
  SalesOrder:   '#f97316',  // orange-dark
  Supplier:     '#6b7280',  // gray
  Product:      '#a78bfa',  // purple-light
  Default:      '#94a3b8',  // slate
};

// ── Node emoji icons per label ────────────────────────────────────────────────
export const NODE_ICONS: Record<string, string> = {
  Company:     '🏢',
  Department:  '🏛️',
  Employee:    '👤',
  Project:     '📁',
  Skill:       '⚡',
  Account:     '🏦',
  Contact:     '📇',
  Opportunity: '💎',
  Customer:    '🛒',
  Invoice:     '🧾',
  SalesOrder:  '📦',
  Supplier:    '🏭',
  Product:     '📦',
  Default:     '⬡',
};

// ── Node sizes per label ──────────────────────────────────────────────────────
export const NODE_SIZES: Record<string, number> = {
  Company:     18,
  Department:  14,
  Employee:    10,
  Project:     11,
  Skill:        7,
  Account:     12,
  Contact:      8,
  Opportunity: 12,
  Customer:    11,
  Invoice:      8,
  SalesOrder:   9,
  Supplier:    10,
  Product:      7,
  Default:      8,
};

// ── Relationship colours ──────────────────────────────────────────────────────
export const REL_COLORS: Record<string, string> = {
  BELONGS_TO:        'rgba(124,58,237,0.6)',
  MANAGED_BY:        'rgba(0,212,255,0.5)',
  HAS_DEPARTMENT:    'rgba(0,212,255,0.7)',
  MANAGES_PROJECT:   'rgba(16,185,129,0.6)',
  HAS_OPPORTUNITY:   'rgba(236,72,153,0.6)',
  OWNS_OPPORTUNITY:  'rgba(245,158,11,0.6)',
  HAS_CONTACT:       'rgba(251,191,36,0.5)',
  HAS_INVOICE:       'rgba(239,68,68,0.5)',
  PLACED_ORDER:      'rgba(249,115,22,0.5)',
  SUPPLIES:          'rgba(107,114,128,0.5)',
  HAS_SKILL:         'rgba(52,211,153,0.5)',
  Default:           'rgba(148,163,184,0.3)',
};

// ── Perspectives / views ──────────────────────────────────────────────────────
export const PERSPECTIVES = [
  {
    id: 'org',
    label: 'Organisation Globale',
    icon: '🏢',
    description: 'Hiérarchie Company → Departments → Employees → Projects',
  },
  {
    id: 'crm',
    label: 'Pipeline CRM',
    icon: '💎',
    description: 'Accounts → Opportunities → Contacts → Owners',
  },
  {
    id: 'hr',
    label: 'HR & Compétences',
    icon: '👥',
    description: 'Départements → Employés → Skills → Congés',
  },
  {
    id: 'erp',
    label: 'ERP & Finance',
    icon: '🧾',
    description: 'Clients → Factures → Commandes → Fournisseurs',
  },
  {
    id: 'cross',
    label: 'Relations Croisées',
    icon: '🕸️',
    description: 'Employee ↔ Project ↔ Account ↔ Customer',
  },
];

// ── Node type filters ─────────────────────────────────────────────────────────
export const NODE_TYPE_FILTERS = [
  { type: 'Employee',    label: 'Employés',     color: NODE_COLORS.Employee },
  { type: 'Department',  label: 'Départements', color: NODE_COLORS.Department },
  { type: 'Project',     label: 'Projets',      color: NODE_COLORS.Project },
  { type: 'Account',     label: 'Comptes CRM',  color: NODE_COLORS.Account },
  { type: 'Opportunity', label: 'Opportunités', color: NODE_COLORS.Opportunity },
  { type: 'Customer',    label: 'Clients ERP',  color: NODE_COLORS.Customer },
  { type: 'Invoice',     label: 'Factures',     color: NODE_COLORS.Invoice },
  { type: 'Skill',       label: 'Compétences',  color: NODE_COLORS.Skill },
  { type: 'Product',     label: 'Produits',     color: NODE_COLORS.Product },
  { type: 'Supplier',    label: 'Fournisseurs', color: NODE_COLORS.Supplier },
];

// ── Event type icons for timeline ─────────────────────────────────────────────
export const EVENT_ICONS: Record<string, string> = {
  hire:          '👤',
  deal_won:      '🏆',
  overdue:       '🚨',
  project_start: '🚀',
  default:       '📌',
};

export const EVENT_COLORS: Record<string, string> = {
  hire:          '#00d4ff',
  deal_won:      '#10b981',
  overdue:       '#ef4444',
  project_start: '#7c3aed',
  default:       '#94a3b8',
};

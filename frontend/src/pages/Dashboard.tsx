import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  PieChart, Pie, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  Check, X, AlertTriangle, TrendingUp, TrendingDown, Users, Briefcase, Clock, Star,
  Target, Zap, Award, Activity, ChevronRight, Bell, Calendar,
  DollarSign, BarChart2, Layers, ArrowUpRight, ArrowDownRight,
} from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import { useAuthStore } from '../stores/authStore';
import {
  employeeKPIs, hoursPerWeek, projectProgress, leaveRequests,
  managerKPIs, teamWorkload, projectStatusDist, pendingApprovals,
  adminKPIs, monthlyRevenue, revenueBySegment, strategicAlerts,
} from '../data/mockDashboard';

/* ── Chart palette adapted for sky-blue context ─────────────────────────── */
const C = {
  blue:    '#0ea5e9',
  indigo:  '#6366f1',
  teal:    '#14b8a6',
  emerald: '#10b981',
  amber:   '#f59e0b',
  danger:  '#ef4444',
  violet:  '#8b5cf6',
  pink:    '#ec4899',
};

const TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: 'rgba(255,255,255,0.95)',
  backdropFilter: 'blur(12px)',
  border: '1px solid rgba(14,116,144,0.15)',
  borderRadius: '12px',
  color: '#0f172a',
  fontSize: '12px',
  boxShadow: '0 8px 32px rgba(14,116,144,0.15)',
};
const GRID_COLOR = 'rgba(14,116,144,0.08)';
const AXIS_COLOR = '#64748b';

/* ── Shared animated stat badge ─────────────────────────────────────────── */
function TrendBadge({ value }: { value?: number }) {
  if (value === undefined) return null;
  if (value > 0)
    return (
      <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full"
        style={{ background: 'rgba(16,185,129,0.15)', color: '#059669' }}>
        <ArrowUpRight size={11} /> +{value}%
      </span>
    );
  if (value < 0)
    return (
      <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full"
        style={{ background: 'rgba(239,68,68,0.12)', color: '#dc2626' }}>
        <ArrowDownRight size={11} /> {value}%
      </span>
    );
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: 'rgba(100,116,139,0.12)', color: '#64748b' }}>
      ─ 0%
    </span>
  );
}

/* ── Advanced KPI Card ───────────────────────────────────────────────────── */
const CARD_THEMES: Record<string, { grad: string; icon: string; glow: string; text: string }> = {
  cyan:    { grad: 'linear-gradient(135deg,#0ea5e9,#38bdf8)', icon: 'rgba(14,165,233,0.15)', glow: 'rgba(14,165,233,0.25)', text: '#0369a1' },
  violet:  { grad: 'linear-gradient(135deg,#7c3aed,#a78bfa)', icon: 'rgba(124,58,237,0.15)', glow: 'rgba(124,58,237,0.25)', text: '#5b21b6' },
  emerald: { grad: 'linear-gradient(135deg,#059669,#34d399)', icon: 'rgba(5,150,105,0.15)',  glow: 'rgba(5,150,105,0.25)',  text: '#047857' },
  amber:   { grad: 'linear-gradient(135deg,#d97706,#fbbf24)', icon: 'rgba(217,119,6,0.15)',  glow: 'rgba(217,119,6,0.25)',  text: '#b45309' },
  pink:    { grad: 'linear-gradient(135deg,#db2777,#f472b6)', icon: 'rgba(219,39,119,0.15)', glow: 'rgba(219,39,119,0.25)', text: '#9d174d' },
  teal:    { grad: 'linear-gradient(135deg,#0d9488,#2dd4bf)', icon: 'rgba(13,148,136,0.15)', glow: 'rgba(13,148,136,0.25)', text: '#0f766e' },
};

interface KPIAdvProps {
  label: string; value: string | number; unit?: string; trend?: number;
  color?: string; icon?: React.ReactNode; delay?: number;
  sparkData?: number[];
}

function KPIAdvanced({ label, value, unit, trend, color = 'cyan', icon, delay = 0, sparkData }: KPIAdvProps) {
  const t = CARD_THEMES[color] ?? CARD_THEMES.cyan;
  const spark = sparkData ?? [40, 55, 45, 60, 52, 70, 65, 80];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="relative rounded-[18px] p-5 overflow-hidden cursor-default select-none"
      style={{
        background: 'rgba(255,255,255,0.90)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(255,255,255,0.70)',
        boxShadow: `0 4px 24px ${t.glow}, 0 1px 4px rgba(0,0,0,0.06)`,
      }}
      whileHover={{ y: -3, boxShadow: `0 12px 40px ${t.glow}, 0 2px 8px rgba(0,0,0,0.08)` }}
    >
      {/* Accent top bar */}
      <div className="absolute top-0 left-0 right-0 h-1 rounded-t-[18px]" style={{ background: t.grad }} />

      <div className="flex items-start justify-between mt-1">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: AXIS_COLOR }}>
            {label}
          </p>
          <div className="flex items-baseline gap-1.5 mb-2">
            <span className="text-[2.1rem] font-bold leading-none tracking-tight" style={{ color: t.text }}>
              {value}
            </span>
            {unit && (
              <span className="text-sm font-medium" style={{ color: AXIS_COLOR }}>{unit}</span>
            )}
          </div>
          <TrendBadge value={trend} />
        </div>

        {/* Icon circle */}
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 ml-3"
          style={{ background: t.icon, color: t.text }}>
          {icon}
        </div>
      </div>

      {/* Mini sparkline */}
      <div className="mt-4 -mx-1">
        <ResponsiveContainer width="100%" height={36}>
          <LineChart data={spark.map((v, i) => ({ v, i }))}>
            <Line type="monotone" dataKey="v" stroke={t.text} strokeWidth={2}
              dot={false} strokeOpacity={0.7} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  );
}

/* ── Section heading ─────────────────────────────────────────────────────── */
function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-1">
      <h2 className="text-base font-bold" style={{ color: '#0f172a' }}>{children}</h2>
      {sub && <p className="text-xs mt-0.5" style={{ color: AXIS_COLOR }}>{sub}</p>}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   EMPLOYEE DASHBOARD
   ══════════════════════════════════════════════════════════════════════════════ */
const statusBadge: Record<string, 'emerald' | 'amber' | 'red'> = {
  Approved: 'emerald', Pending: 'amber', Rejected: 'red',
};

const skillData = [
  { skill: 'React', A: 85 }, { skill: 'Python', A: 70 }, { skill: 'SQL', A: 90 },
  { skill: 'Agile', A: 75 }, { skill: 'DevOps', A: 55 }, { skill: 'Leadership', A: 60 },
];

function EmployeeDashboard() {
  const icons = [<Clock size={20} />, <Star size={20} />, <Briefcase size={20} />, <TrendingUp size={20} />];
  const sparks = [
    [30, 35, 38, 36, 42, 40, 45, 41],
    [20, 18, 20, 19, 18, 17, 18, 16],
    [140, 145, 152, 148, 155, 158, 160, 162],
    [7.5, 7.8, 7.6, 8.0, 8.1, 7.9, 8.3, 8.4],
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Hero greeting */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="rounded-[20px] p-6 relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(14,165,233,0.85) 0%, rgba(99,102,241,0.80) 100%)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.35)',
          boxShadow: '0 8px 40px rgba(14,165,233,0.30)',
        }}
      >
        <div className="absolute inset-0 opacity-10"
          style={{ background: 'radial-gradient(circle at 80% 50%, white 0%, transparent 60%)' }} />
        <div className="relative flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-sky-100 mb-1">Tableau de bord — Employé</p>
            <h1 className="text-2xl font-bold text-white">Bonne journée ! 👋</h1>
            <p className="text-sky-200 text-sm mt-1">Vous avez <strong className="text-white">2</strong> tâches en attente et <strong className="text-white">1</strong> réunion aujourd'hui.</p>
          </div>
          <div className="hidden md:flex gap-4">
            {[{ label: 'Projets', val: 4, icon: <Briefcase size={16} /> },
              { label: 'Congés', val: '18j', icon: <Calendar size={16} /> },
              { label: 'Perf.', val: '8.4', icon: <Star size={16} /> }].map(s => (
              <div key={s.label} className="text-center px-4 py-2 rounded-2xl"
                style={{ background: 'rgba(255,255,255,0.18)' }}>
                <div className="flex items-center gap-1.5 text-sky-100 text-xs mb-1">{s.icon} {s.label}</div>
                <p className="text-xl font-bold text-white">{s.val}</p>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {employeeKPIs.map((kpi, i) => (
          <KPIAdvanced key={kpi.label} {...kpi} delay={i * 0.07} icon={icons[i]} sparkData={sparks[i]} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Hours area chart */}
        <GlassCard animate className="p-5 lg:col-span-3">
          <SectionTitle sub="8 dernières semaines">Heures travaillées</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={hoursPerWeek} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="hoursGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.blue} stopOpacity={0.30} />
                  <stop offset="95%" stopColor={C.blue} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="label" tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis domain={[28, 50]} tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Area type="monotone" dataKey="value" stroke={C.blue} strokeWidth={2.5}
                fill="url(#hoursGrad)" dot={{ fill: C.blue, r: 4, strokeWidth: 2, stroke: '#fff' }} />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Skills radar */}
        <GlassCard animate className="p-5 lg:col-span-2">
          <SectionTitle sub="Compétences clés">Profil de compétences</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={skillData} margin={{ top: 0, right: 20, bottom: 0, left: 20 }}>
              <PolarGrid stroke={GRID_COLOR} />
              <PolarAngleAxis dataKey="skill" tick={{ fill: AXIS_COLOR, fontSize: 10 }} />
              <Radar dataKey="A" stroke={C.indigo} fill={C.indigo} fillOpacity={0.25} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Project progress */}
        <GlassCard animate className="p-5">
          <SectionTitle sub="Progression actuelle">Avancement des projets</SectionTitle>
          <div className="space-y-5 mt-4">
            {projectProgress.map((p, idx) => (
              <motion.div key={p.name}
                initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + idx * 0.07 }}>
                <div className="flex justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: p.color }} />
                    <span className="text-sm font-semibold" style={{ color: '#1e293b' }}>{p.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold" style={{ color: p.color }}>{p.progress}%</span>
                    <Badge label={p.status} variant="emerald" />
                  </div>
                </div>
                <div className="h-2.5 rounded-full overflow-hidden"
                  style={{ background: 'rgba(14,116,144,0.10)' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${p.progress}%` }}
                    transition={{ duration: 1.0, delay: 0.3 + idx * 0.1, ease: 'easeOut' }}
                    className="h-full rounded-full"
                    style={{
                      background: `linear-gradient(90deg, ${p.color}cc, ${p.color})`,
                      boxShadow: `0 0 8px ${p.color}60`,
                    }}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </GlassCard>

        {/* Leave requests */}
        <GlassCard animate className="p-5">
          <div className="flex items-center justify-between mb-4">
            <SectionTitle>Mes demandes de congé</SectionTitle>
            <Button size="sm" variant="secondary" icon={<Calendar size={13} />}>Nouvelle</Button>
          </div>
          <div className="space-y-3">
            {leaveRequests.map((r) => (
              <motion.div key={r.id}
                className="flex items-center gap-3 p-3.5 rounded-xl transition-all"
                style={{ background: 'rgba(14,165,233,0.06)', border: '1px solid rgba(14,165,233,0.12)' }}
                whileHover={{ background: 'rgba(14,165,233,0.10)' }}
              >
                <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(14,165,233,0.15)', color: '#0ea5e9' }}>
                  <Calendar size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold" style={{ color: '#1e293b' }}>{r.type}</p>
                  <p className="text-xs mt-0.5" style={{ color: AXIS_COLOR }}>
                    {r.from} → {r.to} · <strong>{r.days}j</strong>
                  </p>
                </div>
                <Badge label={r.status} variant={statusBadge[r.status] || 'gray'} />
              </motion.div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   MANAGER DASHBOARD
   ══════════════════════════════════════════════════════════════════════════════ */
function ManagerDashboard() {
  const [activeApproval, setActiveApproval] = useState<string | null>(null);
  const icons = [<Users size={20} />, <Bell size={20} />, <Layers size={20} />, <Award size={20} />];
  const sparks = [
    [10, 11, 11, 12, 11, 12, 12, 12],
    [1, 2, 3, 2, 4, 3, 3, 3],
    [5, 6, 7, 6, 7, 7, 8, 7],
    [7.0, 7.3, 7.5, 7.4, 7.6, 7.7, 7.8, 7.8],
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-[20px] p-6 relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(99,102,241,0.85) 0%, rgba(139,92,246,0.80) 100%)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.35)',
          boxShadow: '0 8px 40px rgba(99,102,241,0.28)',
        }}>
        <div className="absolute inset-0 opacity-10"
          style={{ background: 'radial-gradient(circle at 80% 50%, white 0%, transparent 60%)' }} />
        <div className="relative">
          <p className="text-sm font-medium text-indigo-200 mb-1">Tableau de bord — Manager</p>
          <h1 className="text-2xl font-bold text-white">Vue équipe & projets</h1>
          <p className="text-indigo-200 text-sm mt-1">
            <strong className="text-white">3</strong> approbations en attente · Équipe de <strong className="text-white">12</strong> collaborateurs
          </p>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {managerKPIs.map((kpi, i) => (
          <KPIAdvanced key={kpi.label} {...kpi} delay={i * 0.07} icon={icons[i]} sparkData={sparks[i]} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Team workload composed chart */}
        <GlassCard animate className="p-5 lg:col-span-2">
          <SectionTitle sub="Heures / semaine — comparé au seuil de 40h">Charge de travail équipe</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={teamWorkload} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="label" tick={{ fill: AXIS_COLOR, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ color: AXIS_COLOR, fontSize: 11 }} />
              <Bar dataKey="value" name="Heures normales" fill={C.blue} radius={[6, 6, 0, 0]} fillOpacity={0.85} />
              <Bar dataKey="overflow" name="Dépassement" fill={C.danger} radius={[6, 6, 0, 0]} fillOpacity={0.75} />
              <Line type="monotone" dataKey={() => 40} stroke={C.amber} strokeDasharray="5 3"
                strokeWidth={2} dot={false} name="Seuil 40h" />
            </ComposedChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Project donut */}
        <GlassCard animate className="p-5">
          <SectionTitle sub="Répartition actuelle">Statut des projets</SectionTitle>
          <ResponsiveContainer width="100%" height={170}>
            <PieChart>
              <Pie data={projectStatusDist} cx="50%" cy="50%"
                innerRadius={48} outerRadius={72} dataKey="value" paddingAngle={3} strokeWidth={0}>
                {projectStatusDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-2">
            {projectStatusDist.map((d) => (
              <div key={d.name} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} />
                <span className="text-[11px]" style={{ color: AXIS_COLOR }}>
                  {d.name} <strong style={{ color: '#1e293b' }}>({d.value})</strong>
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Pending approvals */}
      <GlassCard animate className="p-5">
        <div className="flex items-center justify-between mb-4">
          <SectionTitle sub={`${pendingApprovals.length} en attente de traitement`}>Approbations</SectionTitle>
          <span className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full"
            style={{ background: 'rgba(245,158,11,0.15)', color: '#b45309' }}>
            <Bell size={11} /> {pendingApprovals.length} nouvelles
          </span>
        </div>
        <div className="space-y-3">
          {pendingApprovals.map((a) => (
            <AnimatePresence key={a.id}>
              <motion.div
                layout
                initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-4 p-4 rounded-2xl transition-all"
                style={{
                  background: activeApproval === a.id ? 'rgba(14,165,233,0.08)' : 'rgba(255,255,255,0.70)',
                  border: '1px solid rgba(14,165,233,0.15)',
                }}
                onMouseEnter={() => setActiveApproval(a.id)}
                onMouseLeave={() => setActiveApproval(null)}
              >
                {/* Avatar */}
                <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 text-sm font-bold text-white"
                  style={{ background: 'linear-gradient(135deg, #0ea5e9, #6366f1)' }}>
                  {a.employee.split(' ').map(n => n[0]).join('')}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold" style={{ color: '#1e293b' }}>{a.employee}</p>
                  <p className="text-xs mt-0.5" style={{ color: AXIS_COLOR }}>
                    {a.type} · {a.from} → {a.to}
                    <span className="ml-2 font-semibold px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(245,158,11,0.12)', color: '#b45309' }}>
                      {a.days}j
                    </span>
                  </p>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <Button size="sm" variant="secondary" icon={<Check size={13} />}>Approuver</Button>
                  <Button size="sm" variant="danger"    icon={<X size={13} />}>Refuser</Button>
                </div>
              </motion.div>
            </AnimatePresence>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   ADMIN DASHBOARD
   ══════════════════════════════════════════════════════════════════════════════ */
const alertCfg = {
  critical: { bg: 'rgba(239,68,68,0.10)',  border: 'rgba(239,68,68,0.20)',  color: '#dc2626', icon: <AlertTriangle size={15} />, dot: '#ef4444' },
  warning:  { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.20)', color: '#b45309', icon: <Zap size={15} />,           dot: '#f59e0b' },
  info:     { bg: 'rgba(14,165,233,0.10)', border: 'rgba(14,165,233,0.20)', color: '#0369a1', icon: <Activity size={15} />,      dot: '#0ea5e9' },
};

function AdminDashboard() {
  const icons = [<DollarSign size={20} />, <Users size={20} />, <Target size={20} />, <BarChart2 size={20} />];
  const sparks = [
    [180, 195, 210, 185, 170, 225, 240, 260],
    [43, 44, 45, 46, 45, 47, 47, 47],
    [700, 750, 780, 810, 840, 860, 870, 890],
    [115, 120, 125, 128, 130, 133, 135, 138],
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Hero admin */}
      <motion.div
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-[20px] p-6 relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(13,148,136,0.85) 0%, rgba(14,165,233,0.80) 100%)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.35)',
          boxShadow: '0 8px 40px rgba(13,148,136,0.28)',
        }}>
        <div className="absolute inset-0 opacity-10"
          style={{ background: 'radial-gradient(circle at 80% 50%, white 0%, transparent 60%)' }} />
        <div className="relative flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-teal-100 mb-1">Vue Stratégique — Direction</p>
            <h1 className="text-2xl font-bold text-white">Tableau de bord exécutif</h1>
            <p className="text-teal-100 text-sm mt-1">
              Données en temps réel · Avril 2026 · <strong className="text-white">3</strong> alertes actives
            </p>
          </div>
          <div className="hidden md:flex items-center gap-3">
            <div className="text-right">
              <p className="text-teal-100 text-xs">Mois en cours</p>
              <p className="text-2xl font-bold text-white">260K</p>
              <p className="text-teal-200 text-xs">TND · +6.1%</p>
            </div>
            <div className="w-px h-12 bg-teal-300 opacity-40" />
            <div className="text-right">
              <p className="text-teal-100 text-xs">YTD</p>
              <p className="text-2xl font-bold text-white">2.4M</p>
              <p className="text-teal-200 text-xs">TND · +12%</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {adminKPIs.map((kpi, i) => (
          <KPIAdvanced key={kpi.label} {...kpi} delay={i * 0.07} icon={icons[i]} sparkData={sparks[i]} />
        ))}
      </div>

      {/* Alerts */}
      <div className="grid grid-cols-1 gap-3">
        {strategicAlerts.map((a, i) => {
          const cfg = alertCfg[a.type as keyof typeof alertCfg] ?? alertCfg.info;
          return (
            <motion.div key={i}
              initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08 }}
              className="flex items-center gap-3 px-4 py-3.5 rounded-2xl"
              style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
              <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: `${cfg.dot}20`, color: cfg.color }}>
                {cfg.icon}
              </div>
              <span className="text-sm font-semibold flex-1" style={{ color: cfg.color }}>{a.message}</span>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-xs px-2 py-0.5 rounded-lg font-mono"
                  style={{ background: 'rgba(255,255,255,0.60)', color: '#475569' }}>
                  {a.entity}
                </span>
                <ChevronRight size={14} style={{ color: cfg.color, opacity: 0.6 }} />
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Revenue chart */}
      <GlassCard animate className="p-5">
        <div className="flex items-center justify-between mb-4">
          <SectionTitle sub="12 derniers mois (TND)">Chiffre d'affaires mensuel</SectionTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
              <TrendingUp size={13} /> +12% vs an passé
            </span>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={monthlyRevenue} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={C.teal} stopOpacity={0.30} />
                <stop offset="95%" stopColor={C.teal} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
            <XAxis dataKey="label" tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
            <Tooltip contentStyle={TOOLTIP_STYLE}
              formatter={(v: number) => [`${v.toLocaleString()} TND`, 'CA']} />
            <Area type="monotone" dataKey="value" stroke={C.teal} strokeWidth={2.5}
              fill="url(#revGrad)" dot={{ fill: C.teal, r: 4, strokeWidth: 2, stroke: '#fff' }} />
          </AreaChart>
        </ResponsiveContainer>
      </GlassCard>

      {/* Revenue by segment + extra stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <GlassCard animate className="p-5 lg:col-span-2">
          <SectionTitle sub="Réalisé vs objectif par secteur">CA par secteur</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={revenueBySegment} barGap={4} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="label" tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: AXIS_COLOR, fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip contentStyle={TOOLTIP_STYLE}
                formatter={(v: number) => [`${v.toLocaleString()} TND`]} />
              <Legend wrapperStyle={{ color: AXIS_COLOR, fontSize: 11 }} />
              <Bar dataKey="value"  name="Réalisé"  fill={C.blue}  radius={[6, 6, 0, 0]} fillOpacity={0.90} />
              <Bar dataKey="target" name="Objectif" fill={C.teal}  radius={[6, 6, 0, 0]} fillOpacity={0.50} />
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Quick stats panel */}
        <GlassCard animate className="p-5">
          <SectionTitle sub="Indicateurs clés">Performance globale</SectionTitle>
          <div className="mt-4 space-y-4">
            {[
              { label: 'Taux de réalisation objectifs', pct: 88, color: C.teal },
              { label: 'Satisfaction clients', pct: 91, color: C.emerald },
              { label: 'Taux de rétention RH', pct: 95, color: C.indigo },
              { label: 'Pipeline qualifié', pct: 73, color: C.amber },
            ].map((s, i) => (
              <div key={i}>
                <div className="flex justify-between mb-1.5">
                  <span className="text-xs font-medium" style={{ color: '#334155' }}>{s.label}</span>
                  <span className="text-xs font-bold font-mono" style={{ color: s.color }}>{s.pct}%</span>
                </div>
                <div className="h-2 rounded-full overflow-hidden"
                  style={{ background: 'rgba(14,116,144,0.10)' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${s.pct}%` }}
                    transition={{ duration: 1.0, delay: 0.4 + i * 0.1 }}
                    className="h-full rounded-full"
                    style={{
                      background: `linear-gradient(90deg, ${s.color}88, ${s.color})`,
                      boxShadow: `0 0 6px ${s.color}50`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   ROOT EXPORT
   ══════════════════════════════════════════════════════════════════════════════ */
export default function Dashboard() {
  const { user } = useAuthStore();
  const role = user?.role;

  const titleMap: Record<string, string> = {
    employee: `Bonjour, ${user?.first_name} 👋`,
    manager:  `Vue Manager — ${user?.first_name}`,
    admin:    'Vue Stratégique — Direction',
  };

  return (
    <AppShell title={titleMap[role || 'employee'] || 'Dashboard'}>
      {role === 'employee' && <EmployeeDashboard />}
      {role === 'manager'  && <ManagerDashboard />}
      {role === 'admin'    && <AdminDashboard />}
      {!role && <EmployeeDashboard />}
    </AppShell>
  );
}

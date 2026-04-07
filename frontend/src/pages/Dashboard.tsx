import { motion } from 'framer-motion';
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Check, X, AlertTriangle, TrendingUp, Users, Briefcase, Clock, Star } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import KPICard from '../components/dashboard/KPICard';
import GlassCard from '../components/ui/GlassCard';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import { useAuthStore } from '../stores/authStore';
import {
  employeeKPIs, hoursPerWeek, projectProgress, leaveRequests,
  managerKPIs, teamWorkload, projectStatusDist, pendingApprovals,
  adminKPIs, monthlyRevenue, revenueBySegment, strategicAlerts,
} from '../data/mockDashboard';

const tooltipStyle = {
  backgroundColor: 'rgba(12,12,20,0.95)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  color: '#fff',
  fontSize: '12px',
};

const statusBadge: Record<string, 'emerald' | 'amber' | 'red'> = {
  Approved: 'emerald',
  Pending: 'amber',
  Rejected: 'red',
};

function EmployeeDashboard() {
  return (
    <div className="p-6 space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {employeeKPIs.map((kpi, i) => (
          <KPICard key={kpi.label} {...kpi} delay={i * 0.08}
            icon={[<Clock size={18} />, <Star size={18} />, <Briefcase size={18} />, <TrendingUp size={18} />][i]}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hours chart */}
        <GlassCard animate className="p-5">
          <h3 className="text-white font-semibold mb-4 text-sm">Heures travaillées / semaine</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={hoursPerWeek}>
              <defs>
                <linearGradient id="hoursGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="label" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="value" stroke="#00d4ff" strokeWidth={2} fill="url(#hoursGrad)" dot={{ fill: '#00d4ff', r: 3 }} />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Project progress */}
        <GlassCard animate className="p-5">
          <h3 className="text-white font-semibold mb-4 text-sm">Avancement des projets</h3>
          <div className="space-y-4">
            {projectProgress.map((p) => (
              <div key={p.name}>
                <div className="flex justify-between mb-1.5">
                  <span className="text-white/70 text-xs">{p.name}</span>
                  <span className="text-white/50 text-xs font-mono">{p.progress}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${p.progress}%` }}
                    transition={{ duration: 1, delay: 0.3 }}
                    className="h-full rounded-full"
                    style={{ background: p.color, boxShadow: `0 0 8px ${p.color}80` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Leave requests */}
      <GlassCard animate className="p-5">
        <h3 className="text-white font-semibold mb-4 text-sm">Mes demandes de congé</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/8">
                <th className="text-left text-white/40 text-xs pb-3 font-medium">ID</th>
                <th className="text-left text-white/40 text-xs pb-3 font-medium">Type</th>
                <th className="text-left text-white/40 text-xs pb-3 font-medium">Période</th>
                <th className="text-left text-white/40 text-xs pb-3 font-medium">Jours</th>
                <th className="text-left text-white/40 text-xs pb-3 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="space-y-2">
              {leaveRequests.map((r) => (
                <tr key={r.id} className="border-b border-white/4 hover:bg-white/3 transition-colors">
                  <td className="py-3 text-white/50 font-mono text-xs">{r.id}</td>
                  <td className="py-3 text-white/80 text-xs">{r.type}</td>
                  <td className="py-3 text-white/60 text-xs">{r.from} → {r.to}</td>
                  <td className="py-3 text-white/60 text-xs">{r.days}j</td>
                  <td className="py-3">
                    <Badge label={r.status} variant={statusBadge[r.status] || 'gray'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}

function ManagerDashboard() {
  return (
    <div className="p-6 space-y-6">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {managerKPIs.map((kpi, i) => (
          <KPICard key={kpi.label} {...kpi} delay={i * 0.08}
            icon={[<Users size={18} />, <AlertTriangle size={18} />, <Briefcase size={18} />, <TrendingUp size={18} />][i]}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Team workload */}
        <GlassCard animate className="p-5 lg:col-span-2">
          <h3 className="text-white font-semibold mb-4 text-sm">Charge de travail équipe (h/semaine)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={teamWorkload}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="label" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#00d4ff" radius={[4, 4, 0, 0]} fillOpacity={0.85} name="Heures normales" />
              <Bar dataKey="overflow" fill="#ef4444" radius={[4, 4, 0, 0]} fillOpacity={0.7} name="Dépassement" />
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Project status donut */}
        <GlassCard animate className="p-5">
          <h3 className="text-white font-semibold mb-4 text-sm">Statut des projets</h3>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={projectStatusDist} cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value" paddingAngle={3}>
                {projectStatusDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-x-3 gap-y-1.5 justify-center mt-1">
            {projectStatusDist.map((d) => (
              <div key={d.name} className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ background: d.color }} />
                <span className="text-white/50 text-[10px]">{d.name} ({d.value})</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Pending approvals */}
      <GlassCard animate className="p-5">
        <h3 className="text-white font-semibold mb-4 text-sm">Approbations en attente</h3>
        <div className="space-y-3">
          {pendingApprovals.map((a) => (
            <div key={a.id} className="flex items-center justify-between p-3.5 rounded-xl bg-white/3 border border-white/6 hover:border-white/12 transition-all">
              <div>
                <p className="text-white/85 text-sm font-medium">{a.employee}</p>
                <p className="text-white/45 text-xs mt-0.5">{a.type} — {a.from} au {a.to} ({a.days}j)</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" icon={<Check size={13} />}>Approuver</Button>
                <Button size="sm" variant="danger" icon={<X size={13} />}>Refuser</Button>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

function AdminDashboard() {
  return (
    <div className="p-6 space-y-6">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {adminKPIs.map((kpi, i) => (
          <KPICard key={kpi.label} {...kpi} delay={i * 0.08} />
        ))}
      </div>

      {/* Alerts */}
      <div className="space-y-2">
        {strategicAlerts.map((a, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`
              flex items-center gap-3 p-3.5 rounded-xl border text-sm
              ${a.type === 'critical'
                ? 'bg-red-500/8 border-red-500/25 text-red-300'
                : a.type === 'warning'
                ? 'bg-amber-500/8 border-amber-500/25 text-amber-300'
                : 'bg-cyber-cyan/8 border-cyber-cyan/20 text-cyber-cyan'
              }
            `}
          >
            <AlertTriangle size={15} className="flex-shrink-0" />
            <span className="flex-1">{a.message}</span>
            <span className="text-white/30 text-xs">{a.entity}</span>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue area chart */}
        <GlassCard animate className="p-5 lg:col-span-2">
          <h3 className="text-white font-semibold mb-4 text-sm">Chiffre d'affaires mensuel (TND)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={monthlyRevenue}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="label" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v/1000).toFixed(0)}K`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v.toLocaleString()} TND`, 'CA']} />
              <Area type="monotone" dataKey="value" stroke="#7c3aed" strokeWidth={2} fill="url(#revGrad)" dot={{ fill: '#7c3aed', r: 3 }} />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Revenue by segment */}
        <GlassCard animate className="p-5 lg:col-span-2">
          <h3 className="text-white font-semibold mb-4 text-sm">CA par secteur vs objectif</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={revenueBySegment}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="label" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v/1000).toFixed(0)}K`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v.toLocaleString()} TND`]} />
              <Legend wrapperStyle={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }} />
              <Bar dataKey="value" fill="#00d4ff" radius={[4, 4, 0, 0]} fillOpacity={0.85} name="Réalisé" />
              <Bar dataKey="target" fill="#7c3aed" radius={[4, 4, 0, 0]} fillOpacity={0.5} name="Objectif" />
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuthStore();
  const role = user?.role;

  const titleMap: Record<string, string> = {
    employee: `Bonjour, ${user?.first_name} 👋`,
    manager: `Vue Manager — ${user?.first_name}`,
    admin: 'Vue Stratégique — Direction',
  };

  return (
    <AppShell title={titleMap[role || 'employee'] || 'Dashboard'}>
      {role === 'employee' && <EmployeeDashboard />}
      {role === 'manager' && <ManagerDashboard />}
      {role === 'admin' && <AdminDashboard />}
      {!role && <EmployeeDashboard />}
    </AppShell>
  );
}

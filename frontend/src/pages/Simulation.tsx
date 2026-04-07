import { useState } from 'react';
import { motion } from 'framer-motion';
import { FlaskConical, Play, RotateCcw, AlertTriangle, TrendingDown, TrendingUp } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LineChart, Line } from 'recharts';
import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';

const scenarios = [
  {
    id: 'lose-client',
    label: 'Perte du top client',
    description: 'Simulation de la perte de Tunisie Telecom (480K TND CA/an)',
    severity: 'critical' as const,
    icon: '📉',
  },
  {
    id: 'hire-10',
    label: 'Embauche de 10 développeurs',
    description: 'Impact sur capacité delivery, masse salariale et CA potentiel',
    severity: 'info' as const,
    icon: '👥',
  },
  {
    id: 'price-increase',
    label: 'Augmentation tarifs +15%',
    description: 'Simulation impact sur taux de rétention clients et revenus',
    severity: 'warning' as const,
    icon: '💰',
  },
  {
    id: 'new-market',
    label: 'Expansion marché Libya',
    description: 'Coûts opération + projections CA sur 24 mois',
    severity: 'info' as const,
    icon: '🌍',
  },
];

const baseRevenue = [240, 245, 260, 258, 270, 275, 280, 285, 290, 295, 300, 308];
const simulatedRevenue = [240, 245, 178, 160, 155, 158, 162, 168, 175, 182, 188, 195];
const months = ['Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar'];

const baseChart = months.map((m, i) => ({
  month: m,
  base: baseRevenue[i],
  simulated: simulatedRevenue[i],
}));

const impactMetrics = [
  { label: 'CA Annuel', base: '2.4M TND', simulated: '1.9M TND', delta: -21, bad: true },
  { label: 'Effectif Delivery', base: '20 ETP', simulated: '15 ETP', delta: -25, bad: true },
  { label: 'Projets Actifs', base: '7', simulated: '5', delta: -28, bad: true },
  { label: 'Risque Financier', base: 'Faible', simulated: 'Élevé', delta: null, bad: true },
];

const severityBadge: Record<string, 'red' | 'amber' | 'cyan'> = {
  critical: 'red',
  warning: 'amber',
  info: 'cyan',
};

const tooltipStyle = {
  backgroundColor: 'rgba(12,12,20,0.95)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  color: '#fff',
  fontSize: '12px',
};

export default function Simulation() {
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<boolean>(false);

  const handleRun = () => {
    if (!selectedScenario) return;
    setRunning(true);
    setResult(false);
    setTimeout(() => {
      setRunning(false);
      setResult(true);
    }, 1800);
  };

  return (
    <AppShell title="Simulation Stratégique">
      <div className="p-6 space-y-6 max-w-6xl">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}>
          <GlassCard className="p-5">
            <div className="flex items-center gap-3 mb-2">
              <FlaskConical size={20} className="text-cyber-violet" />
              <h2 className="text-white font-semibold">Simulation de Scénarios Stratégiques</h2>
            </div>
            <p className="text-white/50 text-sm">
              Modélisez l'impact de décisions stratégiques sur vos KPIs avant de les prendre.
              Les simulations utilisent vos données réelles pour projeter les conséquences.
            </p>
          </GlassCard>
        </motion.div>

        {/* Scenario selector */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {scenarios.map((s, i) => (
            <motion.button
              key={s.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => { setSelectedScenario(s.id); setResult(false); }}
              className={`
                p-4 rounded-2xl border text-left transition-all duration-200
                ${selectedScenario === s.id
                  ? 'bg-cyber-violet/12 border-cyber-violet/40 shadow-[0_0_20px_rgba(124,58,237,0.15)]'
                  : 'glass border-white/8 hover:border-white/18'
                }
              `}
            >
              <span className="text-2xl mb-3 block">{s.icon}</span>
              <div className="mb-1.5">
                <Badge label={s.severity} variant={severityBadge[s.severity]} />
              </div>
              <h3 className="text-white font-semibold text-sm mb-1">{s.label}</h3>
              <p className="text-white/40 text-xs leading-relaxed">{s.description}</p>
            </motion.button>
          ))}
        </div>

        {/* Run button */}
        <div className="flex items-center gap-4">
          <Button
            size="lg"
            loading={running}
            disabled={!selectedScenario}
            onClick={handleRun}
            icon={<Play size={16} />}
          >
            {running ? 'Simulation en cours...' : 'Lancer la simulation'}
          </Button>
          {result && (
            <Button
              size="lg"
              variant="ghost"
              onClick={() => { setResult(false); setSelectedScenario(null); }}
              icon={<RotateCcw size={16} />}
            >
              Réinitialiser
            </Button>
          )}
        </div>

        {/* Results */}
        {result && selectedScenario === 'lose-client' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-5"
          >
            {/* Alert */}
            <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/25 text-red-300">
              <AlertTriangle size={18} />
              <p className="text-sm font-medium">
                Impact critique détecté — La perte de Tunisie Telecom réduirait le CA de 21% sur les 12 prochains mois
              </p>
            </div>

            {/* Impact KPIs */}
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              {impactMetrics.map((m, i) => (
                <motion.div
                  key={m.label}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.08 }}
                >
                  <GlassCard className="p-4">
                    <p className="text-white/40 text-xs uppercase tracking-wider mb-2">{m.label}</p>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-white/40 text-xs">Actuel:</span>
                      <span className="text-white/70 text-sm font-mono">{m.base}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-white/40 text-xs">Simulé:</span>
                      <span className={`text-sm font-mono font-semibold ${m.bad ? 'text-red-400' : 'text-cyber-emerald'}`}>
                        {m.simulated}
                      </span>
                    </div>
                    {m.delta !== null && (
                      <div className="flex items-center gap-1 mt-2">
                        {m.bad ? (
                          <TrendingDown size={12} className="text-red-400" />
                        ) : (
                          <TrendingUp size={12} className="text-cyber-emerald" />
                        )}
                        <span className={`text-xs font-medium ${m.bad ? 'text-red-400' : 'text-cyber-emerald'}`}>
                          {m.delta > 0 ? '+' : ''}{m.delta}%
                        </span>
                      </div>
                    )}
                  </GlassCard>
                </motion.div>
              ))}
            </div>

            {/* Revenue projection chart */}
            <GlassCard animate className="p-5">
              <h3 className="text-white font-semibold mb-4 text-sm">Projection CA sur 12 mois (K TND)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={baseChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="month" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v}K TND`]} />
                  <Legend wrapperStyle={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }} />
                  <Line type="monotone" dataKey="base" stroke="#10b981" strokeWidth={2} dot={false} name="Scénario actuel" />
                  <Line type="monotone" dataKey="simulated" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Sans Tunisie Telecom" />
                </LineChart>
              </ResponsiveContainer>
            </GlassCard>

            {/* Recommendations */}
            <GlassCard animate className="p-5">
              <h3 className="text-white font-semibold mb-3 text-sm">Recommandations IA</h3>
              <div className="space-y-3">
                {[
                  { priority: 'Urgent', action: 'Planifier une réunion de rétention avec le DG de Tunisie Telecom', icon: '🔴' },
                  { priority: 'Court terme', action: 'Accélérer la conversion de l\'opportunité AI Analytics (350K TND)', icon: '🟡' },
                  { priority: 'Moyen terme', action: 'Diversifier le portefeuille clients pour réduire la dépendance à un seul compte', icon: '🟢' },
                ].map((r, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-white/3 border border-white/6">
                    <span className="text-lg flex-shrink-0">{r.icon}</span>
                    <div>
                      <Badge label={r.priority} variant={i === 0 ? 'red' : i === 1 ? 'amber' : 'emerald'} />
                      <p className="text-white/75 text-sm mt-1">{r.action}</p>
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {result && selectedScenario !== 'lose-client' && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <GlassCard animate className="p-8 text-center">
              <FlaskConical size={40} className="text-cyber-violet mx-auto mb-4 opacity-50" />
              <p className="text-white/60 text-sm">
                Simulation "{scenarios.find((s) => s.id === selectedScenario)?.label}" calculée avec succès.
              </p>
              <p className="text-white/30 text-xs mt-2">Rapport complet disponible via l'assistant IA</p>
            </GlassCard>
          </motion.div>
        )}
      </div>
    </AppShell>
  );
}

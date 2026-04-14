/**
 * PricesTicker — live price/volume/volatility table for tracked tickers.
 * Highlights Talan (TAL.PA) and shows change_pct with color coding.
 */
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus, RefreshCw, BarChart2 } from 'lucide-react';
import type { PriceSnapshot } from '../../api/marketAnalysisApi';

interface Props {
  prices: PriceSnapshot | undefined;
  loading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}

const TICKER_LABELS: Record<string, string> = {
  'TAL.PA': 'Talan',
  '^CAC40': 'CAC 40',
  '^GSPC': 'S&P 500',
  '^NDX': 'NASDAQ',
  'MSFT': 'Microsoft',
  'NVDA': 'NVIDIA',
  'GOOGL': 'Google',
  'META': 'Meta',
  'AMD': 'AMD',
  'SAP': 'SAP',
  'CAP.PA': 'Capgemini',
  'SOP.PA': 'Sopra Steria',
  'ATO.PA': 'Atos',
  '^VIX': 'VIX',
  'EURUSD=X': 'EUR/USD',
  'BZ=F': 'Brent',
};

const TICKER_GROUPS = [
  { label: 'Talan & Secteur IT', tickers: ['TAL.PA', 'CAP.PA', 'SOP.PA', 'ATO.PA', 'SAP'] },
  { label: 'Big Tech', tickers: ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD'] },
  { label: 'Marchés & Macro', tickers: ['^CAC40', '^GSPC', '^NDX', '^VIX', 'EURUSD=X', 'BZ=F'] },
];

function ChangeChip({ change }: { change: number }) {
  const abs = Math.abs(change);
  if (abs < 0.01) return (
    <span className="flex items-center gap-1 text-xs text-white/30">
      <Minus size={11} /> 0.00%
    </span>
  );
  const color = change >= 0 ? '#10b981' : '#ef4444';
  const Icon = change >= 0 ? TrendingUp : TrendingDown;
  return (
    <span className="flex items-center gap-1 text-xs font-mono font-semibold" style={{ color }}>
      <Icon size={11} />
      {change >= 0 ? '+' : ''}{change.toFixed(2)}%
    </span>
  );
}

function VolatilityBar({ value }: { value: number }) {
  const capped = Math.min(value, 100);
  const color = capped >= 40 ? '#ef4444' : capped >= 25 ? '#f97316' : capped >= 15 ? '#f59e0b' : '#10b981';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 rounded-full bg-white/8 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${capped}%`, background: color }} />
      </div>
      <span className="text-[10px] font-mono" style={{ color }}>{value.toFixed(0)}%</span>
    </div>
  );
}

export default function PricesTicker({ prices, loading, onRefresh, refreshing }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-32 rounded-xl bg-white/3 border border-white/6 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!prices || Object.keys(prices).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <BarChart2 size={40} className="text-white/15" />
        <p className="text-white/30 text-sm">Données de marché indisponibles</p>
        <p className="text-white/20 text-xs">yfinance requis · vérifiez la connexion</p>
        <button onClick={onRefresh} className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs transition-all"
          style={{ background: 'rgba(0,212,255,0.08)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.20)' }}>
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          Actualiser
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-white/40">Snapshot en temps réel · {Object.keys(prices).length} tickers</p>
        <button onClick={onRefresh} disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all"
          style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.45)' }}>
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
          Actualiser
        </button>
      </div>

      {TICKER_GROUPS.map((group) => {
        const groupPrices = group.tickers.filter((t) => prices[t]);
        if (!groupPrices.length) return null;
        return (
          <div key={group.label} className="rounded-xl overflow-hidden"
            style={{ border: '1px solid rgba(255,255,255,0.07)' }}>
            <div className="px-4 py-2.5 flex items-center justify-between"
              style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <p className="text-xs font-semibold text-white/55">{group.label}</p>
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  {['Ticker', 'Nom', 'Prix', 'Variation', 'Volatilité (ann.)', 'Volume'].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-[10px] text-white/25 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupPrices.map((ticker, i) => {
                  const d = prices[ticker];
                  const isTalan = ticker === 'TAL.PA';
                  return (
                    <motion.tr
                      key={ticker}
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.03 }}
                      style={{
                        background: isTalan ? 'rgba(0,212,255,0.04)' : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                      }}
                    >
                      <td className="px-4 py-2.5">
                        <span className={`font-mono text-[11px] px-2 py-0.5 rounded ${isTalan ? 'bg-cyan-500/15 text-cyan-300' : 'bg-white/5 text-white/55'}`}>
                          {ticker}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-white/65">
                        {TICKER_LABELS[ticker] ?? ticker}
                        {isTalan && <span className="ml-1.5 text-[9px] px-1.5 py-0.5 bg-cyan-500/15 text-cyan-400 rounded">TALAN</span>}
                      </td>
                      <td className="px-4 py-2.5 font-mono font-semibold text-white/80">
                        {d.price?.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                      </td>
                      <td className="px-4 py-2.5">
                        <ChangeChip change={d.change_pct ?? 0} />
                      </td>
                      <td className="px-4 py-2.5">
                        <VolatilityBar value={d.volatility_annualised_pct ?? 0} />
                      </td>
                      <td className="px-4 py-2.5 text-white/35 font-mono text-[10px]">
                        {d.volume?.toLocaleString('fr-FR')}
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

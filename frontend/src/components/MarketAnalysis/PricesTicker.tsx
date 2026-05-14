/**
 * PricesTicker — live price/volume/volatility table for tracked tickers.
 * Light readable version with pastel surfaces.
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
  MSFT: 'Microsoft',
  NVDA: 'NVIDIA',
  GOOGL: 'Google',
  META: 'Meta',
  AMD: 'AMD',
  SAP: 'SAP',
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
  if (abs < 0.01) {
    return (
      <span className="flex items-center gap-1 text-xs text-[var(--text-faint)]">
        <Minus size={11} /> 0.00%
      </span>
    );
  }
  const color = change >= 0 ? '#059669' : '#DC2626';
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
  const color = capped >= 40 ? '#DC2626' : capped >= 25 ? '#EA580C' : capped >= 15 ? '#D97706' : '#059669';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
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
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 rounded-2xl bg-[var(--border-subtle)] animate-pulse" />
        ))}
      </div>
    );
  }

  if (!prices || Object.keys(prices).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <BarChart2 size={40} className="text-[var(--text-faint)]" />
        <p className="text-[var(--text-secondary)] text-base font-semibold">Données de marché indisponibles</p>
        <p className="text-[var(--text-muted)] text-sm">yfinance requis · vérifiez la connexion</p>
        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-all"
          style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)', border: '1px solid var(--primary-muted)' }}
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          Actualiser
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-[var(--text-muted)]">Snapshot en temps réel · {Object.keys(prices).length} tickers</p>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-all"
          style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
          Actualiser
        </button>
      </div>

      {TICKER_GROUPS.map((group) => {
        const groupPrices = group.tickers.filter((t) => prices[t]);
        if (!groupPrices.length) return null;
        return (
          <div key={group.label} className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
            <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-subtle)' }}>
              <p className="text-sm font-semibold text-[var(--text-secondary)]">{group.label}</p>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Ticker', 'Nom', 'Prix', 'Variation', 'Volatilité (ann.)', 'Volume'].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-[11px] text-[var(--text-faint)] font-semibold uppercase tracking-wide">{h}</th>
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
                        background: isTalan ? 'var(--primary-subtle)' : i % 2 === 0 ? 'transparent' : 'var(--bg-base)',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}
                    >
                      <td className="px-4 py-2.5">
                        <span className={`font-mono text-[11px] px-2 py-0.5 rounded-full ${isTalan ? 'bg-cyan-100 text-cyan-800' : 'bg-slate-100 text-slate-600'}`}>
                          {ticker}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">
                        {TICKER_LABELS[ticker] ?? ticker}
                        {isTalan && <span className="ml-1.5 text-[9px] px-1.5 py-0.5 bg-cyan-100 text-cyan-800 rounded-full">TALAN</span>}
                      </td>
                      <td className="px-4 py-2.5 font-mono font-semibold text-[var(--text-primary)]">
                        {d.price?.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                      </td>
                      <td className="px-4 py-2.5">
                        <ChangeChip change={d.change_pct ?? 0} />
                      </td>
                      <td className="px-4 py-2.5">
                        <VolatilityBar value={d.volatility_annualised_pct ?? 0} />
                      </td>
                      <td className="px-4 py-2.5 text-[var(--text-faint)] font-mono text-[10px]">
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

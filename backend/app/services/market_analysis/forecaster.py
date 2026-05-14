"""
LSTM Forecaster — prédit l'impact Talan à 7j et 30j.

Entrée  : série temporelle des scores GNN stockés dans market_gnn_scores
Sortie  : {"forecast_7d": float, "forecast_30d": float, "confidence": float,
           "trend": "up"|"down"|"stable", "history": [...]}

Architecture LSTM :
  Input  : séquence de longueur SEQ_LEN (fenêtre glissante)
  LSTM   : hidden=64, layers=2, dropout=0.2
  Linear : 64 → 2  (prédictions 7j et 30j simultanément)
  Tanh   : output ∈ [-1, +1]

Fallback : si torch absent ou données insuffisantes → moyenne mobile + tendance.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SEQ_LEN    = 20     # nombre de points passés utilisés pour prédire
HIDDEN_DIM = 64
NUM_LAYERS = 2
DROPOUT    = 0.2
MODEL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "lstm_forecaster.pt"

try:
    import torch
    import torch.nn as nn
    _TORCH = True
except ImportError:
    _TORCH = False


# ── Model ─────────────────────────────────────────────────────────────────────

if _TORCH:
    class _LSTMForecaster(nn.Module):
        """2-layer LSTM → prédiction impact 7j et 30j."""

        def __init__(self, input_dim: int = 3, hidden: int = HIDDEN_DIM,
                     num_layers: int = NUM_LAYERS, dropout: float = DROPOUT):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True,
            )
            self.dropout = nn.Dropout(dropout)
            self.head    = nn.Sequential(
                nn.Linear(hidden, 32),
                nn.ReLU(),
                nn.Linear(32, 2),   # [forecast_7d, forecast_30d]
                nn.Tanh(),
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # x: [batch, seq_len, input_dim]
            out, _ = self.lstm(x)
            last   = out[:, -1, :]          # last hidden state
            return self.head(self.dropout(last))   # [batch, 2]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_gnn_series(hours: int = 720) -> list[dict]:
    """
    Pull GNN scores from PostgreSQL ordered by time.
    Returns list of dicts: {recorded_at, talan_impact, systemic_risk, hidden_risks_count}
    """
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    since  = datetime.utcnow() - timedelta(hours=hours)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT recorded_at, talan_impact, systemic_risk, hidden_risks_count
            FROM market_gnn_scores
            WHERE recorded_at >= :since
            ORDER BY recorded_at ASC
        """), {"since": since}).fetchall()

    return [
        {
            "recorded_at":        r[0].isoformat() if r[0] else "",
            "talan_impact":       float(r[1] or 0),
            "systemic_risk":      float(r[2] or 0),
            "hidden_risks_count": int(r[3] or 0),
        }
        for r in rows
    ]


def _build_sequences(series: list[dict], seq_len: int = SEQ_LEN):
    """
    Build (X, y) pairs for LSTM training from a time series.
    X shape: [N, seq_len, 3]   features = [talan_impact, systemic_risk, hidden_count_norm]
    y shape: [N, 2]            targets  = [impact_7d_ahead, impact_30d_ahead]

    30-min cycle → 7j = 336 steps, 30j = 1440 steps.
    We use shorter horizons when data is limited:
      horizon_7d  = min(336, len/4)
      horizon_30d = min(1440, len/2)
    """
    n = len(series)
    if n < seq_len + 2:
        return None, None

    impacts = np.array([s["talan_impact"]       for s in series], dtype=np.float32)
    risks   = np.array([s["systemic_risk"]       for s in series], dtype=np.float32)
    hidden  = np.array([s["hidden_risks_count"]  for s in series], dtype=np.float32)

    # Normalise hidden count to [0, 1]
    mx = hidden.max()
    if mx > 0:
        hidden /= mx

    h7  = min(336,  max(1, n // 4))
    h30 = min(1440, max(1, n // 2))

    X_list, y_list = [], []
    for i in range(seq_len, n - h30):
        x_seq = np.stack([impacts[i-seq_len:i],
                          risks[i-seq_len:i],
                          hidden[i-seq_len:i]], axis=1)   # [seq_len, 3]
        y_7d  = impacts[min(i + h7,  n - 1)]
        y_30d = impacts[min(i + h30, n - 1)]
        X_list.append(x_seq)
        y_list.append([y_7d, y_30d])

    if not X_list:
        return None, None

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


# ── Training ──────────────────────────────────────────────────────────────────

def train_forecaster(
    series: list[dict] | None = None,
    epochs: int = 80,
    lr: float = 1e-3,
    seq_len: int = SEQ_LEN,
    seed: int = 42,
) -> dict:
    """
    Train LSTM forecaster on the GNN time series.
    Returns {"mae_7d", "mae_30d", "epochs", "samples"}.
    Falls back to moving-average if torch absent or data insufficient.
    """
    if series is None:
        series = load_gnn_series(hours=8760)   # last year

    if len(series) < seq_len + 5:
        logger.warning("Insufficient data (%d points) — forecaster will use moving average",
                       len(series))
        return {"mae_7d": None, "mae_30d": None, "samples": len(series), "mode": "fallback"}

    if not _TORCH:
        logger.warning("torch absent — forecaster uses moving average")
        return {"mae_7d": None, "mae_30d": None, "samples": len(series), "mode": "fallback"}

    import torch
    torch.manual_seed(seed)

    X, y = _build_sequences(series, seq_len)
    if X is None or len(X) < 4:
        return {"mae_7d": None, "mae_30d": None, "samples": len(series), "mode": "fallback"}

    # 80/20 split
    split = max(1, int(len(X) * 0.8))
    X_train, X_val = torch.tensor(X[:split]), torch.tensor(X[split:])
    y_train, y_val = torch.tensor(y[:split]), torch.tensor(y[split:])

    model     = _LSTMForecaster()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    criterion = nn.MSELoss()

    t0 = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        pred = model(X_train)
        loss = criterion(pred, y_train)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step(loss)

        if epoch % 20 == 0 or epoch == 1:
            model.eval()
            with torch.no_grad():
                val_loss = criterion(model(X_val), y_val).item() if len(X_val) > 0 else 0
            logger.info("  Forecaster epoch %d/%d  train=%.4f  val=%.4f  (%.1fs)",
                        epoch, epochs, loss.item(), val_loss, time.time() - t0)

    # MAE on val
    model.eval()
    with torch.no_grad():
        if len(X_val) > 0:
            preds_val = model(X_val).numpy()
            mae_7d  = float(np.abs(preds_val[:, 0] - y_val.numpy()[:, 0]).mean())
            mae_30d = float(np.abs(preds_val[:, 1] - y_val.numpy()[:, 1]).mean())
        else:
            mae_7d = mae_30d = 0.0

    torch.save(model.state_dict(), MODEL_PATH)
    logger.info("LSTM forecaster saved → %s  (MAE 7d=%.4f, 30d=%.4f)", MODEL_PATH, mae_7d, mae_30d)

    return {"mae_7d": round(mae_7d, 4), "mae_30d": round(mae_30d, 4),
            "samples": len(X), "epochs": epochs, "mode": "lstm"}


# ── Inference ─────────────────────────────────────────────────────────────────

def _moving_average_forecast(series: list[dict]) -> dict:
    """Simple fallback: weighted moving average + linear trend."""
    impacts = [s["talan_impact"] for s in series[-20:]]
    if not impacts:
        return {"forecast_7d": 0.0, "forecast_30d": 0.0,
                "confidence": 0.3, "trend": "stable", "mode": "fallback"}

    # Weighted mean (recent = higher weight)
    weights  = np.linspace(0.5, 1.0, len(impacts))
    wmean    = float(np.average(impacts, weights=weights))
    # Trend: slope of last N points
    if len(impacts) >= 3:
        slope = float(np.polyfit(range(len(impacts)), impacts, 1)[0])
    else:
        slope = 0.0

    trend_str = "up" if slope > 0.005 else ("down" if slope < -0.005 else "stable")
    f7d  = float(np.clip(wmean + slope * 336,  -1, 1))
    f30d = float(np.clip(wmean + slope * 1440, -1, 1))
    return {"forecast_7d": round(f7d, 4), "forecast_30d": round(f30d, 4),
            "confidence": 0.4, "trend": trend_str, "mode": "moving_average"}


def forecast(series: list[dict] | None = None) -> dict:
    """
    Run impact forecast.
    Returns {forecast_7d, forecast_30d, confidence, trend, history, mode}.
    """
    if series is None:
        series = load_gnn_series(hours=720)   # last 30 days

    history = [
        {"recorded_at": s["recorded_at"], "talan_impact": s["talan_impact"]}
        for s in series[-50:]
    ]

    if len(series) < SEQ_LEN + 2:
        result = _moving_average_forecast(series)
        result["history"] = history
        return result

    if not _TORCH or not MODEL_PATH.exists():
        result = _moving_average_forecast(series)
        result["history"] = history
        return result

    try:
        import torch
        model = _LSTMForecaster()
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()

        impacts = np.array([s["talan_impact"]       for s in series], dtype=np.float32)
        risks   = np.array([s["systemic_risk"]       for s in series], dtype=np.float32)
        hidden  = np.array([s["hidden_risks_count"]  for s in series], dtype=np.float32)
        mx = hidden.max()
        if mx > 0:
            hidden /= mx

        seq = np.stack([impacts[-SEQ_LEN:],
                        risks[-SEQ_LEN:],
                        hidden[-SEQ_LEN:]], axis=1)   # [SEQ_LEN, 3]
        x_t = torch.tensor(seq, dtype=torch.float32).unsqueeze(0)   # [1, SEQ_LEN, 3]

        with torch.no_grad():
            out = model(x_t).squeeze().numpy()   # [2]

        f7d, f30d = float(out[0]), float(out[1])

        # Trend from last 10 points
        recent = impacts[-10:]
        slope  = float(np.polyfit(range(len(recent)), recent, 1)[0]) if len(recent) >= 2 else 0.0
        trend  = "up" if slope > 0.005 else ("down" if slope < -0.005 else "stable")

        # Confidence based on data quantity and recency
        confidence = min(0.9, 0.4 + len(series) / 200)

        return {
            "forecast_7d":  round(f7d,  4),
            "forecast_30d": round(f30d, 4),
            "confidence":   round(confidence, 2),
            "trend":        trend,
            "history":      history,
            "mode":         "lstm",
        }
    except Exception as e:
        logger.warning("LSTM forecast failed (%s) — using moving average", e)
        result = _moving_average_forecast(series)
        result["history"] = history
        return result

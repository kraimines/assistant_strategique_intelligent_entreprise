"""Quick forward-pass sanity check — run before training."""
import sys, warnings
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

import torch
from app.services.market_analysis.world_model import WorldModel
from app.services.market_analysis.gnn_predictor import GraphBuilder, HeteroTemporalGNN

print("1. Loading KG snapshot...")
wm = WorldModel()
snap = wm.get_snapshot("Talan", hops=2)
wm.close()
print(f"   {len(snap['nodes'])} nodes, {len(snap['edges'])} edges")

print("2. Building HeteroData...")
gb = GraphBuilder()
data = gb.build_from_kg_snapshot(snap)
print(f"   Node types: {data.node_types}")
print(f"   Edge types: {data.edge_types}")
for nt in data.node_types:
    print(f"   {nt}: {data[nt].x.shape}  NaN={torch.isnan(data[nt].x).any().item()}")

print("3. Forward pass (random weights)...")
model = HeteroTemporalGNN()
model.train()
out = model(data)

impact = out["impact"]
risk   = out["risk"]
print(f"   impact shape : {impact.shape}")
print(f"   impact NaN?  : {torch.isnan(impact).any().item()}")
print(f"   impact range : [{impact.min().item():.4f}, {impact.max().item():.4f}]")
print(f"   risk         : {risk.item():.4f}  NaN={torch.isnan(risk).any().item()}")

if torch.isnan(impact).any():
    print("\n[FAIL] NaN still present — check encode() nan_to_num patches")
    sys.exit(1)
else:
    print("\n[OK] No NaN — safe to run train_gnn_predictor.py")

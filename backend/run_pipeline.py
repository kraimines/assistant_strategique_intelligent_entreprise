"""Lance un cycle du pipeline Market Analysis avec progression visible."""
import sys
import os
import logging
import time

sys.path.insert(0, os.path.dirname(__file__))

# Affiche tous les logs INFO en temps réel
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Réduit le bruit des libs tierces
for noisy in ["sentence_transformers", "tensorflow", "tf_keras",
              "httpx", "httpcore", "hpack", "neo4j"]:
    logging.getLogger(noisy).setLevel(logging.WARNING)

from app.services.market_analysis.orchestrator import MarketAnalysisPipeline

cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 1
print(f"\n{'='*55}")
print(f"  Market Analysis Pipeline — {cycles} cycle(s)")
print(f"{'='*55}\n")

for i in range(cycles):
    t0 = time.time()
    print(f"── Cycle {i+1}/{cycles} ─────────────────────────────────")
    r = MarketAnalysisPipeline().run()
    elapsed = time.time() - t0
    print(f"\n  ✓ Cycle {i+1} terminé en {elapsed:.0f}s")
    print(f"    Articles KG   : +{r['kg_nodes_added']} nœuds")
    print(f"    GNN ran       : {r['gnn_ran']}")
    print(f"    Errors        : {r['errors'] or 'aucune'}\n")

print("Pipeline terminé.")

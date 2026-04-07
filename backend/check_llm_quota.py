"""Vérification rapide du quota et des métriques LLM Groq.

Usage:
    cd backend
    python check_llm_quota.py
"""
from __future__ import annotations

import sys
import time

from dotenv import load_dotenv
load_dotenv(".env")
sys.path.insert(0, ".")

from groq import Groq
from app.core.config import settings

client = Groq(api_key=settings.groq_api_key)

print("=" * 60)
print("  MÉTRIQUES LLM — GROQ")
print("=" * 60)
print(f"  Modèle actif : {settings.groq_model}")
print()

# ── 1. Test de connectivité + latence ─────────────────────────
print("[1] Test de connectivité et latence...")
t0 = time.perf_counter()
try:
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": "Réponds uniquement: OK"}],
        max_tokens=5,
    )
    latency = (time.perf_counter() - t0) * 1000
    print(f"    ✓ Connecté — latence : {latency:.0f} ms")

    # Lire les headers de quota depuis la réponse
    usage = resp.usage
    print(f"    Tokens utilisés sur ce test : {usage.total_tokens}")
except Exception as e:
    latency = (time.perf_counter() - t0) * 1000
    print(f"    ✗ Erreur ({latency:.0f} ms) : {e}")

# ── 2. Limites du modèle ──────────────────────────────────────
print()
print("[2] Limites connues du modèle sur Groq (free tier) :")

LIMITS = {
    "llama-3.3-70b-versatile": {"TPM": 12_000, "RPM": 30, "TPD": 100_000},
    "qwen/qwen3-32b":           {"TPM": 6_000,  "RPM": 30, "TPD": 100_000},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"TPM": 30_000, "RPM": 30, "TPD": 500_000},
    "moonshotai/kimi-k2-instruct": {"TPM": 10_000, "RPM": 30, "TPD": "?"},
}

limits = LIMITS.get(settings.groq_model, {"TPM": "?", "RPM": "?", "TPD": "?"})
print(f"    TPM (tokens/minute) : {limits['TPM']:,}" if isinstance(limits['TPM'], int) else f"    TPM : {limits['TPM']}")
print(f"    RPM (requêtes/min)  : {limits['RPM']}")
print(f"    TPD (tokens/jour)   : {limits['TPD']:,}" if isinstance(limits['TPD'], int) else f"    TPD : {limits['TPD']}")

# ── 3. Estimation capacité pour ce projet ────────────────────
print()
print("[3] Estimation de capacité pour ce projet :")
TOKENS_PER_QUESTION = 2000  # estimation basée sur les tests

if isinstance(limits['TPD'], int):
    questions_per_day = limits['TPD'] // TOKENS_PER_QUESTION
    print(f"    ~{TOKENS_PER_QUESTION} tokens/question (prompt + outil + réponse)")
    print(f"    → Capacité estimée : {questions_per_day} questions/jour")

if isinstance(limits['TPM'], int):
    questions_per_minute = limits['TPM'] // TOKENS_PER_QUESTION
    wait_between = 60 // max(questions_per_minute, 1)
    print(f"    → Max {questions_per_minute} questions/minute")
    if wait_between > 1:
        print(f"    → Attente recommandée entre questions : {wait_between}s")

# ── 4. Test tool calling ──────────────────────────────────────
print()
print("[4] Test tool calling (appel d'outil simulé)...")
t0 = time.perf_counter()
try:
    tools = [{
        "type": "function",
        "function": {
            "name": "get_data",
            "description": "Récupère des données",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }]
    resp2 = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": "Appelle get_data avec query='test'"}],
        tools=tools,
        max_tokens=100,
    )
    latency2 = (time.perf_counter() - t0) * 1000
    msg = resp2.choices[0].message
    if msg.tool_calls:
        print(f"    ✓ Tool calling OK — {msg.tool_calls[0].function.name}() — {latency2:.0f} ms")
    else:
        print(f"    ⚠ Pas d'appel d'outil généré (réponse texte) — {latency2:.0f} ms")
        print(f"      Réponse : {msg.content[:80] if msg.content else 'vide'}")
except Exception as e:
    latency2 = (time.perf_counter() - t0) * 1000
    print(f"    ✗ Erreur tool calling ({latency2:.0f} ms) : {str(e)[:120]}")

print()
print("=" * 60)
print("  RÉSUMÉ")
print("=" * 60)
print(f"  Modèle     : {settings.groq_model}")
print(f"  Statut     : {'✓ Opérationnel' if latency < 10000 else '✗ Lent ou hors ligne'}")
print(f"  Latence    : {latency:.0f} ms (connexion simple)")
print()

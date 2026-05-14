"""Vérification rapide du quota et des métriques LLM (Groq ou Gemini).

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

from app.core.config import settings

PROVIDER = settings.llm_provider.lower()

print("=" * 60)
print(f"  MÉTRIQUES LLM — {PROVIDER.upper()}")
print("=" * 60)

# ── GROQ ──────────────────────────────────────────────────────────────────────
if PROVIDER == "groq":
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    model = settings.groq_model
    print(f"  Modèle actif : {model}")
    print()

    # 1. Connectivité + latence
    print("[1] Test de connectivité et latence...")
    t0 = time.perf_counter()
    latency = 99999
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Réponds uniquement: OK"}],
            max_tokens=5,
        )
        latency = (time.perf_counter() - t0) * 1000
        print(f"    ✓ Connecté — latence : {latency:.0f} ms")
        print(f"    Tokens utilisés sur ce test : {resp.usage.total_tokens}")
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        print(f"    ✗ Erreur ({latency:.0f} ms) : {e}")

    # 2. Limites
    print()
    print("[2] Limites connues du modèle sur Groq (free tier) :")
    LIMITS = {
        "llama-3.3-70b-versatile":                    {"TPM": 12_000, "RPM": 30, "TPD": 100_000},
        "qwen/qwen3-32b":                              {"TPM": 6_000,  "RPM": 30, "TPD": 100_000},
        "meta-llama/llama-4-scout-17b-16e-instruct":  {"TPM": 30_000, "RPM": 30, "TPD": 500_000},
        "moonshotai/kimi-k2-instruct":                 {"TPM": 10_000, "RPM": 30, "TPD": "?"},
    }
    limits = LIMITS.get(model, {"TPM": "?", "RPM": "?", "TPD": "?"})
    print(f"    TPM : {limits['TPM']:,}" if isinstance(limits['TPM'], int) else f"    TPM : {limits['TPM']}")
    print(f"    RPM : {limits['RPM']}")
    print(f"    TPD : {limits['TPD']:,}" if isinstance(limits['TPD'], int) else f"    TPD : {limits['TPD']}")

    # 3. Estimation
    print()
    print("[3] Estimation de capacité pour ce projet :")
    TOKENS_PER_QUESTION = 2000
    if isinstance(limits['TPD'], int):
        print(f"    ~{TOKENS_PER_QUESTION} tokens/question")
        print(f"    → {limits['TPD'] // TOKENS_PER_QUESTION} questions/jour")
    if isinstance(limits['TPM'], int):
        qpm = limits['TPM'] // TOKENS_PER_QUESTION
        print(f"    → Max {qpm} questions/minute")
        wait = 60 // max(qpm, 1)
        if wait > 1:
            print(f"    → Attente recommandée : {wait}s entre questions")

    # 4. Tool calling
    print()
    print("[4] Test tool calling...")
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
            model=model,
            messages=[{"role": "user", "content": "Appelle get_data avec query='test'"}],
            tools=tools,
            max_tokens=100,
        )
        latency2 = (time.perf_counter() - t0) * 1000
        msg = resp2.choices[0].message
        if msg.tool_calls:
            print(f"    ✓ Tool calling OK — {msg.tool_calls[0].function.name}() — {latency2:.0f} ms")
        else:
            print(f"    ⚠ Pas d'appel d'outil ({latency2:.0f} ms) : {(msg.content or '')[:80]}")
    except Exception as e:
        latency2 = (time.perf_counter() - t0) * 1000
        print(f"    ✗ Erreur tool calling ({latency2:.0f} ms) : {str(e)[:120]}")

    print()
    print("=" * 60)
    print("  RÉSUMÉ")
    print("=" * 60)
    print(f"  Modèle     : {model}")
    print(f"  Statut     : {'✓ Opérationnel' if latency < 10000 else '✗ Lent ou hors ligne'}")
    print(f"  Latence    : {latency:.0f} ms")

# ── GEMINI ────────────────────────────────────────────────────────────────────
elif PROVIDER == "gemini":
    import google.generativeai as genai
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool

    model = settings.gemini_model
    print(f"  Modèle actif : {model}")
    print()

    genai.configure(api_key=settings.google_api_key)

    # 1. Connectivité + latence
    print("[1] Test de connectivité et latence...")
    t0 = time.perf_counter()
    latency = 99999
    try:
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=0.1,
            max_output_tokens=10,
            streaming=False,
            convert_system_message_to_human=True,
        )
        resp = llm.invoke([HumanMessage(content="Réponds uniquement: OK")])
        latency = (time.perf_counter() - t0) * 1000
        print(f"    ✓ Connecté — latence : {latency:.0f} ms")
        print(f"    Réponse : {resp.content[:50]}")
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        print(f"    ✗ Erreur ({latency:.0f} ms) : {e}")

    # 2. Limites Gemini (free tier Google AI Studio)
    print()
    print("[2] Limites connues sur Google AI Studio (free tier) :")
    GEMINI_LIMITS = {
        "gemini-2.5-flash": {"RPM": 10,  "TPM": 250_000, "RPD": 500},
        "gemini-2.0-flash": {"RPM": 15,  "TPM": 1_000_000, "RPD": 1500},
        "gemini-1.5-flash": {"RPM": 15,  "TPM": 1_000_000, "RPD": 1500},
        "gemini-1.5-pro":   {"RPM": 2,   "TPM": 32_000,   "RPD": 50},
    }
    lim = GEMINI_LIMITS.get(model, {"RPM": "?", "TPM": "?", "RPD": "?"})
    print(f"    RPM (requêtes/min)  : {lim['RPM']}")
    print(f"    TPM (tokens/min)    : {lim['TPM']:,}" if isinstance(lim['TPM'], int) else f"    TPM : {lim['TPM']}")
    print(f"    RPD (requêtes/jour) : {lim['RPD']:,}" if isinstance(lim['RPD'], int) else f"    RPD : {lim['RPD']}")

    # 3. Estimation
    print()
    print("[3] Estimation de capacité pour ce projet :")
    TOKENS_PER_QUESTION = 2000
    if isinstance(lim['TPM'], int):
        qpm = lim['TPM'] // TOKENS_PER_QUESTION
        print(f"    ~{TOKENS_PER_QUESTION} tokens/question")
        print(f"    → Max {qpm} questions/minute (limite TPM)")
    if isinstance(lim['RPD'], int):
        print(f"    → {lim['RPD']} questions/jour max (limite RPD)")

    # 4. Tool calling via LangChain
    print()
    print("[4] Test tool calling (LangChain bind_tools)...")
    t0 = time.perf_counter()
    try:
        @tool
        def get_data(query: str) -> str:
            """Récupère des données selon une requête."""
            return f"données pour: {query}"

        llm2 = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=0.1,
            max_output_tokens=100,
            streaming=False,
            convert_system_message_to_human=True,
        )
        llm_with_tools = llm2.bind_tools([get_data])
        resp2 = llm_with_tools.invoke([HumanMessage(content="Appelle get_data avec query='test'")])
        latency2 = (time.perf_counter() - t0) * 1000
        if resp2.tool_calls:
            tc = resp2.tool_calls[0]
            print(f"    ✓ Tool calling OK — {tc['name']}({tc['args']}) — {latency2:.0f} ms")
        else:
            print(f"    ⚠ Pas d'appel d'outil ({latency2:.0f} ms) : {str(resp2.content)[:80]}")
    except Exception as e:
        latency2 = (time.perf_counter() - t0) * 1000
        print(f"    ✗ Erreur tool calling ({latency2:.0f} ms) : {str(e)[:120]}")

    # 5. JSON mode
    print()
    print("[5] Test JSON mode...")
    t0 = time.perf_counter()
    try:
        json_llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=0.0,
            max_output_tokens=100,
            streaming=False,
            convert_system_message_to_human=True,
            response_mime_type="application/json",
        )
        resp3 = json_llm.invoke([HumanMessage(content='Retourne exactement ce JSON: {"status": "ok"}')])
        latency3 = (time.perf_counter() - t0) * 1000
        print(f"    ✓ JSON mode OK — {latency3:.0f} ms")
        print(f"    Réponse : {resp3.content[:80]}")
    except Exception as e:
        latency3 = (time.perf_counter() - t0) * 1000
        print(f"    ✗ Erreur JSON mode ({latency3:.0f} ms) : {str(e)[:120]}")

    print()
    print("=" * 60)
    print("  RÉSUMÉ")
    print("=" * 60)
    print(f"  Modèle     : {model}")
    print(f"  Statut     : {'✓ Opérationnel' if latency < 10000 else '✗ Lent ou hors ligne'}")
    print(f"  Latence    : {latency:.0f} ms")

else:
    print(f"  Provider '{PROVIDER}' non supporté par ce script.")
    print("  Providers supportés : groq, gemini")

print()

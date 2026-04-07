"""CLI interactif pour tester les agents en terminal.

Lancement :
    cd backend
    python chat_cli.py

Commandes spéciales :
    quit / exit  — quitter
    role         — changer de rôle
    clear        — nouvelle conversation (réinitialise l'historique)
"""

from __future__ import annotations

import sys
import os
import uuid
import json
import textwrap

# ── Env setup ─────────────────────────────────────────────────────────────────
# Charger le .env avant tout import de l'application
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Ajouter le dossier backend au path si nécessaire
sys.path.insert(0, os.path.dirname(__file__))

# ── Imports app ───────────────────────────────────────────────────────────────
from app.agents.graph import graph
from app.agents.state import initial_state


# ── Constants ─────────────────────────────────────────────────────────────────

COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "cyan":    "\033[36m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "red":     "\033[31m",
    "magenta": "\033[35m",
    "blue":    "\033[34m",
    "grey":    "\033[90m",
}

DOMAIN_COLORS = {
    "hr":    "green",
    "crm":   "cyan",
    "erp":   "blue",
    "rag":   "magenta",
    "multi": "yellow",
}

VALID_ROLES = ["employee", "manager", "admin"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def c(color: str, text: str) -> str:
    """Wrap text with ANSI color codes."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def print_separator(char: str = "─", width: int = 70) -> None:
    print(c("grey", char * width))


def choose_role() -> str:
    print()
    print(c("bold", "Choisissez votre rôle :"))
    for i, role in enumerate(VALID_ROLES, 1):
        print(f"  {c('cyan', str(i))}. {role}")
    while True:
        choice = input(c("cyan", "Rôle (1/2/3) ou nom > ")).strip().lower()
        if choice in VALID_ROLES:
            return choice
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(VALID_ROLES):
                return VALID_ROLES[idx]
        except ValueError:
            pass
        print(c("red", f"  Choix invalide. Entrez 1, 2, 3 ou {VALID_ROLES}"))


def format_tool_results(tool_results: dict | None) -> str:
    if not tool_results:
        return c("grey", "  (aucun outil appelé)")
    lines = []
    for tool_name, result in tool_results.items():
        if isinstance(result, list):
            summary = f"{len(result)} enregistrement(s)"
        elif isinstance(result, dict):
            if "error" in result:
                summary = c("red", f"ERREUR: {result['error']}")
            else:
                keys = list(result.keys())[:4]
                summary = "{" + ", ".join(keys) + ("..." if len(result) > 4 else "") + "}"
        else:
            summary = str(result)[:80]
        lines.append(f"  {c('yellow', '●')} {c('bold', tool_name)}: {summary}")
    return "\n".join(lines)


def wrap_response(text: str, width: int = 70, indent: int = 2) -> str:
    """Wrap long lines in the final response."""
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
        else:
            wrapped.extend(textwrap.wrap(line, width=width, subsequent_indent=" " * indent))
    return "\n".join(wrapped)


# ── Main CLI loop ─────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(c("bold", "═" * 70))
    print(c("bold", "  Assistant Stratégique Intelligent — CLI Interactif"))
    print(c("bold", "═" * 70))
    print(c("grey", "  Tapez votre question en français. Commandes : quit, role, clear"))
    print()

    role = choose_role()
    conversation_id = str(uuid.uuid4())
    turn = 0

    print()
    print(c("green", f"  Connecté en tant que : {c('bold', role)}"))
    print(c("grey", f"  Session ID : {conversation_id[:8]}..."))
    print_separator()

    while True:
        print()
        user_input = input(c("bold", f"[{role}] > ")).strip()

        if not user_input:
            continue

        # ── Special commands ───────────────────────────────────────────────
        if user_input.lower() in ("quit", "exit", "q"):
            print(c("grey", "\n  Au revoir !"))
            break

        if user_input.lower() == "role":
            role = choose_role()
            conversation_id = str(uuid.uuid4())
            turn = 0
            print(c("green", f"\n  Nouveau rôle : {c('bold', role)} — session réinitialisée"))
            print_separator()
            continue

        if user_input.lower() == "clear":
            conversation_id = str(uuid.uuid4())
            turn = 0
            print(c("grey", "\n  Conversation réinitialisée."))
            print_separator()
            continue

        # ── Run pipeline ───────────────────────────────────────────────────
        turn += 1
        print(c("grey", "  Traitement en cours..."))

        try:
            state = initial_state(
                user_id=f"CLI_USER_{role.upper()}",
                user_role=role,
                message=user_input,
            )

            config = {"configurable": {"thread_id": conversation_id}}
            result = graph.invoke(state, config=config)

        except Exception as exc:
            print(c("red", f"\n  ERREUR pipeline : {exc}"))
            continue

        # ── Display results ────────────────────────────────────────────────
        print()
        print_separator()

        # Domain routing
        domain = result.get("detected_domain") or "?"
        confidence = result.get("domain_confidence")
        domain_color = DOMAIN_COLORS.get(domain, "cyan")
        domain_label = c(domain_color, f"[{domain.upper()}]")
        conf_label = f" {c('grey', f'(confiance: {confidence:.0%})')}" if confidence else ""
        print(f"  {c('bold', 'Domaine détecté')} : {domain_label}{conf_label}")

        # Error message
        error = result.get("error_message")
        if error:
            print(f"  {c('red', 'Erreur')} : {error}")

        # Tool results
        tool_results = result.get("tool_results")
        if tool_results:
            print(f"\n  {c('bold', 'Outils appelés')} :")
            print(format_tool_results(tool_results))

        # RAG context summary
        rag_context = result.get("rag_context")
        if rag_context:
            rag_preview = rag_context[:120].replace("\n", " ")
            print(f"\n  {c('magenta', 'Contexte RAG')} : {c('grey', rag_preview + '...')}")

        # Final response
        final_response = result.get("final_response")
        print()
        print_separator("─")
        if final_response:
            print(c("bold", "  Réponse :"))
            print()
            for line in wrap_response(final_response).split("\n"):
                print(f"  {line}")
        else:
            # Fallback: last AI message
            for msg in reversed(result.get("messages", [])):
                if hasattr(msg, "content") and msg.content:
                    content = str(msg.content)
                    if content != user_input:
                        print(c("bold", "  Réponse :"))
                        print()
                        for line in wrap_response(content).split("\n"):
                            print(f"  {line}")
                        break

        print_separator()


if __name__ == "__main__":
    main()

"""
Script de test de l'orchestrateur — deux modes :

  MODE MOCK (défaut, sans API) :
    python test_orchestrator_live.py
    Teste toute la logique de l'orchestrateur avec un LLM simulé.

  MODE LIVE (avec clé API Gemini) :
    python test_orchestrator_live.py --live
    Appelle vraiment Gemini — nécessite un quota disponible.
"""
import sys
import json
from unittest.mock import MagicMock, patch

# ── Couleurs terminal ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):     print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):   print(f"  {RED}✗{RESET} {msg}")
def info(msg):   print(f"  {BLUE}→{RESET} {msg}")
def warn(msg):   print(f"  {YELLOW}⚠{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{YELLOW}{'='*62}{RESET}\n{BOLD}{msg}{RESET}\n{'='*62}")

LIVE_MODE = "--live" in sys.argv

# ── Réponses simulées du LLM pour chaque cas de test ─────────────────────────
MOCK_RESPONSES = {
    1: {"domain": "hr",    "primary_domain": "hr",  "secondary_domain": None,  "confidence": 0.97, "requires_write": True,  "intent_summary": "Créer une demande de congé", "entities_detected": ["EMP0001"]},
    2: {"domain": "hr",    "primary_domain": "hr",  "secondary_domain": None,  "confidence": 0.95, "requires_write": False, "intent_summary": "Consulter les compétences",   "entities_detected": ["EMP0002"]},
    3: {"domain": "crm",   "primary_domain": "crm", "secondary_domain": None,  "confidence": 0.93, "requires_write": False, "intent_summary": "Historique revenus clients",  "entities_detected": []},
    4: {"domain": "erp",   "primary_domain": "erp", "secondary_domain": None,  "confidence": 0.94, "requires_write": False, "intent_summary": "Factures impayées client",    "entities_detected": ["CUS0022"]},
    5: {"domain": "rag",   "primary_domain": "rag", "secondary_domain": None,  "confidence": 0.91, "requires_write": False, "intent_summary": "Politique congé maladie",     "entities_detected": []},
    6: {"domain": "multi", "primary_domain": "hr",  "secondary_domain": "erp", "confidence": 0.88, "requires_write": False, "intent_summary": "Budget projet + membres équipe","entities_detected": ["PRJ0001"]},
    7: {"domain": "erp",   "primary_domain": "erp", "secondary_domain": None,  "confidence": 0.92, "requires_write": True,  "intent_summary": "Créer commande fournisseur",  "entities_detected": ["SUP001"]},
}

# ── Cas de test ───────────────────────────────────────────────────────────────
TEST_CASES = [
    {
        "id": 1,
        "description": "Demande de congé (écriture RH)",
        "message": "Crée une demande de congé annuel du 15 au 18 juillet 2025 pour EMP0001",
        "role": "employee",
        "expected_domain": "hr",
        "expected_write": True,
        "expected_error": False,
    },
    {
        "id": 2,
        "description": "Compétences employé (lecture RH)",
        "message": "Quelles sont les compétences de EMP0002 ?",
        "role": "employee",
        "expected_domain": "hr",
        "expected_write": False,
        "expected_error": False,
    },
    {
        "id": 3,
        "description": "CA clients (lecture CRM)",
        "message": "Quel est le CA de nos clients sur les 6 derniers mois ?",
        "role": "manager",
        "expected_domain": "crm",
        "expected_write": False,
        "expected_error": False,
    },
    {
        "id": 4,
        "description": "Factures impayées (lecture ERP)",
        "message": "Montre-moi toutes les factures impayées du client CUS0022",
        "role": "admin",
        "expected_domain": "erp",
        "expected_write": False,
        "expected_error": False,
    },
    {
        "id": 5,
        "description": "Politique congés (RAG documentaire)",
        "message": "Quelle est la politique de congés maladie dans l'entreprise ?",
        "role": "employee",
        "expected_domain": "rag",
        "expected_write": False,
        "expected_error": False,
    },
    {
        "id": 6,
        "description": "Budget projet + équipe (multi-domaine)",
        "message": "Quel est le budget du projet PRJ0001 et quels employés y travaillent ?",
        "role": "manager",
        "expected_domain": "multi",
        "expected_write": False,
        "expected_error": False,
    },
    {
        "id": 7,
        "description": "Permission refusée (employee tente ERP écriture)",
        "message": "Crée une commande fournisseur pour le fournisseur SUP001",
        "role": "employee",
        "expected_domain": "erp",
        "expected_write": True,
        "expected_error": True,
    },
]


def make_mock_llm(test_id: int):
    """Crée un LLM simulé qui retourne la réponse JSON prédéfinie pour ce test."""
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_RESPONSES[test_id])

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


def run_test(tc: dict, use_mock: bool) -> bool:
    """Exécute un cas de test. Retourne True si passé."""
    from app.agents.state import initial_state
    from app.agents.orchestrator import orchestrator_node

    state = initial_state(
        user_id="TEST001",
        user_role=tc["role"],
        message=tc["message"],
    )

    if use_mock:
        mock_llm = make_mock_llm(tc["id"])
        with patch("app.agents.orchestrator.get_json_llm", return_value=mock_llm):
            result = orchestrator_node(state)
    else:
        result = orchestrator_node(state)

    domain     = result.get("detected_domain")
    confidence = result.get("domain_confidence", 0.0)
    write      = result.get("requires_write", False)
    error      = result.get("error_message")
    secondary  = result.get("secondary_domain")

    info(f"Domaine détecté   : {BOLD}{domain}{RESET}")
    info(f"Confiance         : {BOLD}{confidence:.2f}{RESET}")
    info(f"Requires write    : {write}")
    if secondary:
        info(f"Domaine secondaire: {secondary}")
    if error:
        info(f"Erreur            : {RED}{error}{RESET}")

    test_ok = True

    # ── Vérif domaine ──────────────────────────────────────────────────────────
    domain_ok = (domain == tc["expected_domain"])
    if domain_ok:
        ok(f"Domaine correct ({domain})")
    else:
        fail(f"Domaine attendu={tc['expected_domain']}, obtenu={domain}")
        test_ok = False

    # ── Vérif confiance ────────────────────────────────────────────────────────
    if confidence >= 0.7:
        ok(f"Confiance OK ({confidence:.2f} ≥ 0.70)")
    else:
        fail(f"Confiance trop basse : {confidence:.2f} < 0.70")
        test_ok = False

    # ── Vérif requires_write ───────────────────────────────────────────────────
    if write == tc["expected_write"]:
        ok(f"requires_write correct ({write})")
    else:
        fail(f"requires_write attendu={tc['expected_write']}, obtenu={write}")
        test_ok = False

    # ── Vérif permission ───────────────────────────────────────────────────────
    if tc["expected_error"]:
        if error:
            ok("Permission refusée comme attendu")
        else:
            fail("Permission aurait dû être refusée mais aucune erreur")
            test_ok = False
    else:
        if error:
            fail(f"Erreur inattendue : {error}")
            test_ok = False

    return test_ok


def main():
    mode_label = "LIVE (Gemini API)" if LIVE_MODE else "MOCK (sans quota API)"
    header(f"TEST ORCHESTRATEUR — {mode_label}")

    # ── Import ────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[1/3] Import des modules...{RESET}")
    try:
        from app.agents.state import initial_state
        from app.agents.orchestrator import orchestrator_node, WRITE_OPERATIONS_ALLOWED
        ok("app.agents.state importé")
        ok("app.agents.orchestrator importé")
        ok(f"WRITE_OPERATIONS_ALLOWED = {WRITE_OPERATIONS_ALLOWED}")
    except Exception as e:
        fail(f"Import échoué : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ── Vérif config ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}[2/3] Vérification configuration...{RESET}")
    from app.core.config import settings
    provider = settings.llm_provider.lower()
    if provider == "groq":
        active_model = settings.groq_model
        active_key = settings.groq_api_key
        key_label = "GROQ_API_KEY"
    else:
        active_model = settings.gemini_model
        active_key = settings.google_api_key
        key_label = "GOOGLE_API_KEY"
    ok(f"Provider actif    : {provider}")
    ok(f"Modèle configuré  : {active_model}")
    if LIVE_MODE:
        if not active_key or active_key in ("your_groq_api_key_here", "your_gemini_key_here"):
            fail(f"{key_label} manquante dans backend/.env !")
            sys.exit(1)
        ok(f"Clé API : {active_key[:8]}...{active_key[-4:]}")
    else:
        warn("Mode MOCK — LLM simulé, aucun appel API réel")
        warn("Pour tester avec le vrai LLM : python test_orchestrator_live.py --live")

    # ── Tests ─────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[3/3] Exécution des {len(TEST_CASES)} tests...{RESET}")
    passed = 0
    failed_count = 0

    for tc in TEST_CASES:
        print(f"\n{BOLD}── Test {tc['id']} : {tc['description']}{RESET}")
        msg = tc['message']
        info(f"Message : \"{msg[:70]}\"" if len(msg) > 70 else f"Message : \"{msg}\"")
        info(f"Rôle    : {tc['role']}")
        try:
            result = run_test(tc, use_mock=not LIVE_MODE)
            if result:
                passed += 1
                print(f"  {GREEN}{BOLD}→ PASSÉ ✓{RESET}")
            else:
                failed_count += 1
                print(f"  {RED}{BOLD}→ ÉCHOUÉ ✗{RESET}")
        except Exception as e:
            fail(f"Exception : {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1
            print(f"  {RED}{BOLD}→ ÉCHOUÉ (exception) ✗{RESET}")

    # ── Bilan ─────────────────────────────────────────────────────────────────
    header(f"BILAN : {passed}/{len(TEST_CASES)} tests passés")
    if failed_count == 0:
        print(f"{GREEN}{BOLD}✓ Orchestrateur opérationnel !{RESET}\n")
        if not LIVE_MODE:
            print(f"{YELLOW}Note : tests en mode MOCK.")
            print(f"Pour valider avec le vrai LLM :{RESET}")
            print(f"  python test_orchestrator_live.py --live\n")
    else:
        print(f"{RED}{BOLD}✗ {failed_count} test(s) échoué(s){RESET}\n")


if __name__ == "__main__":
    main()

# Orbiads-GAM-A2A — Agents A2A pour Google Ad Manager (via OrbiAds)

Exemples **prêts à cloner et déployer** qui prouvent, de bout en bout : **créer un agent Google Ad
Manager, le brancher sur OrbiAds (MCP), le déployer dans l'Agent Platform de Google (Vertex Agent
Engine), le rendre découvrable en A2A, et composer des cas métier multi-agents — y compris le standard
d'achat AdCP.**

> Dépôt public d'accompagnement de la série d'articles **OrbiAds Academy « OrbiAds en A2A »**.
> MCP = agent ↔ outils. A2A (Agent2Agent) = agent ↔ agent.

## 👉 Le tutoriel
**[TUTORIAL.md](./TUTORIAL.md)** — tutoriel complet, concret, **générique** (placeholders, aucun ID réel) :
prérequis → projet/API → code de l'agent → connexion OAuth → déploiement Agent Engine → Agent Card /
registre → A2A (orchestrateur) → cas métier multi-agents → **AdCP natif** → what's next → teardown.

`agent-card.json` = modèle d'Agent Card A2A.

## Les 4 agents (progression)
| Dossier | Démontre | Partie |
|---|---|---|
| `gam_sentinel/` | 1 agent GAM A2A (instruction + MCP OrbiAds filtré), déployable Agent Engine | 2–5 |
| `orchestrator/` | A2A : `registry_search_agents` → délégation vers `gam_sentinel` | 6–7 |
| `gam_optimizer/` | Cas métier **3 agents async** : forecast ∥ format/CTR → synthèse | 8 |
| `adcp_gateway/` | **AdCP natif** : buy agent → `create_media_buy` → `deals(adcp_validate)` puis `deals(adcp_preview)` → DealSpec GAM, **read-only** | 8bis |

> Prompts en **anglais** ; chaque agent qui touche aux données fait un **NETWORK CHECK** (affiche le réseau
> actif, s'arrête si inattendu). Le **modèle est un paramètre** (`MODEL` dans `.env`) — mets celui qui
> convient à ton usage ; un gros JSON imbriqué (AdCP) peut nécessiter un modèle plus costaud que `flash`.

## Quickstart (local)
```bash
git clone https://github.com/OrbiAds/Orbiads-GAM-A2A.git
cd Orbiads-GAM-A2A
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) Configure chaque agent : copie .env.example -> .env dans le dossier de l'agent
cp gam_sentinel/.env.example gam_sentinel/.env       # idem pour les autres
# Renseigne MODEL + ORBIADS_MCP_TOKEN (jeton obtenu via `python get_token.py`)

# 2) Lance l'UI de dev ADK (les 4 agents)
adk web .                                            # http://127.0.0.1:8000

# ou sers l'agent GAM en A2A :
uvicorn gam_sentinel.agent:a2a_app --port 10000      # /.well-known/agent.json
```

Obtenir un jeton OrbiAds : `python get_token.py` (DCR + PKCE + consentement) écrit le token dans `.env`.
Voir la **Partie 3** du tutoriel.

> ⚠️ Reste sur un **réseau GAM de test** (jamais un réseau client réel). Le réseau actif est un état
> serveur : bascule via l'outil MCP `network(action='switch_network', ...)`. Les agents affichent le réseau
> actif et s'arrêtent s'il est inattendu (NETWORK CHECK).

## Sécurité
Les `.env` (jetons), les états `.adk/` et les captures brutes ne sont **pas** versionnés (cf `.gitignore`).
Seules les captures floutées (`captures/web/*.webp`) sont publiées. Licence **MIT**.

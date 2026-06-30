# Tutoriel complet — Agent GAM connecté à OrbiAds, déployé et orchestré en A2A

> **Générique** : remplace les placeholders `EN_MAJUSCULES`. Aucune valeur réelle codée en dur.
> Écrit « depuis zéro » : chaque étape, chaque piège rencontré (⚠️), chaque lien officiel.
>
> Placeholders : `PROJECT_ID`, `PROJECT_NUMBER`, `REGION` (ex. `us-central1`), `NETWORK_CODE` (réseau GAM
> de test), `CONNECTOR_NAME` (ex. `orbiads`), `AGENT_ENGINE_ID`, `CLIENT_ID`/`CLIENT_SECRET`.

## 📖 Documentation officielle (à garder ouverte)
- ADK (Agent Development Kit) : <https://adk.dev/> · tutoriel outils <https://adk.dev/tutorials/multi-tool-agent/>
- ADK + MCP : <https://adk.dev/tools-custom/mcp-tools/> · ADK auth : <https://adk.dev/tools-custom/authentication/>
- ADK A2A : <https://google.github.io/adk-docs/a2a/> · codelab A2A : <https://codelabs.developers.google.com/codelabs/currency-agent>
- Déploiement Agent Engine/Runtime : <https://adk.dev/deploy/agent-runtime/>
- Agent Identity (auth managée) : <https://adk.dev/integrations/agent-identity/> ·
  vue d'ensemble <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview>
- Connecteurs 3LO : <https://docs.cloud.google.com/iam/docs/manage-auth-providers> ·
  <https://docs.cloud.google.com/iam/docs/auth-with-3lo>
- Agent Registry : <https://docs.cloud.google.com/agent-registry/register-agents> ·
  enregistrer un agent A2A <https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent>
- Modèles Vertex : <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models>
- Protocole A2A : <https://a2a-protocol.org/latest/specification/> · OAuth DCR : RFC 7591 / PKCE : RFC 7636

---

## Partie 0 — Prérequis et installation

- Compte **OrbiAds** connecté à ton réseau GAM. Endpoint MCP : `https://orbiads.com/mcp`.
- `gcloud` installé + **mis à jour** :
  ```bash
  gcloud auth login
  gcloud components update        # ⚠️ requis : les commandes "agent-identity connectors" sont récentes
  gcloud components install alpha # ⚠️ sinon "Invalid choice: agent-identity"
  ```
- Python 3.11+ et un venv dédié :
  ```bash
  python -m venv .venv && .venv/Scripts/activate           # Windows ; sinon: source .venv/bin/activate
  pip install "google-adk[a2a,agent-identity]==2.3.0" "mcp==1.28.1" \
              "google-cloud-aiplatform[agent_engines]" "google-cloud-secret-manager" \
              uvicorn httpx python-dotenv
  pip install "opentelemetry-api==1.42.1" "opentelemetry-sdk==1.42.1"
  ```
  > ⚠️ **Frein vécu** : `google-cloud-aiplatform[agent_engines]` tire `opentelemetry 1.43` qui **casse**
  > ADK 2.3.0 (qui veut `<=1.42.1`). D'où le repin `==1.42.1` en dernier. Sans ça : conflit au déploiement.
  > ⚠️ `google-adk` **seul** ne suffit pas : il faut l'extra `[a2a,agent-identity]` **et** `mcp`.

---

## Partie 1 — Projet GCP, facturation, API

```bash
gcloud projects create PROJECT_ID --name="Agent A2A"
gcloud billing projects link PROJECT_ID --billing-account=TON_BILLING_ID
gcloud config set project PROJECT_ID
gcloud auth application-default set-quota-project PROJECT_ID

gcloud services enable \
  aiplatform.googleapis.com iamconnectors.googleapis.com secretmanager.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com
```
> ⚠️ **Frein vécu** : `billing projects link` → `Cloud billing quota exceeded` = ton compte de facturation
> a atteint son quota de **nombre de projets**. Solution : autre compte de facturation, ou réutiliser un
> projet existant déjà facturé.
> ⚠️ `aiplatform` = Vertex (modèle) **et** Agent Engine. `iamconnectors` = le connecteur OAuth. Active-les
> avant la Partie 3, sinon `SERVICE_DISABLED` (et compte ~1-2 min de propagation après activation).

---

## Partie 2 — Le code de l'agent GAM

Arborescence (chaque sous-dossier = un agent pour ADK) :
```
mon-agent/
  gam_sentinel/
    __init__.py
    agent.py
    .env
    requirements.txt
```

`gam_sentinel/__init__.py` :
```python
from . import agent      # ADK découvre root_agent ici
```

`gam_sentinel/agent.py` :
```python
import os
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.a2a.utils.agent_to_a2a import to_a2a

load_dotenv()
MCP_URL = os.environ.get("ORBIADS_MCP_URL", "https://orbiads.com/mcp")
TOKEN   = os.environ.get("ORBIADS_MCP_TOKEN", "")
MODEL   = os.environ.get("MODEL", "gemini-2.5-flash")
PORT    = int(os.environ.get("A2A_PORT", "10000"))

orbiads = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=MCP_URL,
        headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {},
    ),
    # « borner les skills » : 2-3 outils, pas 50 (précision + sobriété de contexte)
    tool_filter=["check_credentials", "select_gam_network", "inventory"],
)

root_agent = LlmAgent(
    name="gam_inventory_sentinel",
    model=MODEL,
    instruction=(
        "Tu es une sentinelle d'inventaire GAM en LECTURE SEULE. "
        "1) check_credentials (confirme connexion + réseau). 2) inspecte l'inventaire (ad units). "
        "3) signale les unités à faible disponibilité ou non conformes. Tu n'écris JAMAIS."
    ),
    tools=[orbiads],
)

# Expose l'agent en A2A : sert /.well-known/agent.json + reçoit les tâches
a2a_app = to_a2a(root_agent, port=PORT)
```

`gam_sentinel/requirements.txt` :
```
google-adk[a2a,agent-identity]==2.3.0
mcp==1.28.1
google-cloud-aiplatform[agent_engines]
google-cloud-secret-manager
```

`gam_sentinel/.env` (config ; l'auth = Partie 3) :
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=PROJECT_ID
GOOGLE_CLOUD_LOCATION=REGION
MODEL=gemini-2.5-flash
ORBIADS_MCP_URL=https://orbiads.com/mcp
A2A_PORT=10000
```
> ⚠️ **Frein majeur** : ADK charge le `.env` **du dossier de l'agent** (`gam_sentinel/.env`), **pas** tes
> variables d'environnement shell. C'est CE fichier qui fixe le modèle ET l'auth. Symptôme si l'auth y est
> mauvaise : le MCP renvoie `401`, les outils ne se chargent pas, et le modèle **« narre » l'appel d'outil**
> (`Unexpected tool call: print(default_api.check_credentials())`) au lieu de l'exécuter.
> ⚠️ **Modèle** : vérifie que `MODEL` est disponible via Vertex dans ton `PROJECT_ID`/`REGION`
> (<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models>). Sinon `Publisher model ... not
> found`. (`gemini-2.5-flash` est largement disponible.)

---

## Partie 3 — Récupérer ET injecter ton token de connexion OrbiAds (en détail)

OrbiAds est un **serveur OAuth standard** (cf RFC 7591 DCR + PKCE RFC 7636). Discovery :
`GET https://orbiads.com/mcp/.well-known/oauth-authorization-server` → expose :
- `authorization_endpoint` = `https://orbiads.com/mcp/authorize`
- `token_endpoint` = `https://orbiads.com/mcp/token`
- `registration_endpoint` = `https://orbiads.com/mcp/register` (DCR)
- `grant_types` = `authorization_code`, `refresh_token` · PKCE = `S256` · (pas de `client_credentials`).

Il y a **deux jetons** : un **access token** (≈ 1 h, sert d'en-tête `Authorization: Bearer`) et un
**refresh token** (longue durée, sert à réémettre des access tokens). **⚠️ Le refresh token TOURNE** à
chaque usage : l'ancien est invalidé, le `/token` renvoie un nouveau refresh — il faut le re-sauver.

### 3.1 — Récupérer les tokens (flux OAuth complet)
> 💡 **Le plus simple (self-service, sans CLI)** : OrbiAds → **Paramètres → Agents → « Connecter un agent »**
> provisionne un client OAuth (client_id + secret) en un clic — voir Partie 5bis. Le script `get_token.py`
> ci-dessous est l'**équivalent CLI** (utile pour obtenir directement un *bearer* de test).

Le script `get_token.py` (fourni dans le lab) fait, dans l'ordre :
1. **DCR** — enregistre un client OAuth : `POST /mcp/register` avec un `redirect_uri` local
   (`http://localhost:8765/callback`) → renvoie un `client_id`.
2. **PKCE** — génère un `code_verifier` + `code_challenge` (S256).
3. **Consentement** — ouvre `…/mcp/authorize?...` dans ton navigateur ; tu te connectes avec ton compte
   Google et tu approuves (c'est le « 3-legged » : au nom de l'utilisateur).
4. **Callback** — un mini serveur local capte le `code` redirigé.
5. **Échange** — `POST /mcp/token` (`grant_type=authorization_code` + `code_verifier`) → **access_token**
   + **refresh_token**.

```bash
python get_token.py        # ouvre le navigateur ; à la fin, écrit dans .env :
#   ORBIADS_MCP_CLIENT_ID, ORBIADS_MCP_TOKEN (access), ORBIADS_MCP_REFRESH_TOKEN
```
> Cœur du script (à comprendre) :
> ```python
> # 1) DCR
> reg = POST("/mcp/register", {"client_name":"...", "redirect_uris":[REDIRECT],
>            "grant_types":["authorization_code","refresh_token"], "token_endpoint_auth_method":"none"})
> client_id = reg["client_id"]
> # 2) PKCE
> verifier  = secrets.token_urlsafe(64)
> challenge = b64url(sha256(verifier))
> # 3) ouvrir /mcp/authorize?response_type=code&client_id=...&redirect_uri=...&scope=openid ...
> #    &code_challenge=challenge&code_challenge_method=S256
> # 4) capter ?code=... sur http://localhost:8765/callback
> # 5) échange
> tok = POST_form("/mcp/token", {"grant_type":"authorization_code","code":code,
>                 "redirect_uri":REDIRECT,"client_id":client_id,"code_verifier":verifier})
> access, refresh = tok["access_token"], tok["refresh_token"]
> ```

### 3.2 — Injecter le token dans l'agent
ADK lit le `.env` de l'agent. **Donc le token va dans `gam_sentinel/.env`** :
```
ORBIADS_MCP_CLIENT_ID=CLIENT_ID
ORBIADS_MCP_TOKEN=COLLE_L_ACCESS_TOKEN
ORBIADS_MCP_REFRESH_TOKEN=COLLE_LE_REFRESH_TOKEN
```
Le code (`agent.py`, Partie 2) lit `ORBIADS_MCP_TOKEN` et le met dans `Authorization: Bearer ...`.
> ⚠️ Mets le **bon** `.env` (celui du dossier d'agent que tu lances). Un `.env` en mode connecteur ou avec
> un token périmé → `401` → outils non chargés (cf Partie 2).

### 3.3 — Gérer l'expiration (réémettre un access token)
L'access token expire (~1 h). Pour le réémettre **sans navigateur**, via le refresh token :
```bash
curl -s -X POST https://orbiads.com/mcp/token \
  -d "grant_type=refresh_token" -d "refresh_token=TON_REFRESH" -d "client_id=TON_CLIENT_ID"
# → nouveau access_token (+ un nouveau refresh_token : REMPLACE l'ancien dans ton .env !)
```
> ⚠️ **Frein vécu** : si tu re-mintes mais ne **sauvegardes pas** le nouveau refresh token, le suivant
> échoue (`invalid_grant: refresh token does not exist`). Toujours réécrire le refresh tourné.

### 3.4 — Pour un agent MANAGÉ (Agent Engine) : ne plus gérer de token du tout
Voir **Partie 5bis** (Agent Identity Auth Manager) : Google gère consentement + coffre + rotation +
injection. Ton agent n'a alors **aucun** token ni code d'auth.

---

## Partie 4 — Lancer et vérifier en local (runner canonique)

> ⚠️ **Frein vécu** : ne teste **pas** en envoyant du JSON-RPC brut à l'endpoint A2A — ça court-circuite la
> boucle d'exécution d'outils du runner. Utilise `adk run` / `adk web` (cf <https://adk.dev/tutorials/multi-tool-agent/>).

```bash
adk run gam_sentinel          # REPL ; pose une question, l'agent appelle check_credentials + inventory
# ou l'UI dev (recommandée pour les captures) :
adk web .                      # → http://127.0.0.1:8000
```
> ⚠️ **Sécurité données** : avant toute requête, assure-toi d'être sur un **réseau GAM de test** (jamais un
> réseau client réel). Le réseau actif est un **état serveur** OrbiAds. Pour le changer, appelle l'**outil
> MCP** `network` (via ton client MCP — Claude Desktop, ou un petit script `mcp` avec ton bearer) :
> `network(action="switch_network", params={"network_code": "NETWORK_CODE"})`. Ce n'est PAS une commande
> shell ni un sous-commande `adk`.

---

## Partie 5 — Déployer dans l'Agent Platform (Agent Engine)

Réf : <https://adk.dev/deploy/agent-runtime/>
> ⚠️ **Auth de l'agent déployé** : un agent managé ne peut pas faire le consentement navigateur. Pour qu'il
> s'authentifie, mets en place **la Partie 5bis (connecteur Agent Identity) AVANT/avec ce déploiement** et
> référence-le dans `agent.py` (`auth_scheme`). Un agent déployé sans cette auth se connectera à OrbiAds
> mais ne pourra pas récupérer de credential (« Failed to retrieve credential »).
```bash
python -m google.adk.cli deploy agent_engine \
  --project=PROJECT_ID --region=REGION --display_name="GAM Inventory Sentinel" gam_sentinel
# → renvoie AGENT_ENGINE_ID + URL playground
```
> ⚠️ **Freins vécus** : `No module named 'vertexai'` → installer `google-cloud-aiplatform[agent_engines]` ;
> conflit opentelemetry → repin `==1.42.1` (Partie 0). Pour mettre à jour le même agent (pas de doublon) :
> ajoute `--agent_engine_id=AGENT_ENGINE_ID`.

Vérifier : console **Vertex AI → Agents → Agent Engines**.

## Partie 5bis — Auth managée propre : le connecteur Agent Identity (3LO)

Réf : <https://adk.dev/integrations/agent-identity/> · <https://docs.cloud.google.com/iam/docs/auth-with-3lo>

1. **Obtenir un client confidentiel chez OrbiAds.** Le `redirect_uri` DOIT être le **callback du connecteur** :
   `https://iamconnectorcredentials.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME/oauthcallback`

   **Voie recommandée (self-service, sans CLI)** : OrbiAds → **Paramètres → Agents → « Connecter un agent »** →
   *Nom* + colle ce **Redirect URI** (le champ affiche déjà le gabarit) → **Créer** → copie le **`CLIENT_ID`**
   + le **`CLIENT_SECRET`** (affiché une seule fois). *(Validé live : un client créé ainsi crée bien un
   connecteur ENABLED et se connecte à OrbiAds → GAM.)*

   **Voie CLI alternative (DCR)** :
   ```bash
   CB="https://iamconnectorcredentials.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME/oauthcallback"
   curl -s -X POST https://orbiads.com/mcp/register -H "Content-Type: application/json" -d "{
     \"client_name\":\"agent-identity\",\"redirect_uris\":[\"$CB\"],
     \"grant_types\":[\"authorization_code\",\"refresh_token\"],\"response_types\":[\"code\"],
     \"token_endpoint_auth_method\":\"client_secret_post\"}"
   # → CLIENT_ID + CLIENT_SECRET
   ```
   > ⚠️ Le `redirect_uri` du client **doit** correspondre au callback du connecteur, sinon le consentement
   > échoue au runtime (redirect mismatch). Crée donc le client AVEC ce callback (pas un localhost).
2. **Créer le connecteur** :
   ```bash
   gcloud alpha agent-identity connectors create CONNECTOR_NAME --project=PROJECT_ID --location=REGION \
     --three-legged-oauth-authorization-url="https://orbiads.com/mcp/authorize" \
     --three-legged-oauth-token-url="https://orbiads.com/mcp/token" \
     --three-legged-oauth-client-id="CLIENT_ID" --three-legged-oauth-client-secret="CLIENT_SECRET" \
     --allowed-scopes="openid,https://www.googleapis.com/auth/userinfo.email"
   ```
3. **Référencer dans l'agent** (au lieu du bearer) :
   ```python
   from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
   from google.adk.auth.credential_manager import CredentialManager
   scheme = GcpAuthProviderScheme(
       name="projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME",
       scopes=["openid","https://www.googleapis.com/auth/userinfo.email"])
   CredentialManager.register_auth_provider(GcpAuthProvider())   # ⚠️ classmethod (PAS AuthProviderRegistry())
   orbiads = MCPToolset(connection_params=StreamableHTTPConnectionParams(url="https://orbiads.com/mcp"),
                        tool_filter=["check_credentials","inventory"], auth_scheme=scheme)
   ```
> ⚠️ **Freins vécus** : (a) `agent-identity connectors` absent → `gcloud components update`. (b) API
> `iamconnectors` à activer (+ propagation). (c) Au runtime : `No auth provider registered for ...
> gcpAuthProviderScheme` si tu fais `AuthProviderRegistry().register(...)` (registre vide) au lieu de la
> **classmethod** `CredentialManager.register_auth_provider(...)`. (d) Le consentement reste **humain une
> fois** ; le playground Agent Engine ne l'orchestre PAS (il appelle avec une identité technique) → le
> consentement se fait dans Agentspace/Gemini Enterprise. Le `client_secret` est requis par le connecteur
> mais **non vérifié par OrbiAds** (sécurité = PKCE + redirect_uri).

---

## Partie 6 — L'Agent Card dans l'Agent Registry (découvrabilité)

Réf : <https://docs.cloud.google.com/agent-registry/register-agents> ·
<https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent>

> ⚠️ **Frein vécu** : `adk deploy agent_engine` seul enregistre l'agent en **`CUSTOM`** (API query), **sans
> Agent Card** (`has card: False`) → non appelable en A2A. Il faut une **Agent Card** (`/.well-known/agent.json`).

- **Auto** : déployer/servir un agent qui expose l'Agent Card → le registre la scanne et l'indexe.
- **Console** : Gemini Enterprise → ton app → **Agents → Add → Custom agent via A2A** → coller l'Agent Card
  JSON (modèle : [agent-card.json](./agent-card.json), `url` = endpoint A2A) + l'OAuth du connecteur.

Servir l'agent en A2A localement (la carte est déjà construite par `to_a2a`, Partie 2) :
```bash
uvicorn gam_sentinel.agent:a2a_app --port 10000     # carte : http://127.0.0.1:10000/.well-known/agent.json
```
> ⚠️ **Frein vécu** : la carte contient son propre `url` (avec un port). Sers l'agent **sur le même port**
> que celui inscrit dans la carte, sinon l'appelant A2A → `503: All connection attempts failed`.

---

## Partie 7 — A2A : un orchestrateur qui DÉCOUVRE puis DÉLÈGUE

`orchestrator/agent.py` :
```python
import os
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools import FunctionTool
from google.adk.integrations.agent_registry import AgentRegistry

reg = AgentRegistry(project_id=os.environ["GOOGLE_CLOUD_PROJECT"],
                    location=os.environ["GOOGLE_CLOUD_LOCATION"])

def registry_search_agents(need: str) -> list[dict]:
    """Cherche les agents A2A disponibles dans l'Agent Registry."""
    res = reg.list_agents()
    return [{"name": a.get("displayName"), "id": a.get("name")} for a in res.get("agents", [])]

gam_remote = RemoteA2aAgent(
    name="gam_inventory_sentinel",
    description="Agent GAM (inventaire, lecture seule) joint en A2A.",
    agent_card=os.environ.get("GAM_A2A_CARD_URL", "http://127.0.0.1:10000/.well-known/agent.json"),
)

root_agent = LlmAgent(
    name="orchestrator", model=os.environ.get("MODEL", "gemini-2.5-flash"),
    instruction=("Pour toute demande GAM : 1) registry_search_agents pour trouver l'agent spécialisé, "
                 "2) délègue au sous-agent gam_inventory_sentinel, 3) restitue sa réponse."),
    tools=[FunctionTool(registry_search_agents)],
    sub_agents=[gam_remote],
)
```
`orchestrator/.env` : mêmes `GOOGLE_*` + `MODEL` + `GAM_A2A_CARD_URL=http://127.0.0.1:10000/.well-known/agent.json`.
Lancer `gam_sentinel` (Partie 6) **puis** `adk web .` → app `orchestrator` : trace
`registry_search_agents` → `transfer_to_agent` → réponse de l'agent GAM.

---

## Partie 8 — Cas métier : plan d'optimisation multi-agents (async)

`gam_optimizer/agent.py` — 2 spécialistes **en parallèle** + synthèse :
```python
import os
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

TOKEN=os.environ.get("ORBIADS_MCP_TOKEN",""); MODEL=os.environ.get("MODEL","gemini-2.5-flash")
def mcp(f): return MCPToolset(connection_params=StreamableHTTPConnectionParams(
    url="https://orbiads.com/mcp", headers={"Authorization":f"Bearer {TOKEN}"} if TOKEN else {}), tool_filter=f)

forecast_agent = LlmAgent(name="forecast_agent", model=MODEL, output_key="forecast_result",
  instruction="Estime le POTENTIEL de diffusion (lecture seule). check_credentials puis reporting "
              "(get_traffic_data / get_standalone_forecast). Donne un volume + 1 phrase.",
  tools=[mcp(["check_credentials","reporting","inventory"])])
format_agent = LlmAgent(name="format_agent", model=MODEL, output_key="format_result",
  instruction="Recommande les FORMATS pour le CTR (lecture seule). check_credentials puis "
              "reporting.run_custom_report (CTR par taille, LAST_30_DAYS) + inventory (tailles obsolètes). "
              "Donne top formats + tailles à abandonner.",
  tools=[mcp(["check_credentials","reporting","inventory","formats"])])

specialists = ParallelAgent(name="specialists", sub_agents=[forecast_agent, format_agent])
synthesis = LlmAgent(name="synthesis_agent", model=MODEL,
  instruction=("Plan d'optimisation à partir de :\n— Potentiel : {forecast_result?}\n"
               "— Formats : {format_result?}\nDonne : potentiel · formats à privilégier · tailles à abandonner."))
root_agent = SequentialAgent(name="gam_optimizer", sub_agents=[specialists, synthesis])
```
> ⚠️ **Frein vécu** : templating d'instruction `{var}` **strict** → `KeyError` si la clé d'un sous-agent
> n'est pas encore en state. Utilise `{var?}` (optionnel) pour `forecast_result`/`format_result`.

> ⚠️ **Frein prompt — l'agent invente des outils / des chiffres.** Avec une instruction vague (« via
> inventory, repère les tailles obsolètes »), le LLM **hallucine** un nom d'outil (`listing_obsolete_ad_unit_sizes`),
> se passe la réponse en paramètre, puis se contredit ; ou il sort des **placeholders** (`[CTR_DATA_HERE]`)
> et un **chiffre rond inventé** (5 000 000). Correctifs dans le prompt : (a) **nommer l'action exacte**
> (`inventory` action `list_ad_unit_sizes`, **sans** paramètre) ; (b) dire que le **jugement d'obsolescence
> est le travail de l'agent** (comparer `fullDisplayString` à une liste connue), jamais un paramètre d'outil ;
> (c) traiter `width=0`/`fullDisplayString` vide comme **responsive/fluid**, pas « obsolète » ; (d) **interdire
> les placeholders** `[…]` et les nombres inventés — soit la valeur réelle de l'outil, soit l'absence dite en clair.

> ⚠️ **Frein GAM Reporting** : la dimension `AD_REQUEST_SIZES` est **incompatible** avec les métriques
> `IMPRESSIONS`/`CLICKS` dans le report historique par défaut (rejet côté GAM). Et `run_custom_report`
> **refuse `dateRange`** posé tel quel dans `params` (erreur de validation). Conséquence concrète : sur un
> **réseau de test sans trafic**, le `format_agent` ne peut pas calculer de CTR — il doit le **dire**, pas
> inventer. C'est le comportement attendu après correction du prompt.

`adk web .` → app `gam_optimizer` : graphe parallèle (forecast ∥ format) → `synthesis_agent`.

> 🔒 **Prompts en anglais + garde-fou réseau.** Les instructions des agents sont en **anglais** (portée
> internationale) et chaque agent qui touche aux données fait un **NETWORK CHECK** : il lit `networkCode` /
> `networkDisplayName` via `check_credentials`, les affiche, et **s'arrête si `autoBound=true` ou si le
> réseau n'est pas celui attendu** — pour ne jamais lire un réseau de production par erreur.

---

## Partie 8bis — AdCP natif (un agent qui parle le standard d'achat)

OrbiAds expose déjà une surface **AdCP** (Ad Context Protocol) — **n'invente pas un brief JSON**, utilise
les outils natifs. Attention : ils passent par des **tools parents** (pattern parent>action), pas par des
noms standalone :

| Capacité | Appel MCP réel | Type |
|---|---|---|
| Discovery côté vente (produits au format AdCP) | `products` → action discovery `get_products_adcp` | read-only |
| Valider un `create_media_buy` vs schéma v3 | `deals(action='adcp_validate', params={request})` | read-only |
| Traduire une requête AdCP en `DealSpec` (sans exécuter) | `deals(action='adcp_preview', params={request})` | read-only |
| Exécuter de bout en bout | `deals(action='adcp_create', params={request, confirmation_token})` | **write** |

**Le cas A2A** (dossier `adcp_gateway/`) : un **agent acheteur** envoie une requête AdCP `create_media_buy`
→ l'agent OrbiAds la **valide** (`adcp_validate`) puis la **preview** en deal GAM (`adcp_preview`),
**100 % read-only** (`adcp_create` interdit par le prompt). Requête d'exemple :
`adcp_gateway/sample_adcp_request.json`. Capture : `captures/web/06-adcp-gateway-preview.webp`.

> ℹ️ **Le modèle est un choix de l'utilisateur — ce tuto valide l'APPROCHE, pas un modèle.** Observé au
> passage : un gros JSON AdCP imbriqué peut faire « coder » l'appel à gemini-2.5-**flash**
> (`MALFORMED_FUNCTION_CALL` : `print(default_api.deals(...))`). Pour des arguments très imbriqués, un
> modèle plus costaud (ex. gemini-2.5-pro) fiabilise le run. Mets le modèle qui convient à TON usage via
> `MODEL` dans le `.env` — rien dans le code n'y est lié.

> ⚠️ **Frein vécu** : `tool_filter` filtre par **nom de tool**, pas par action. Comme les actions AdCP
> read-only vivent sous le parent `deals` (qui a aussi `adcp_create` en write), on ne peut pas les isoler
> au niveau tool. On s'appuie sur (a) le prompt et (b) le **confirmation_token** d'OrbiAds (`adcp_create`
> refuse de s'exécuter sans token issu d'un preview). Pour un read-only **dur**, il faudrait un scope
> serveur read-only.

> ⚠️ **Frein vécu** : `adcp_preview` fait un **vrai lookup d'annonceur GAM**. Sans annonceur correspondant
> (`brand.domain`), il renvoie l'erreur **actionnable** `ADCP_ADVERTISER_UNRESOLVED` → fournis
> `ext.orbiads_advertiser_company_id` (l'ID GAM `Company`). C'est le comportement attendu, pas un bug.

---

## Partie 9 — Nettoyage, logging & confidentialité (teardown)

> ⚠️ **Le logging cloud PERSISTE.** Un agent déployé sur Agent Engine laisse deux traces persistantes
> **dans le projet GCP de déploiement** : (a) **Cloud Logging** (rétention par défaut **30 jours**, bucket
> `_Default`, configurable 1–3650 j) ; (b) les **sessions Agent Engine managées** (`create_session` …) qui
> gardent l'**historique de conversation jusqu'à `delete_session`**. Tout ce que l'agent trace — y compris
> les **données GAM renvoyées par les outils** — peut y figurer. Pour un déploiement réel (et cohérent avec
> le principe **zéro-stockage** d'OrbiAds) : réduire la rétention des logs, limiter le tracing verbeux, et
> **purger les sessions** régulièrement.

```bash
# agent(s) Agent Engine
python -c "import vertexai; from vertexai import agent_engines; vertexai.init(project='PROJECT_ID',location='REGION'); [a.delete(force=True) for a in agent_engines.list()]"
# connecteur
gcloud alpha agent-identity connectors delete CONNECTOR_NAME --project=PROJECT_ID --location=REGION --quiet
# secrets éventuels + projet dédié
gcloud projects delete PROJECT_ID --quiet
```
Et **stoppe les serveurs locaux** (`uvicorn`, `adk web`). **Repasse le réseau actif sur un réseau test.**

---

## Partie 10 — What's next (pour aller plus loin)

Le lab prouve l'**approche** (connexion, A2A, multi-agents, AdCP) sur des cas read-only. Pistes pour un
usage réel — chacune mérite potentiellement son propre article :

- **Monitoring des réponses (eval / quality)** — capturer chaque tour agent (entrée, outils appelés,
  sortie) et le **scorer**. Deux niveaux : (a) *online* — log structuré des `tool_calls` + verdict
  (succès / erreur actionnable / hallucination évitée) via Cloud Logging + une métrique log-based ;
  (b) *offline* — un jeu de prompts de référence rejoué (`adk eval`) pour détecter les régressions
  (ex. le retour au mode « code » de flash, ou un AdCP qui repasse `adcp_create`). Garde-fou clé déjà en
  place : le **NETWORK CHECK** et l'interdiction d'écrire — à *asserter* dans l'eval.
- **Choix & coût du modèle** — `MODEL` est un paramètre utilisateur ; mesurer latence/coût/fiabilité
  function-calling par modèle sur les mêmes prompts (flash vs pro) et documenter le compromis.
- **Auth de prod** — passer du token statique au **connecteur Agent Identity** (3LO managé) pour les
  agents déployés ; chaque utilisateur autorise via le connecteur (cf l'erreur `Failed to retrieve
  credential` = comportement attendu tant que l'utilisateur n'a pas consenti).
- **AdCP bout-en-bout** — du `adcp_preview` (read-only) au `adcp_create` (write) avec le
  `confirmation_token`, derrière un garde-fou humain — un article « exécuter un media buy via AdCP ».
- **Rétention & confidentialité** — politique de rétention des logs + purge des sessions (Partie 9),
  alignée zéro-stockage.

---

## 📸 Captures illustratives (illustrer l'important, pas chaque étape)

Une capture ne sert qu'aux **moments non évidents / preuves** — pas à chaque commande (le reste = blocs de
code/terminal, déjà dans le texte). Les 6 captures qui comptent :

Les captures **web-ready** (webp, ≤ 1600 px) sont dans [`captures/web/`](./captures/web/).

⚠️ **L'Academy est multilingue** (pages Svelte, texte bilingue FR/EN via `$locale`). Donc les images
sont **neutres linguistiquement** (floutage des identifiants + badge/flèche uniquement, **aucun texte
gravé**) ; la **légende vit dans la page** via le ternaire `$locale`. Les paires FR/EN prêtes à coller
sont dans [`captures/captions.md`](./captures/captions.md).

| # | Illustre (partie) | Écran | Fichier `captures/web/` |
|---|---|---|---|
| 1 | Agent **déployé dans l'Agent Platform** (P5) | Console Vertex AI → Agent Runtime (agent listé, framework `google-adk`) | `01-agent-deploye-agent-platform.webp` — IDs floutés |
| 2b | **La vraie Agent Card A2A** (P2/P6) | Navigateur : `http://127.0.0.1:10000/.well-known/agent.json` (carte servie par `to_a2a`) | `02b-agent-card-a2a.webp` |
| 3 | **Consentement OAuth** (P3) | Écran Google « Sélectionnez un compte » + « signing back in » pendant `get_token.py` | `03-consentement-oauth-compte.webp` + `03b-consentement-oauth-autoriser.webp` — emails floutés |
| 4 | **Communication A2A inter-agents** (P7) | `adk web` : `registry_search_agents` → `transfer_to_agent` → réponse de l'agent GAM | `04-a2a-communication-inter-agents.webp` |
| 5 | **Multi-agents async** (P8) | `adk web` : `specialists` (forecast ∥ format) → `synthesis_agent` | `05-multi-agents-async.webp` |
| 5bis-a | **Page « Connecter un agent »** (P5bis) | OrbiAds → Paramètres → Compte → Agents : formulaire self-service | `5bis-connecter-un-agent.webp` — ⚠️ overlay FR à neutraliser |
| 5bis-b | **Client agent créé** (P5bis) | OrbiAds : `client_id` + secret one-time affichés une fois | `5bis-agent-cree.webp` — ⚠️ overlay FR à neutraliser |

À refaire/compléter soi-même (non incluses, car spécifiques à ton compte) : `2a` la fiche Agent
**Registry** (`CUSTOM`), `6` les **MCP servers managés** Google. Floute toujours projet / n° projet /
code réseau / IDs d'ad units / emails avant publication.

- Captures **4 et 5** : à prendre nativement depuis `http://127.0.0.1:8000` (apps `orchestrator` et
  `gam_optimizer`) → enregistre-les dans `captures/`.
- Capture **2b / 3** : se prennent en lançant l'agent local (`uvicorn …:a2a_app --port 10000`) et
  `python get_token.py`.
- ⚠️ **Tes captures console montrent tes vrais identifiants** (projet, n° projet, code réseau, IDs d'ad
  units…). Pour **publier** : floute ces zones, ou refais les captures sur un projet/réseau de **démo**.
  Le tutoriel (texte) est déjà 100 % générique ; ce sont les images qu'il faut nettoyer.

## ✅ Checklist (ne rien oublier)
- [ ] `gcloud components update` + `install alpha`
- [ ] venv + `google-adk[a2a,agent-identity]` + `mcp` + `opentelemetry==1.42.1`
- [ ] Projet + facturation liée + 7 API activées (propagation)
- [ ] `gam_sentinel/.env` correct (modèle Vertex dispo, auth présente) — **c'est CE fichier que ADK lit**
- [ ] Token : `get_token.py` (DCR+PKCE+consentement) → access **et** refresh dans le `.env`
- [ ] Test via `adk run`/`adk web` (pas JSON-RPC brut) sur un **réseau test**
- [ ] Déploiement Agent Engine (vertexai installé, opentelemetry pinné)
- [ ] Connecteur 3LO (API iamconnectors, `CredentialManager.register_auth_provider`)
- [ ] Agent Card servie (carte = même port que le serveur) + enregistrée dans le registre
- [ ] Orchestrateur : `GAM_A2A_CARD_URL` correct + `gam_sentinel` lancé en A2A
- [ ] Multi-agents : `{var?}` optionnel dans la synthèse
- [ ] Teardown : agents + connecteur + projet + serveurs locaux + réseau test

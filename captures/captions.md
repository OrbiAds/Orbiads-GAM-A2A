# Légendes des captures — bilingues (à coller dans la page Academy)

Les images dans `web/` sont **neutres linguistiquement** (floutage + badge uniquement, aucun texte
gravé). La légende vit dans la page Svelte via le ternaire `$locale` — comme les autres articles
Academy (cf `gam-key-values-guide/+page.svelte`). Pattern :

```svelte
<figure>
  <enhanced:img src="/captures/web/01-agent-deploye-agent-platform.webp" alt={alt01} />
  <figcaption>{cap01}</figcaption>
</figure>
```

| Fichier `web/` | FR | EN |
|---|---|---|
| `01-agent-deploye-agent-platform.webp` | L'agent GAM déployé dans l'Agent Platform (Vertex AI Agent Runtime) — framework `google-adk`, région `us-central1`. | The GAM agent deployed to Agent Platform (Vertex AI Agent Runtime) — `google-adk` framework, `us-central1` region. |
| `02b-agent-card-a2a.webp` | L'Agent Card A2A (`/.well-known/agent.json`) : nom, description, skills, URL — ce que les autres agents découvrent pour dialoguer avec lui. | The A2A Agent Card (`/.well-known/agent.json`): name, description, skills, URL — what other agents discover in order to talk to it. |
| `04-a2a-communication-inter-agents.webp` | Communication A2A : l'orchestrateur **découvre** l'agent (`registry_search_agents`) puis lui **délègue** (`transfer_to_agent`) → réponse. Deux agents qui dialoguent. | A2A in action: the orchestrator **discovers** the agent (`registry_search_agents`) then **delegates** to it (`transfer_to_agent`) → reply. Two agents talking. |
| `05-multi-agents-async.webp` | Multi-agents asynchrone : deux spécialistes en parallèle (forecast ∥ format/CTR) → un agent de synthèse. Un livrable métier composé. | Async multi-agent: two specialists in parallel (forecast ∥ format/CTR) → a synthesis agent. A composed business deliverable. |
| `03-consentement-oauth-compte.webp` | Consentement OAuth : Google demande quel compte autorise l'application OrbiAds (scope `admanager`). C'est l'utilisateur qui autorise, pas l'agent. | OAuth consent: Google asks which account authorizes the OrbiAds app (`admanager` scope). The user grants access, not the agent. |
| `03b-consentement-oauth-autoriser.webp` | Écran « You're signing back in to OrbiAds » : l'utilisateur confirme et OrbiAds reçoit le jeton d'accès GAM. | "You're signing back in to OrbiAds" screen: the user confirms and OrbiAds receives the GAM access token. |
| `06-adcp-gateway-preview.webp` | AdCP natif : l'agent valide une requête `create_media_buy` (`deals(adcp_validate)`) puis la *preview* en deal GAM (`deals(adcp_preview)`) — read-only, rien n'est écrit. L'erreur actionnable (`ADCP_ADVERTISER_UNRESOLVED`) montre la traduction vers GAM en action. | Native AdCP: the agent validates a `create_media_buy` request (`deals(adcp_validate)`) then *previews* it as a GAM deal (`deals(adcp_preview)`) — read-only, nothing written. The actionable error (`ADCP_ADVERTISER_UNRESOLVED`) shows the GAM translation at work. |
| `5bis-connecter-un-agent.webp` | *(overlay FR à refaire neutre — voir note)* Page « Connecter un agent » : on saisit un nom et l'URL de redirection de l'agent. | *(FR overlay to redo neutral — see note)* "Connect an agent" page: enter a name and the agent's redirect URL. |
| `5bis-agent-cree.webp` | *(overlay FR à refaire neutre — voir note)* Le client est créé : `client_id` + secret affichés **une seule fois**, à copier immédiatement. | *(FR overlay to redo neutral — see note)* The client is created: `client_id` + secret shown **once only**, copy them immediately. |

> **Note 5bis** : `5bis-connecter-un-agent.webp` et `5bis-agent-cree.webp` portent encore des **overlays
> de texte en français** (flèches + explications gravées, demandés au départ). Pour le multilingue il faut
> soit (a) les régénérer avec des **flèches/numéros neutres** + la légende dans la page, soit (b) produire
> une **version par locale**. À trancher avant publication.

# Deploying the Copilot Studio Agent Quality Reporter

Two supported paths: a **one-click "Deploy to Azure" button** (uses prebuilt public images), and **`azd up`** (builds from source). Both land the same architecture on Azure Container Apps.

## Architecture

The deploy provisions, into a resource group of your choice:

- **PostgreSQL Flexible Server** (Burstable B1ms, 32 GB) + a database named `agentquality`.
- **Container Apps environment** with Log Analytics.
- **api** container app — external HTTPS ingress on port 8000; serves the React dashboard **and** the API, and runs database migrations on startup.
- **worker** container app — internal; runs the scheduled scan loop.

Both containers share the same secrets (database URL, Fernet key, session key, admin password) supplied as Container Apps secrets. Only an **admin password** is required at deploy time; the Postgres password and encryption keys are auto-generated.

## 1. One-click button

### For end users (deploying an existing published build)

1. Click **Deploy to Azure** in the [README](../README.md#deploy-to-azure-one-click).
2. Pick a subscription, resource group, and region.
3. Set a **dashboard admin password** (min 8 chars). Optionally expand **Entra SSO** and **Advanced**.
4. **Review + create**. Deployment takes ~5–8 minutes (Postgres is the slow part).
5. Open the **`dashboardUrl`** output, sign in with `admin` + your password, and configure the service principal in **Admin**.

### For maintainers (one-time, so the button works for everyone)

The button pulls **public** images from GitHub Container Registry (GHCR). Publish them once:

1. Push this repo to `https://github.com/loryanstrant/AgentQualityReporter` (branch `main`).
2. The **Publish container images** workflow (`.github/workflows/publish-images.yml`) builds and pushes `api` and `worker` on every push to `main` and every `v*` tag.
3. After the first successful run, open the repo's **Packages**, and for **both** `agentqualityreporter/api` and `agentqualityreporter/worker` set the visibility to **Public** (Package settings → Danger Zone → Change visibility). Azure Container Apps then pulls them anonymously.

The image namespace is `ghcr.io/loryanstrant/agentqualityreporter/{api,worker}`; the ARM template defaults to it and to the `latest` tag.

## 2. azd (build from source)

Prefer building from your own source? Infrastructure is defined in `/infra` (`main.bicep`, `resources.bicep`) and `azure.yaml`.

```powershell
azd env set POSTGRES_ADMIN_PASSWORD "<strong-password>"
azd env set FERNET_KEY "<fernet-key>"
azd env set SECRET_KEY "<random-secret>"
azd env set ADMIN_PASSWORD "<admin-password>"

azd up      # provision + build + deploy
azd down    # tear everything down
```

## After deployment

1. Open the `dashboardUrl` output and sign in (`admin` + the password you set).
2. Go to **Admin** → follow the setup wizard to create one Entra app registration and register it as an **application user** in each Power Platform environment you want to scan.
3. Enter the **Tenant ID**, **Client ID**, and **Client Secret**. Optionally add the **Azure OpenAI / Foundry** base URL, model, and key to enable the LLM instruction-quality judge.
4. **Add environment** → paste the Dataverse org URL → **Test** → **Scan now** (or **Scan all environments**).

The service principal needs the Dynamics CRM `user_impersonation` application permission and a security role that can read `bot`, `botcomponent`, and `solution` rows in each environment.

## Entra single sign-on (optional)

By default only the admin password protects the dashboard. To let licensed users view it with their Microsoft work account, enable **Entra SSO** at deploy time (it uses Azure Container Apps Easy Auth):

1. Register an app registration for sign-in (single-tenant is fine). Add a **Web** platform.
2. In the deploy form's **Entra SSO** step, tick **Enable Entra ID single sign-on** and paste the app's **client ID** and a **client secret**.
3. After deployment, copy the **`entraRedirectUriToRegister`** output (`https://<fqdn>/.auth/login/aad/callback`) and add it as a **Web redirect URI** on the app registration.
4. Users now sign in with Entra ID to view the dashboard; the **Admin** console remains password-protected.

## Updating a deployment

- **One-click:** re-run the **Publish container images** workflow (or push to `main`), then in the Azure portal restart the `api` and `worker` container apps to pull the new `latest` image — or redeploy the ARM template with a specific version tag (e.g. `v0.6.0`).
- **azd:** run `azd deploy` to rebuild and roll out from source.

Database migrations run automatically on `api` startup (`RUN_MIGRATIONS_ON_STARTUP=true`), so schema changes apply on the next revision with no manual step.

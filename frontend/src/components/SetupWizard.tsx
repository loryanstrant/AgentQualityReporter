import { useState, type ReactNode } from "react";

// Microsoft Graph PowerShell: creates the app registration, (optionally) adds
// Directory.Read.All + grants admin consent, creates a client secret, and prints
// the Tenant ID, Client ID, and secret. Permission GUIDs are resolved by name at
// runtime so nothing is hard-coded or can drift.
const ENTRA_SCRIPT = `# Microsoft Graph PowerShell. Requires Global Administrator (or Application
# Administrator + rights to grant admin consent).
Install-Module Microsoft.Graph -Scope CurrentUser -Force   # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
# Directory.Read.All is ONLY needed if you gate the dashboard by an Entra group.
# Dataverse read access is granted separately in Part B (application user).
$needed  = "Directory.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "Agent Quality Platform" -RequiredResourceAccess @{
  ResourceAppId  = "00000003-0000-0000-c000-000000000000"
  ResourceAccess = @($roles | ForEach-Object { @{ Id = $_.Id; Type = "Role" } })
}
$sp = New-MgServicePrincipal -AppId $app.AppId

# Grant admin consent for the application permission(s)
foreach ($r in $roles) {
  New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id \`
    -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $r.Id | Out-Null
}

$secret = Add-MgApplicationPassword -ApplicationId $app.Id \`
  -PasswordCredential @{ DisplayName = "aqp"; EndDateTime = (Get-Date).AddYears(1) }

Write-Host "Tenant ID:     $((Get-MgContext).TenantId)"
Write-Host "Client ID:     $($app.AppId)"
Write-Host "Client secret: $($secret.SecretText)"
# Next: run Part B to register this app as an application user per environment.`;

// One-shot PAC CLI command: creates the Entra app registration AND registers it
// as an application user in the target environment, then prints the IDs + secret.
const PAC_SCRIPT = `# Power Platform CLI (pac). Install: https://aka.ms/PowerPlatformCLI
# Run once per environment you want to scan. Requires Power Platform admin rights.
pac auth create
pac admin list                 # copy the Environment ID you want to scan

pac admin create-service-principal \\
  --environment <ENVIRONMENT-ID> \\
  --role "System Administrator"

# Prints: Application (client) ID, Tenant ID, and Client secret.
# 'System Administrator' is convenient for a lab; scope to a least-privilege
# custom role (read on the tables listed above) for production.`;

const DATAVERSE_TABLES = [
  "Bot",
  "Bot Component",
  "Connection Reference",
  "Environment Variable Definition",
  "Solution",
];

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked — user can select manually */
        }
      }}
      className="shrink-0 rounded-md border border-hairline px-2 py-1 text-xs font-medium text-slate hover:bg-mist"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

function Chip({ value }: { value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-mist px-3 py-2">
      <code className="text-xs text-ink">{value}</code>
      <CopyButton text={value} />
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-orange text-xs font-bold text-white">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-1.5">
        <h4 className="text-sm font-semibold text-ink">{title}</h4>
        <div className="text-sm text-slate">{children}</div>
      </div>
    </div>
  );
}

function RoleNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-line bg-mist px-3 py-2 text-xs text-slate">
      <span className="shrink-0 rounded bg-strong px-1.5 py-0.5 font-semibold text-white">
        Requires
      </span>
      <span className="leading-relaxed">{children}</span>
    </div>
  );
}

/**
 * Guided setup for the service principal the platform needs to read agents live.
 * Two parts: (A) the Entra app registration, (B) registering that app as an
 * application user in each Power Platform environment. Collapsible.
 */
export default function SetupWizard({ defaultOpen = true }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [showScript, setShowScript] = useState(false);
  const [showEntraScript, setShowEntraScript] = useState(false);

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 bg-mist px-6 py-4 text-left"
      >
        <div>
          <h2 className="text-lg font-semibold text-ink">
            Setup guide: service principal for live scanning
          </h2>
          <p className="mt-0.5 text-sm text-slate">
            The platform reads agents live from the Dataverse Web API. Create one Entra app
            registration, then register it as an application user in each environment you scan.
          </p>
        </div>
        <span className="shrink-0 text-slate">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-6 py-5 space-y-8">
          {/* -------- Part A: Entra ID -------- */}
          <div className="space-y-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-orange">
              Part A · Microsoft Entra ID (app registration)
            </div>
            <RoleNote>
              Microsoft Entra <span className="font-semibold text-ink">Application Administrator</span>{" "}
              (or Cloud Application Administrator / Global Administrator) — needed to register the app
              and, for the optional <span className="font-mono">Directory.Read.All</span>, to grant
              admin consent. Registering an app alone only needs the{" "}
              <span className="font-semibold text-ink">Application Developer</span> role.
            </RoleNote>

            <Step n={1} title="Create the app registration">
              <p>
                Open{" "}
                <a
                  href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-orange underline"
                >
                  Entra → App registrations → New registration
                </a>
                . Name it something like <span className="font-medium">Agent Quality Platform</span>,
                keep the defaults, and select <span className="font-medium">Register</span>.
              </p>
            </Step>

            <Step n={2} title="Create a client secret">
              <p>
                Under <span className="font-medium">Certificates &amp; secrets → New client secret</span>,
                create one and copy its <span className="font-medium">Value</span> immediately — it's
                shown only once.
              </p>
            </Step>

            <Step n={3} title="(Optional) Add a Graph permission for report-group gating">
              <p className="mb-2">
                Only needed if you'll restrict the dashboard to an Entra security group. Under{" "}
                <span className="font-medium">
                  API permissions → Add a permission → Microsoft Graph → Application permissions
                </span>
                , add this and choose <span className="font-medium">Grant admin consent</span>:
              </p>
              <div className="max-w-sm">
                <Chip value="Directory.Read.All" />
              </div>
            </Step>

            <Step n={4} title="Copy the IDs into the form below">
              <p>
                From the app's <span className="font-medium">Overview</span> page, copy the{" "}
                <span className="font-medium">Directory (tenant) ID</span> and{" "}
                <span className="font-medium">Application (client) ID</span>. Paste those plus the
                secret into <span className="font-medium">Service principal &amp; judge</span> below,
                then <span className="font-medium">Save</span>.
              </p>
            </Step>

            <div className="rounded-lg border border-line">
              <button
                type="button"
                onClick={() => setShowEntraScript((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-ink"
              >
                <span>Prefer to script it? Run this instead of steps 1–3</span>
                <span className="text-slate">{showEntraScript ? "▲" : "▼"}</span>
              </button>
              {showEntraScript && (
                <div className="border-t border-line px-4 py-3">
                  <div className="mb-2 flex justify-end">
                    <CopyButton text={ENTRA_SCRIPT} label="Copy script" />
                  </div>
                  <pre className="max-h-72 overflow-auto rounded-md bg-strong p-3 text-xs leading-relaxed text-white">
                    <code>{ENTRA_SCRIPT}</code>
                  </pre>
                  <p className="mt-2 text-xs text-slate">
                    Resolves permission IDs by name, creates the app, (optionally) grants{" "}
                    <span className="font-mono">Directory.Read.All</span> consent, and prints the
                    Tenant ID, Client ID, and secret to paste below.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* -------- Part B: Power Platform -------- */}
          <div className="space-y-5 border-t border-line pt-6">
            <div className="text-xs font-semibold uppercase tracking-wide text-orange">
              Part B · Power Platform (application user, per environment)
            </div>
            <RoleNote>
              <span className="font-semibold text-ink">Power Platform Administrator</span> (or a{" "}
              <span className="font-semibold text-ink">System Administrator</span> security role in the
              target environment) — needed to create application users and assign security roles.
              Global / Dynamics 365 Administrator also works.
            </RoleNote>

            <Step n={1} title="Open the environment's application users">
              <p>
                In the{" "}
                <a
                  href="https://admin.powerplatform.microsoft.com/environments"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-orange underline"
                >
                  Power Platform admin center
                </a>
                , pick your environment →{" "}
                <span className="font-medium">
                  Settings → Users + permissions → Application users
                </span>{" "}
                → <span className="font-medium">New app user</span>.
              </p>
            </Step>

            <Step n={2} title="Add the app registration">
              <p>
                Choose <span className="font-medium">Add an app</span>, search for the app by its{" "}
                <span className="font-medium">Application (client) ID</span> from Part A, and pick a
                business unit.
              </p>
            </Step>

            <Step n={3} title="Assign a security role with read on the agent tables">
              <p className="mb-2">
                Give the app user a role with <span className="font-medium">Read</span> (Organization
                level) on these Dataverse tables so the scanner can see agents and their config:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg">
                {DATAVERSE_TABLES.map((t) => (
                  <Chip key={t} value={t} />
                ))}
              </div>
              <p className="mt-2 text-xs text-slate">
                Least privilege: a custom role with Organization-level Read on those tables. Quick lab
                option: the built-in <span className="font-medium">System Customizer</span> role.
              </p>
            </Step>

            <Step n={4} title="Repeat per environment, then test">
              <p>
                Do this in every environment you added above. Back here, use{" "}
                <span className="font-medium">Test</span> on the environment, then{" "}
                <span className="font-medium">Scan now</span>.
              </p>
            </Step>

            <div className="rounded-lg border border-line">
              <button
                type="button"
                onClick={() => setShowScript((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-ink"
              >
                <span>Prefer to script it? Create the app + app user in one command</span>
                <span className="text-slate">{showScript ? "▲" : "▼"}</span>
              </button>
              {showScript && (
                <div className="border-t border-line px-4 py-3">
                  <div className="mb-2 flex justify-end">
                    <CopyButton text={PAC_SCRIPT} label="Copy command" />
                  </div>
                  <pre className="max-h-72 overflow-auto rounded-md bg-strong p-3 text-xs leading-relaxed text-white">
                    <code>{PAC_SCRIPT}</code>
                  </pre>
                  <p className="mt-2 text-xs text-slate">
                    <span className="font-mono">pac admin create-service-principal</span> creates the
                    Entra app <em>and</em> registers it as an application user in the environment, then
                    prints the Tenant ID, Client ID, and secret to paste below.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* -------- App Insights note -------- */}
          <div className="border-t border-line pt-5 text-sm text-slate">
            <span className="font-semibold text-ink">Application Insights (optional):</span> to light
            up live telemetry (runs, errors, latency) per agent, add the environment's App Insights{" "}
            <span className="font-medium">Application ID</span> and an{" "}
            <span className="font-medium">API key</span> (App Insights → API Access) on the environment
            above. No service-principal permission is required for this.
            <span className="block mt-1 text-xs">
              Requires <span className="font-semibold text-ink">Contributor</span> (or Monitoring
              Contributor) on the Application Insights resource to create the API key.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

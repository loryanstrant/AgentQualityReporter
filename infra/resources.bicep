// Container Apps environment + API/worker apps + Postgres Flexible Server + Key Vault.
@description('Name prefix for all resources.')
param name string

@description('Azure region.')
param location string

@description('PostgreSQL administrator login.')
param dbAdmin string

@secure()
param dbPassword string

@secure()
param appAdminPassword string

var suffix = uniqueString(resourceGroup().id)
var pgName = toLower('${name}pg${suffix}')
var dbName = 'agentquality'

// ---- Log Analytics (required by Container Apps) ----
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---- User-assigned managed identity for outbound API auth (Dataverse etc.) ----
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-identity'
  location: location
}

// ---- Key Vault for secrets ----
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: toLower('${name}kv${suffix}')
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
  }
}

// ---- PostgreSQL Flexible Server ----
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: dbAdmin
    administratorLoginPassword: dbPassword
    storage: { storageSizeGB: 32 }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource pgFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: pg
  name: 'AllowAzure'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: dbName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

var databaseUrl = 'postgresql+psycopg://${dbAdmin}:${dbPassword}@${pg.properties.fullyQualifiedDomainName}:5432/${dbName}'

// ---- Container Apps environment ----
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var sharedSecrets = [
  { name: 'database-url', value: databaseUrl }
  { name: 'app-admin-password', value: appAdminPassword }
  { name: 'fernet-key', value: uniqueString(resourceGroup().id, 'fernet') }
  { name: 'secret-key', value: uniqueString(resourceGroup().id, 'jwt') }
]

var sharedEnv = [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'FERNET_KEY', secretRef: 'fernet-key' }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'APP_ENV', value: 'production' }
]

// ---- API container app (public) ----
resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-api'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: { external: true, targetPort: 8000 }
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${name}/api:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'ADMIN_USERNAME', value: 'admin' }
            { name: 'ADMIN_PASSWORD', secretRef: 'app-admin-password' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// ---- Worker container app (no ingress) ----
resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-worker'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: { secrets: sharedSecrets }
    template: {
      containers: [
        {
          name: 'worker'
          image: '${name}/worker:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: sharedEnv
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output apiUrl string = 'https://${apiApp.properties.configuration.ingress.fqdn}'

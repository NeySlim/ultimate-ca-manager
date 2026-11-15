{{/* Expand the name of the chart. */}}
{{- define "ucm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Fully qualified app name. */}}
{{- define "ucm.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "ucm.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. */}}
{{- define "ucm.labels" -}}
helm.sh/chart: {{ include "ucm.chart" . }}
{{ include "ucm.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels. */}}
{{- define "ucm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ucm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* ServiceAccount name. */}}
{{- define "ucm.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ucm.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/* Secret name. */}}
{{- define "ucm.secretName" -}}
{{- printf "%s-secrets" (include "ucm.fullname" .) }}
{{- end }}

{{/* Image reference (tag falls back to appVersion). */}}
{{- define "ucm.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- if and .Values.fips.enabled (not (hasSuffix "-fips" $tag)) -}}
{{- $tag = printf "%s-fips" $tag -}}
{{- end -}}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{/* PVC names. */}}
{{- define "ucm.dataPvcName" -}}
{{- .Values.persistence.data.existingClaim | default (printf "%s-data" (include "ucm.fullname" .)) }}
{{- end }}
{{- define "ucm.etcPvcName" -}}
{{- .Values.persistence.etc.existingClaim | default (printf "%s-etc" (include "ucm.fullname" .)) }}
{{- end }}

{{/* HA render guard: fails the render when the values cannot span nodes. */}}
{{- define "ucm.haValidate" -}}
{{- if .Values.ha.enabled -}}
{{- if ne .Values.database.type "postgresql" -}}
{{- fail "ha.enabled requires database.type=postgresql (SQLite is single-node)" -}}
{{- end -}}
{{- if not (or .Values.database.databaseUrl .Values.database.existingSecret) -}}
{{- fail "ha.enabled requires database.databaseUrl or database.existingSecret" -}}
{{- end -}}
{{- if lt (int .Values.replicaCount) 2 -}}
{{- fail "ha.enabled requires replicaCount >= 2" -}}
{{- end -}}
{{- /* An existing release without these keys in its Secret is a single instance moving to HA */ -}}
{{- if .Release.IsUpgrade -}}
{{- if not (include "ucm.existingKek" .) -}}
{{- fail "ha.enabled on an existing single instance requires secrets.keyEncryptionKey: set it to the content of the instance's /etc/ucm/master.key, or a new key would make its private keys unreadable (docs/HA.md, From one node to a cluster)" -}}
{{- end -}}
{{- if not (include "ucm.existingDbKey" .) -}}
{{- fail "ha.enabled on an existing single instance requires secrets.dbEncryptionKey: set it while the instance still runs alone and re-encrypt its integration secrets under it first (docs/HA.md, From one node to a cluster)" -}}
{{- end -}}
{{- end -}}
{{- else if gt (int .Values.replicaCount) 1 -}}
{{- fail "replicaCount > 1 requires ha.enabled=true (and PostgreSQL): a single instance cannot run in several pods" -}}
{{- end -}}
{{- end }}

{{/*
Existing or explicit KEY_ENCRYPTION_KEY ("" when none): kept whatever ha.enabled is,
so leaving HA never drops the only copy of the key.
*/}}
{{- define "ucm.existingKek" -}}
{{- $existing := (lookup "v1" "Secret" .Release.Namespace (include "ucm.secretName" .)) | default dict -}}
{{- $data := $existing.data | default dict -}}
{{- .Values.secrets.keyEncryptionKey | default ((get $data "KEY_ENCRYPTION_KEY") | default "" | b64dec) -}}
{{- end -}}

{{/* Existing or explicit UCM_DB_ENCRYPTION_KEY ("" when none), kept like the KEK. */}}
{{- define "ucm.existingDbKey" -}}
{{- $existing := (lookup "v1" "Secret" .Release.Namespace (include "ucm.secretName" .)) | default dict -}}
{{- $data := $existing.data | default dict -}}
{{- .Values.secrets.dbEncryptionKey | default ((get $data "UCM_DB_ENCRYPTION_KEY") | default "" | b64dec) -}}
{{- end -}}

{{/*
How extraEnv provides the initial admin password, if it does: "file" or "variable".
The chart's own variable is then not passed: it would replace the operator's value,
and both sources set refuse the start.
*/}}
{{- define "ucm.adminPasswordFromExtraEnv" -}}
{{- $how := "" -}}
{{- range .Values.extraEnv -}}
{{- if has .name (list "INITIAL_ADMIN_PASSWORD_FILE" "UCM_INITIAL_ADMIN_PASSWORD_FILE") -}}{{- $how = "file" -}}
{{- else if and (has .name (list "INITIAL_ADMIN_PASSWORD" "UCM_INITIAL_ADMIN_PASSWORD")) (not $how) -}}{{- $how = "variable" -}}
{{- end -}}
{{- end -}}
{{- $how -}}
{{- end -}}

{{/*
"true" when the initial admin password is the chart's own random value: the
application then forces its change at first login, as for one it generates.
*/}}
{{- define "ucm.adminPasswordGenerated" -}}
{{- if not (or .Values.initialAdminPassword (include "ucm.adminPasswordFromExtraEnv" .)) }}true{{ end -}}
{{- end -}}

{{/*
What the Secret is made from, as the operator sets it: the input of checksum/secret.
A generated value is stored once and read back, so it never changes the Secret.
*/}}
{{- define "ucm.secretInputs" -}}
{{- list .Values.secrets.secretKey .Values.initialAdminPassword (include "ucm.adminPasswordFromExtraEnv" .)
    .Values.secrets.keyEncryptionKey .Values.secrets.dbEncryptionKey .Values.ha.enabled
    .Values.database.type .Values.database.databaseUrl .Values.database.existingSecret | toJson -}}
{{- end -}}

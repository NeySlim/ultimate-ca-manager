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

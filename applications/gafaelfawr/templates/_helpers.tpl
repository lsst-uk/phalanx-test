{{/* vim: set filetype=mustache: */}}
{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "gafaelfawr.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "gafaelfawr.labels" -}}
helm.sh/chart: {{ include "gafaelfawr.chart" . }}
{{ include "gafaelfawr.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "gafaelfawr.selectorLabels" -}}
app.kubernetes.io/name: "gafaelfawr"
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Common environment variables
*/}}
{{- define "gafaelfawr.envVars" -}}
{{- if (not .Values.config.afterLogoutUrl) }}
- name: "GAFAELFAWR_AFTER_LOGOUT_URL"
  value: {{ required "global.baseUrl must be set" .Values.global.baseUrl | quote }}
{{- end }}
- name: "GAFAELFAWR_BOOTSTRAP_TOKEN"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "bootstrap-token"
{{- if .Values.config.cilogon.clientId }}
- name: "GAFAELFAWR_CILOGON_CLIENT_SECRET"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "cilogon-client-secret"
{{- end }}
- name: "GAFAELFAWR_DATABASE_PASSWORD"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "database-password"
{{- if (or .Values.cloudsql.enabled .Values.config.internalDatabase) }}
- name: "GAFAELFAWR_DATABASE_URL"
  {{- if (and .sidecar .Values.cloudsql.enabled) }}
  value: "postgresql://gafaelfawr@localhost/gafaelfawr"
  {{- else if .Values.cloudsql.enabled }}
  value: "postgresql://gafaelfawr@cloud-sql-proxy/gafaelfawr"
  {{- else if .Values.config.internalDatabase }}
  value: "postgresql://gafaelfawr@postgres.postgres/gafaelfawr"
  {{- end }}
{{- end }}
{{- if .Values.config.github.clientId }}
- name: "GAFAELFAWR_GITHUB_CLIENT_SECRET"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "github-client-secret"
{{- end }}
{{- if .Values.config.ldap.userDn }}
- name: "GAFAELFAWR_LDAP_PASSWORD"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "ldap-password"
{{- end }}
{{- if .Values.config.oidc.clientId }}
- name: "GAFAELFAWR_OIDC_CLIENT_SECRET"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "oidc-client-secret"
{{- end }}
{{- if .Values.config.oidcServer.enabled }}
- name: "GAFAELFAWR_OIDC_SERVER_CLIENTS"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "oidc-server-secrets"
{{- if (not .Values.config.oidcServer.issuer) }}
- name: "GAFAELFAWR_OIDC_SERVER_ISSUER"
  value: {{ .Values.global.baseUrl | quote }}
{{- end }}
- name: "GAFAELFAWR_OIDC_SERVER_KEY"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "signing-key"
{{- end }}
{{- if (not .Values.config.realm) }}
- name: "GAFAELFAWR_REALM"
  value: {{ required "global.host must be set" .Values.global.host | quote }}
{{- end }}
- name: "GAFAELFAWR_REDIRECT_URL"
  value: "{{ .Values.global.baseUrl }}/login"
- name: "GAFAELFAWR_REDIS_PASSWORD"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "redis-password"
- name: "GAFAELFAWR_REDIS_URL"
  value: "redis://gafaelfawr-redis.{{ .Release.Namespace }}:6379/0"
- name: "GAFAELFAWR_SESSION_SECRET"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "session-secret"
{{- if .Values.config.slackAlerts }}
- name: "GAFAELFAWR_SLACK_WEBHOOK"
  valueFrom:
    secretKeyRef:
      name: {{ .secretName | quote }}
      key: "slack-webhook"
{{- end }}
{{- end }}

{{- define "roxy-wi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "roxy-wi.fullname" -}}
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

{{- define "roxy-wi.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "roxy-wi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "roxy-wi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "roxy-wi.labels" -}}
helm.sh/chart: {{ include "roxy-wi.chart" . }}
{{ include "roxy-wi.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "roxy-wi.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) }}
{{- end }}

{{- define "roxy-wi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "roxy-wi.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "roxy-wi.configSecretName" -}}
{{- default (printf "%s-config" (include "roxy-wi.fullname" .)) .Values.existingConfigSecret }}
{{- end }}

{{- define "roxy-wi.runtimeSecretName" -}}
{{- printf "%s-runtime" (include "roxy-wi.fullname" .) }}
{{- end }}

{{- define "roxy-wi.dataClaimName" -}}
{{- default (printf "%s-data" (include "roxy-wi.fullname" .)) .Values.persistence.existingClaim }}
{{- end }}

{{- define "roxy-wi.validateValues" -}}
{{- if not .Values.existingConfigSecret -}}
{{- $main := default (dict) (get .Values.config "main") -}}
{{- $secretKey := required "config.main.secret_key is required" (get $main "secret_key") | toString -}}
{{- if lt (len $secretKey) 32 -}}
{{- fail "config.main.secret_key must contain at least 32 characters" -}}
{{- end -}}
{{- $secretPhrase := required "config.main.secret_phrase is required" (get $main "secret_phrase") | toString -}}
{{- if eq ($secretPhrase | trim) "CHANGE_ME" -}}
{{- fail "config.main.secret_phrase must not use CHANGE_ME" -}}
{{- end -}}
{{- $database := default (dict) (get .Values.config "database") -}}
{{- $engine := default "sqlite" (get $database "engine") | toString | lower -}}
{{- if not (has $engine (list "sqlite" "mysql" "mariadb")) -}}
{{- fail "config.database.engine must be sqlite, mysql or mariadb" -}}
{{- end -}}
{{- if and (eq $engine "sqlite") (gt (int .Values.web.replicaCount) 1) -}}
{{- fail "SQLite supports only web.replicaCount=1; use MySQL/MariaDB for HA" -}}
{{- end -}}
{{- end -}}
{{- if not .Values.persistence.enabled -}}
{{- fail "persistence.enabled must be true until external object storage is supported" -}}
{{- end -}}
{{- if and (gt (int .Values.web.replicaCount) 1) (not (has "ReadWriteMany" .Values.persistence.accessModes)) -}}
{{- fail "Multiple web replicas require persistence.accessModes to include ReadWriteMany" -}}
{{- end -}}
{{- if .Values.rabbitmq.environmentOverride -}}
{{- $_ := required "rabbitmq.host is required when environmentOverride=true" .Values.rabbitmq.host -}}
{{- if not .Values.rabbitmq.existingSecret -}}
{{- $_ := required "rabbitmq.password or rabbitmq.existingSecret is required" .Values.rabbitmq.password -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "roxy-wi.config" -}}
{{- include "roxy-wi.validateValues" . -}}
{{ range $section, $options := .Values.config -}}
[{{ $section }}]
{{ range $key, $value := $options -}}
{{ $key }} = {{ $value }}
{{ end }}
{{ end -}}
{{- end }}

{{- define "roxy-wi.configChecksum" -}}
{{- if not .Values.existingConfigSecret -}}
checksum/config: {{ include "roxy-wi.config" . | sha256sum }}
{{- end }}
{{- end }}

{{- define "roxy-wi.runtimeChecksum" -}}
{{- if or .Values.bootstrapAdminPassword (and .Values.rabbitmq.environmentOverride (not .Values.rabbitmq.existingSecret)) -}}
checksum/runtime: {{ printf "%s:%s" (toJson .Values.rabbitmq) .Values.bootstrapAdminPassword | sha256sum }}
{{- end }}
{{- end }}

{{- define "roxy-wi.commonEnv" -}}
- name: ROXYWI_CONFIG_FILE
  value: /etc/roxy-wi/roxy-wi.cfg
{{- end }}

{{- define "roxy-wi.commonEnvFrom" -}}
{{- if or .Values.bootstrapAdminPassword (and .Values.rabbitmq.environmentOverride (not .Values.rabbitmq.existingSecret)) }}
- secretRef:
    name: {{ include "roxy-wi.runtimeSecretName" . }}
{{- end }}
{{- if and .Values.rabbitmq.environmentOverride .Values.rabbitmq.existingSecret }}
- secretRef:
    name: {{ .Values.rabbitmq.existingSecret }}
{{- end }}
{{- end }}

{{- define "roxy-wi.volumes" -}}
- name: config
  secret:
    secretName: {{ include "roxy-wi.configSecretName" . }}
- name: data
  persistentVolumeClaim:
    claimName: {{ include "roxy-wi.dataClaimName" . }}
- name: tmp
  emptyDir: {}
{{- with .Values.extraVolumes }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{- define "roxy-wi.volumeMounts" -}}
- name: config
  mountPath: /etc/roxy-wi
  readOnly: true
- name: data
  mountPath: /var/lib/roxy-wi
- name: tmp
  mountPath: /tmp
{{- with .Values.extraVolumeMounts }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{- define "roxy-wi.waitForDatabase" -}}
- name: wait-for-database
  image: {{ include "roxy-wi.image" . }}
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  args: ["wait-for-database"]
  env:
    {{- include "roxy-wi.commonEnv" . | nindent 4 }}
  {{- $envFrom := include "roxy-wi.commonEnvFrom" . }}
  {{- if $envFrom }}
  envFrom:
    {{- $envFrom | nindent 4 }}
  {{- end }}
  securityContext:
    {{- toYaml .Values.securityContext | nindent 4 }}
  volumeMounts:
    {{- include "roxy-wi.volumeMounts" . | nindent 4 }}
{{- end }}

{{- define "roxy-wi.dataWorkerAffinity" -}}
{{- if and .Values.persistence.enabled (not (has "ReadWriteMany" .Values.persistence.accessModes)) }}
podAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          {{- include "roxy-wi.selectorLabels" . | nindent 10 }}
          app.kubernetes.io/component: web
      topologyKey: kubernetes.io/hostname
{{- end }}
{{- end }}

{{- define "roxy-wi.workerProbes" -}}
startupProbe:
  exec:
    command: ["python", "/var/www/haproxy-wi/roxy_wi.py", "healthcheck", "--role", {{ . | quote }}, "--check", "live"]
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 60
livenessProbe:
  exec:
    command: ["python", "/var/www/haproxy-wi/roxy_wi.py", "healthcheck", "--role", {{ . | quote }}, "--check", "live"]
  periodSeconds: 20
  timeoutSeconds: 3
  failureThreshold: 3
readinessProbe:
  exec:
    command: ["python", "/var/www/haproxy-wi/roxy_wi.py", "healthcheck", "--role", {{ . | quote }}, "--check", "ready"]
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 1
{{- end }}

{{- define "roxy-wi.migrationName" -}}
{{- $base := include "roxy-wi.fullname" . | trunc 42 | trimSuffix "-" -}}
{{- $hash := printf "%s:%s:%s" (include "roxy-wi.image" .) (include "roxy-wi.config" .) .Chart.Version | sha256sum | trunc 8 -}}
{{- printf "%s-migrate-%s" $base $hash -}}
{{- end }}

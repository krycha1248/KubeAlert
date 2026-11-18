locals {
  node_pool_flavor         = "d2-4"
  deploy_traefik           = true
  domain_name              = get_env("TF_VAR_domain_name", "kubealert.wlodek.net")
  zone_name                = get_env("TF_VAR_zone_name", "wlodek.net")
  www_subdomain_enabled    = false
  acme_email               = get_env("TF_VAR_acme_email", "")
  namespace                = "kubealert"
  postgres_instances_count = 1
  app_image_tag            = get_env("TF_VAR_app_image_tag", "latest")

  # SMTP & Alerting settings
  smtp_host              = get_env("TF_VAR_smtp_host")
  smtp_port              = tonumber(get_env("TF_VAR_smtp_port", "587"))
  smtp_user              = get_env("TF_VAR_smtp_user")
  smtp_password          = get_env("TF_VAR_smtp_password")
  smtp_use_tls           = get_env("TF_VAR_smtp_use_tls", "true")
  smtp_use_ssl           = get_env("TF_VAR_smtp_use_ssl", "false")
  alert_from_email       = get_env("TF_VAR_smtp_user")
  alert_to_email         = get_env("TF_VAR_alert_to_email", "krystian@wlodek.net")
  monitored_namespaces   = get_env("TF_VAR_monitored_namespaces", "")
  ignored_namespaces     = get_env("TF_VAR_ignored_namespaces", "kube-system,local-path-storage")
  alert_cooldown_seconds = tonumber(get_env("TF_VAR_alert_cooldown_seconds", "900"))
  include_logs           = get_env("TF_VAR_include_logs", "true")

  oauth_client_id     = get_env("TF_VAR_oauth_client_id", "")
  oauth_client_secret = get_env("TF_VAR_oauth_client_secret", "")
}

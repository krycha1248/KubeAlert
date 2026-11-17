locals {
  node_pool_flavor         = "d2-4"
  deploy_traefik           = true
  domain_name              = get_env("TF_VAR_domain_name", "kubealert.wlodek.net")
  zone_name                = get_env("TF_VAR_zone_name", "wlodek.net")
  www_subdomain_enabled    = false
  acme_email               = get_env("TF_VAR_acme_email", "")
  namespace                = "kubealert"
  postgres_instances_count = 1
  app_image_tag            = get_env("TF_VAR_app_image_tag", "")
}

locals {
    node_pool_flavor         = "d2-4"
    deploy_traefik           = true
    deploy_cnpg              = true
    domain_name              = get_env("TF_VAR_domain_name", "")
    zone_name                = get_env("TF_VAR_zone_name", "")
    www_subdomain_enabled    = true
    acme_email               = get_env("TF_VAR_acme_email", "")
    namespace                = "kubealert"
    postgres_instances_count = 1
}
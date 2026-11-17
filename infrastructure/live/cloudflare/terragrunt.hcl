include {
  path = find_in_parent_folders("root.hcl")
}

locals {
  deployment = read_terragrunt_config(find_in_parent_folders("deployment.hcl"))
}

dependency "bootstrap" {
  config_path = "../bootstrap"

  mock_outputs = {
    ingress_lb_ip = "127.0.0.1"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

terraform {
  source = "git::https://github.com/krycha1248/terraform-modules.git//cloudflare-domain"
}

inputs = {
  domain_name           = local.deployment.locals.domain_name
  zone_name             = local.deployment.locals.zone_name
  ip_address            = dependency.bootstrap.outputs.ingress_lb_ip
  www_subdomain_enabled = false
  proxy                 = true
}

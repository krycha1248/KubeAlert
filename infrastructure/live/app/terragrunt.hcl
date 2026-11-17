include {
  path = find_in_parent_folders("root.hcl")
}

locals {
  deployment = read_terragrunt_config(find_in_parent_folders("deployment.hcl"))
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs = {
    kubernetes_host                   = "https://127.0.0.1:6443"
    kubernetes_cluster_ca_certificate = "bW9ja19jYQo="
    kubernetes_client_certificate     = "bW9ja19jbGllbnRfY2VydAo="
    kubernetes_client_key             = "bW9ja19jbGllbnRfa2V5Cg=="
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

terraform {
  source = "../../modules/app"
}

inputs = {
  kube_host                   = dependency.cluster.outputs.kubernetes_host
  kube_cluster_ca_certificate = dependency.cluster.outputs.kubernetes_cluster_ca_certificate
  kube_client_certificate     = dependency.cluster.outputs.kubernetes_client_certificate
  kube_client_key             = dependency.cluster.outputs.kubernetes_client_key

  create_namespace = true
  namespace        = local.deployment.locals.namespace
  app_name         = "kubealert"
  image_name       = "ghcr.io/krycha1248/kubealert"
  image_tag        = local.deployment.locals.app_image_tag
  domain_name      = local.deployment.locals.domain_name
}

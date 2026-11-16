include {
  path = find_in_parent_folders("root.hcl")
}

locals {
    deployment = read_terragrunt_config(find_in_parent_folders("deployment.hcl"))
}

terraform {
    source = "git::https://github.com/krycha1248/terraform-modules.git//k8s-cluster"
}

inputs = {
    node_pool_flavor = local.deployment.locals.node_pool_flavor
}
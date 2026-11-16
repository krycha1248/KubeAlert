remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    bucket = "krywlo-tfstate"
    key    = "k8s-kubealert/${path_relative_to_include()}/terraform.tfstate"
    region = "waw"

    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true

    use_path_style = true
  }
}
variable "kube_host" {
  description = "Kubernetes API server host URL"
  type        = string
}

variable "kube_cluster_ca_certificate" {
  description = "Base64 encoded CA certificate for the Kubernetes cluster"
  type        = string
}

variable "kube_client_certificate" {
  description = "Base64 encoded client certificate for Kubernetes authentication"
  type        = string
}

variable "kube_client_key" {
  description = "Base64 encoded client key for Kubernetes authentication"
  type        = string
  sensitive   = true
}

variable "namespace" {
  description = "Kubernetes namespace to deploy the application into"
  type        = string
  default     = "kubealert"
}

variable "app_name" {
  description = "Name of the application and Kubernetes resources prefix"
  type        = string
  default     = "kubealert"
}

variable "image_name" {
  description = "Docker image repository name (e.g. ghcr.io/krycha1248/kubealert)"
  type        = string
  default     = "ghcr.io/krycha1248/kubealert"
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. v1.0.0)"
  type        = string
}

variable "image_pull_policy" {
  description = "Kubernetes image pull policy"
  type        = string
  default     = "IfNotPresent"
}

variable "image_pull_secrets" {
  description = "List of names of Kubernetes image pull secrets for private registry access"
  type        = list(string)
  default     = []
}

variable "replicas" {
  description = "Number of deployment replicas"
  type        = number
  default     = 1
}

variable "container_port" {
  description = "Port exposed by the application container"
  type        = number
  default     = 8080
}

variable "service_port" {
  description = "Port exposed by the Kubernetes ClusterIP service"
  type        = number
  default     = 80
}

variable "env_vars" {
  description = "Additional environment variables to pass to the container"
  type        = map(string)
  default     = {}
}

variable "resources" {
  description = "Resource limits and requests for the container"
  type = object({
    limits = object({
      cpu    = string
      memory = string
    })
    requests = object({
      cpu    = string
      memory = string
    })
  })
  default = {
    limits = {
      cpu    = "200m"
      memory = "128Mi"
    }
    requests = {
      cpu    = "50m"
      memory = "64Mi"
    }
  }
}

variable "ingress_enabled" {
  description = "Whether to deploy a Kubernetes Ingress resource"
  type        = bool
  default     = false
}

variable "ingress_class_name" {
  description = "Ingress class name (e.g. traefik)"
  type        = string
  default     = "traefik"
}

variable "domain_name" {
  description = "Domain name for the Ingress route"
  type        = string
  default     = ""
}

variable "extra_labels" {
  description = "Extra labels to attach to all resources"
  type        = map(string)
  default     = {}
}

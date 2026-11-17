output "deployment_name" {
  description = "Name of the Kubernetes deployment"
  value       = kubernetes_deployment_v1.this.metadata[0].name
}

output "service_name" {
  description = "Name of the Kubernetes service"
  value       = kubernetes_service_v1.this.metadata[0].name
}

output "service_account_name" {
  description = "Name of the ServiceAccount used by the pod"
  value       = kubernetes_service_account_v1.this.metadata[0].name
}

output "service_port" {
  description = "Port of the Kubernetes service"
  value       = var.service_port
}

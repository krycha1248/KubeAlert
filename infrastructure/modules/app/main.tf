locals {
  common_labels = merge(
    {
      "app.kubernetes.io/name"       = var.app_name
      "app.kubernetes.io/instance"   = var.app_name
      "app.kubernetes.io/version"    = var.image_tag
      "app.kubernetes.io/managed-by" = "terraform"
    },
    var.extra_labels
  )
}

# Optional namespace creation
resource "kubernetes_namespace_v1" "this" {

  metadata {
    name   = var.namespace
    labels = local.common_labels
  }
}

# ServiceAccount with automounted token for in-cluster KubeAPI access
resource "kubernetes_service_account_v1" "this" {
  metadata {
    name      = "${var.app_name}-sa"
    namespace = var.namespace
    labels    = local.common_labels
  }

  automount_service_account_token = true
}

# ClusterRole allowing KubeAlert to query KubeAPI endpoints
resource "kubernetes_cluster_role_v1" "this" {
  metadata {
    name   = "${var.app_name}-${var.namespace}-reader"
    labels = local.common_labels
  }

  # Allow version discovery and core API querying
  rule {
    non_resource_urls = ["/version", "/version/*", "/api", "/api/*", "/apis", "/apis/*"]
    verbs             = ["get"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods", "services", "namespaces", "nodes", "events"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log"]
    verbs      = ["get"]
  }
}

# Bind the ClusterRole to the application's ServiceAccount
resource "kubernetes_cluster_role_binding_v1" "this" {
  metadata {
    name   = "${var.app_name}-${var.namespace}-binding"
    labels = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role_v1.this.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.this.metadata[0].name
    namespace = var.namespace
  }
}

# Application Deployment
resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels    = local.common_labels
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        "app.kubernetes.io/name" = var.app_name
      }
    }

    template {
      metadata {
        labels = local.common_labels
      }

      spec {
        service_account_name            = kubernetes_service_account_v1.this.metadata[0].name
        automount_service_account_token = true

        dynamic "image_pull_secrets" {
          for_each = var.image_pull_secrets
          content {
            name = image_pull_secrets.value
          }
        }

        container {
          name              = var.app_name
          image             = "${var.image_name}:${var.image_tag}"
          image_pull_policy = var.image_pull_policy

          port {
            name           = "http"
            container_port = var.container_port
            protocol       = "TCP"
          }

          env {
            name  = "PORT"
            value = tostring(var.container_port)
          }

          env {
            name  = "APP_VERSION"
            value = var.image_tag
          }

          env {
            name  = "SMTP_HOST"
            value = var.smtp_host
          }

          env {
            name  = "SMTP_PORT"
            value = tostring(var.smtp_port)
          }

          env {
            name  = "SMTP_USER"
            value = var.smtp_user
          }

          env {
            name  = "SMTP_PASSWORD"
            value = var.smtp_password
          }

          env {
            name  = "SMTP_USE_TLS"
            value = tostring(var.smtp_use_tls)
          }

          env {
            name  = "SMTP_USE_SSL"
            value = tostring(var.smtp_use_ssl)
          }

          env {
            name  = "ALERT_FROM_EMAIL"
            value = var.alert_from_email
          }

          env {
            name  = "ALERT_TO_EMAIL"
            value = var.alert_to_email
          }

          env {
            name  = "MONITORED_NAMESPACES"
            value = var.monitored_namespaces
          }

          env {
            name  = "IGNORED_NAMESPACES"
            value = var.ignored_namespaces
          }

          env {
            name  = "ALERT_COOLDOWN_SECONDS"
            value = tostring(var.alert_cooldown_seconds)
          }

          env {
            name  = "INCLUDE_LOGS"
            value = tostring(var.include_logs)
          }

          dynamic "env" {
            for_each = var.env_vars
            content {
              name  = env.key
              value = env.value
            }
          }

          resources {
            limits = {
              cpu    = var.resources.limits.cpu
              memory = var.resources.limits.memory
            }
            requests = {
              cpu    = var.resources.requests.cpu
              memory = var.resources.requests.memory
            }
          }

          liveness_probe {
            http_get {
              path = "/healthz"
              port = var.container_port
            }
            initial_delay_seconds = 5
            period_seconds        = 10
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/ready"
              port = var.container_port
            }
            initial_delay_seconds = 3
            period_seconds        = 5
            timeout_seconds       = 2
            failure_threshold     = 2
          }

          security_context {
            run_as_non_root            = true
            run_as_user                = 10001
            allow_privilege_escalation = false
            read_only_root_filesystem  = false

            capabilities {
              drop = ["ALL"]
            }
          }
        }
      }
    }
  }
}

# ClusterIP Service
resource "kubernetes_service_v1" "this" {
  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels    = local.common_labels
  }

  spec {
    type = "ClusterIP"

    selector = {
      "app.kubernetes.io/name" = var.app_name
    }

    port {
      name        = "http"
      port        = var.service_port
      target_port = var.container_port
      protocol    = "TCP"
    }
  }
}

# Optional Ingress resource (Traefik-compatible)
resource "kubernetes_ingress_v1" "this" {
  count = var.ingress_enabled ? 1 : 0

  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels    = local.common_labels
    annotations = {
      "traefik.ingress.kubernetes.io/router.entrypoints" = "web,websecure",
      "traefik.ingress.kubernetes.io/router.middlewares" = module.oauth_proxy.traefik_middleware_annotation
    }
  }

  spec {
    ingress_class_name = var.ingress_class_name

    rule {
      host = var.domain_name

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service_v1.this.metadata[0].name
              port {
                number = var.service_port
              }
            }
          }
        }
      }
    }
  }
}

module "oauth_proxy" {
  source = "git::https://github.com/krycha1248/terraform-modules.git//oauth-proxy"

  namespace                 = var.namespace
  create_namespace          = false
  app_name                  = "${var.app_name}-oauth-proxy"
  domain_name               = var.domain_name
  provider_type             = "github"
  client_id                 = var.oauth_client_id
  client_secret             = var.oauth_client_secret
  github_users              = var.oauth_github_users
  create_traefik_middleware = true
  ingress_enabled           = true
  ingress_class_name        = var.ingress_class_name
  portal_title              = var.oauth_portal_title
  extra_labels              = var.extra_labels
}

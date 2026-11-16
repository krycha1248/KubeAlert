.PHONY: \
        init plan apply destroy \
        config local all ci \
        init-instance plan-instance apply-instance destroy-instance config-instance all-instance \
        init-instance-local plan-instance-local apply-instance-local destroy-instance-local config-instance-local all-instance-local \

#
# helpers
#

SHELL := /bin/bash

TG := terragrunt --non-interactive
TG_LOCAL := . ./variables.sh && terragrunt

ENV ?= tech
LIVE_DIR := infrastructure/live
TG_INSTANCE := $(TG) --working-dir $(LIVE_DIR)
TG_INSTANCE_LOCAL := $(TG_LOCAL) --working-dir $(LIVE_DIR)
TF_ARGS ?=

init: init-instance
plan: plan-instance
apply: apply-instance
destroy: destroy-instance
config: config-instance
local: all-instance-local
all: all-instance
ci: all-instance

init-instance:
	@$(TG_INSTANCE) run --all init

plan-instance:
	@$(TG_INSTANCE) run --all plan $(TF_ARGS)

apply-instance:
	@$(TG_INSTANCE) run --all apply

destroy-instance:
	@$(TG_INSTANCE) run --all destroy

config-instance:
	@mkdir -p ~/.kube && $(TG) --working-dir $(LIVE_DIR)/cluster output -raw kubernetes_config > ~/.kube/config

all-instance: init-instance apply-instance config-instance

init-instance-local:
	@$(TG_INSTANCE_LOCAL) run --all init

plan-instance-local:
	@$(TG_INSTANCE_LOCAL) run --all plan $(TF_ARGS)

apply-instance-local:
	@$(TG_INSTANCE_LOCAL) run --all apply

destroy-instance-local:
	@$(TG_INSTANCE_LOCAL) run --all destroy

config-instance-local:
	@mkdir -p ~/.kube && $(TG_LOCAL) --working-dir $(LIVE_DIR)/cluster output -raw kubernetes_config > ~/.kube/config

all-instance-local: init-instance-local apply-instance-local config-instance-local
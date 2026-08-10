# Driving Copilot — operator convenience targets.
# Run from the repo root. `make help` lists targets.

.PHONY: help deploy-check deploy-check-docker up down logs ps

help:
	@echo "Targets:"
	@echo "  deploy-check         validate .env keys + compose config (no docker needed for .env)"
	@echo "  deploy-check-docker  deploy-check + docker compose config validation"
	@echo "  up                   build and start all services (detached)"
	@echo "  down                 stop all services"
	@echo "  logs                 follow bot logs"
	@echo "  ps                   show service status"

deploy-check:
	@scripts/deploy_check.sh

# Alias: the script already runs `docker compose config`. Kept for discoverability.
deploy-check-docker: deploy-check

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f bot

ps:
	docker compose ps

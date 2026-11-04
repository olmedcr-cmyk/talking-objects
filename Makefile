# Talking objects — common tasks. Run `make help`.

.PHONY: help setup test lint dev worker-setup worker-test worker-dev

help:            ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup:           ## Create the device venv and example config
	cd device && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest pytest-asyncio ruff
	cd device && cp -n config.example.env config.env; cp -n rules.example.toml rules.toml; true

test:            ## Device tests
	cd device && .venv/bin/python -m pytest -q

lint:            ## Device lint
	cd device && .venv/bin/ruff check .

dev:             ## Run the device on a laptop (null audio, keyboard trigger)
	cd device && FAKE_AUDIO=1 TRIGGER_MODE=keyboard .venv/bin/python -m talking_objects -v

worker-setup:    ## Install the Worker
	cd worker && npm install

worker-test:     ## Worker tests and type check
	cd worker && npm test && npm run typecheck

worker-dev:      ## Run the Worker locally on :8787
	cd worker && cp -n .dev.vars.example .dev.vars; npm run dev

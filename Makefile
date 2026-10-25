.PHONY: demo demo-stop sdlc sdlc-sample

demo:
	bash scripts/run_demo.sh

demo-stop:
	bash scripts/run_demo.sh stop

# SDLC agent + delivery console (:8792) + agent MCP server (:8791)
sdlc:
	PYTHONPATH=src uv run python -m sdlc

sdlc-sample:
	PYTHONPATH=src uv run python -m sdlc --source sample

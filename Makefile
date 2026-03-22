.PHONY: dev install test backend frontend

install:
	uv pip install -e ".[stt,tts,dev]"
	cd web && npm install

dev:
	@trap 'kill 0' INT; $(MAKE) backend & $(MAKE) frontend & wait

backend:
	uv run python -m ada

frontend:
	cd web && npm run dev

test:
	uv run python -m pytest tests/ -q

.PHONY: run test lint install clean clean-restart typecheck coverage install-hooks

run:
	python run.py

# Clear caches only (pycache, pytest, vite)
clean:
	@rm -rf frontend/node_modules/.vite frontend/dist .pytest_cache htmlcov .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Caches cleared."

# Stop backend+Vite, clear caches, start fresh
clean-restart:
	@pkill -f "run.py" 2>/dev/null || true
	@pkill -f "BTC_Claude_bot/frontend.*vite" 2>/dev/null || true
	@sleep 2
	@rm -rf frontend/node_modules/.vite frontend/dist .pytest_cache
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Caches cleared. Start backend: make run, frontend: cd frontend && npm run dev"

install:
	pip install -r requirements-dev.txt
	cd frontend && npm install

test:
	pytest tests/ -v

coverage:
	pytest tests/ -v --cov --cov-report=term-missing --cov-report=html

typecheck:
	mypy core/ ai/ safety/ strategy/ --ignore-missing-imports

lint:
	ruff check .
	ruff format --check .

install-hooks:
	pre-commit install

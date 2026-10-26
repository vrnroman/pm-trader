.PHONY: setup test lint run deploy

setup:
	pip install -r requirements.txt freezegun

test:
	python -m pytest tests/ -q
	CLOCK_DRIFT_DAYS=90 python -m pytest tests/ -q -p tests.clock_drift_plugin

lint:
	ruff check src/ tests/ main.py

run:
	python main.py

deploy:
	bash deploy.sh

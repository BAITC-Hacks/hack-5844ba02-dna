.PHONY: install pipeline serve all mock test

install:
	python -m pip install -r requirements.txt

pipeline:
	python -m pipeline --data data --out out

serve:
	uvicorn api.main:app --host 0.0.0.0 --port 8000

mock:
	python scripts/make_mock_out.py

test:
	pytest -q tests/test_api.py

all: pipeline serve

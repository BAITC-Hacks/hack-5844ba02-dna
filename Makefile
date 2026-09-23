.PHONY: install pipeline serve all mock test

PYTHON ?= python3
VENV ?= .venv
VPYTHON = $(VENV)/bin/python3

install:
	$(PYTHON) -m venv $(VENV)
	$(VPYTHON) -m pip install --upgrade pip
	$(VPYTHON) -m pip install -r requirements.txt

pipeline:
	$(VPYTHON) -m pipeline --data data --out out

serve:
	$(VPYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

mock:
	$(VPYTHON) scripts/make_mock_out.py

test:
	$(VPYTHON) -m pytest -q

all: pipeline serve

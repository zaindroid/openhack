.PHONY: dev check seed demo ui
dev:        ## run the API on :18000
	cd engine && python -m uvicorn engine.api:app --port 18000 --reload
seed:       ## synthetic experts, panels, answers into the DB
	cd engine && python -m scripts.seed
demo:       ## full loop on R1043 with the synthetic panel, offline, < 60 s
	cd engine && python -m scripts.demo_replay
check:      ## everything a merge must pass
	cd engine && python -m pytest -q
	cd ui && npm run build
	python scripts/validate_fixtures.py
ui:         ## frontend dev server on :5173
	cd ui && npm run dev

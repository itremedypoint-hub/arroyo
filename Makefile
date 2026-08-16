.PHONY: verify test-js test-py validate-training serve freshness links
verify: test-js test-py validate-training
	@echo "== verify: ALL GREEN =="
test-js:
	node --test tests/*.test.mjs
test-py:
	python3 tests/test_build_basins.py
	python3 tests/test_fetchers.py
	python3 tests/test_html_structure.py
validate-training:
	node tests/dump_training.mjs > /tmp/arroyo_training.json
	python3 scripts/ops_validate.py /tmp/arroyo_training.json
serve:
	cd site && python3 -m http.server 8000
freshness:
	python3 scripts/ops_freshness.py site/data/basins_eaton.json --require-live
links:
	python3 scripts/ops_linkcheck.py

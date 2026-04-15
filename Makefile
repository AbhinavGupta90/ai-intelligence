# AI Intelligence System — Dev Shortcuts

.PHONY: install run dry-run test-source weekly monthly feedback taste-update lint

# Install dependencies
install:
	pip install -r requirements.txt

# Full daily digest
run:
	python -m src.main --mode daily

# Dry run (no Telegram send)
dry-run:
	python -m src.main --mode daily --dry-run

# Test a single source
test-source:
	python -m src.main --source $(SOURCE) --dry-run --debug

# Alert check
alert:
	python -m src.main --mode alert

# Weekly report
weekly:
	python -m src.main --mode weekly

# Monthly report
monthly:
	python -m src.main --mode monthly

# Run feedback bot (long-polling, runs forever)
feedback:
	python -m src.main --mode feedback

# Recalculate taste profile
taste-update:
	python -m src.main --mode taste-update

# Debug run
debug:
	python -m src.main --mode daily --dry-run --debug

# Lint (optional)
lint:
	python -m py_compile src/main.py
	python -m py_compile src/config.py
	@echo "✅ No syntax errors"

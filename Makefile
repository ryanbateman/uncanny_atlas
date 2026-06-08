.PHONY: install collect collect-realorai stats enrich test lint clean

install:
	uv sync --all-extras

collect:
	uv run isthisai-collect submissions && uv run isthisai-collect comments

collect-realorai:
	uv run isthisai-collect submissions --subreddit RealOrAI && uv run isthisai-collect comments --subreddit RealOrAI

stats:
	uv run isthisai-stats

enrich:
	uv run isthisai-enrich subscribers && uv run isthisai-enrich post-types && uv run isthisai-enrich engagement

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/

import-arctic-api:
	uv run isthisai-import api submissions && uv run isthisai-import api comments

import-arctic-api-realorai:
	uv run isthisai-import api submissions --subreddit RealOrAI && uv run isthisai-import api comments --subreddit RealOrAI

import-arctic-file:
	uv run isthisai-import file submissions data/RS_*.zst
	uv run isthisai-import file comments data/RC_*.zst

clean:
	rm -rf data/isthisai.db
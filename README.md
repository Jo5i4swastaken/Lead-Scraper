# Lead Scraper (RGV) — OmniAgents Scaffold

Core scaffold for an AI-powered lead scraping pipeline for the Rio Grande Valley (RGV). This repo is intentionally modular so later phases can plug in additional scrapers/enrichers/scorers/exporters.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Set required env vars (secrets via env only):

```bash
export SERPAPI_API_KEY="..."
```

Optional:

```bash
export LEAD_SCRAPER_CONFIG_PATH="config/config.json"
```

## Run (CLI)

End-to-end pipeline:

```bash
lead-scraper run
```

Without installing, you can also run:

```bash
PYTHONPATH=src python3 -m lead_scraper.cli.main run
```

Run a single stage:

```bash
lead-scraper stage scrape
lead-scraper stage score
lead-scraper stage export --format jsonl
```

Outputs default to `out/leads.jsonl` and `out/leads.csv`.

## Run (OmniAgents)

```bash
cd agents/rgv_lead_scraper
omniagents run -c agent.yml --mode ink
```

The agent exposes tools to run the pipeline and stages.

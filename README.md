# Sentiment Market Prediction

This repo contains a Jupyter notebook implementation of determining whether aggregated Twitter sentiment can improve short-term prediction of political prediction market movements.

## Files

- `sentiment_market_prediction.ipynb`: main notebook
- `scripts/fetch_kalshi_market_data.py`: download Kalshi candlesticks into `market_data.csv`
- `scripts/prepare_election_dataset.py`: filter a public election-post dataset into `tweets_data.csv`
- `data/raw/`: place input CSV files here
- `data/processed/`: notebook outputs are saved here
- `outputs/figures/`: optional figure exports

## Quick Start

1. Activate the local environment:
   `. .venv/bin/activate`
2. Launch Jupyter:
   `jupyter notebook`
3. Run these scripts to get relevant datastes:
  - `fetch_kalshi_market_data.py`
  - `prepare_election_dataset.py`
3. Open `sentiment_market_prediction.ipynb`

## Default Data Source

The repo is now set up around `Kalshi + local tweet CSV`.

- Use Kalshi's official public API for prediction-market candles.
- Put tweet or post data into `data/raw/tweets_data.csv`.
- If you later get X API access, export your post search results into the same CSV shape.

Official Kalshi docs used here:

- Market discovery: https://docs.kalshi.com/api-reference/market/get-markets
- Live candles: https://docs.kalshi.com/api-reference/market/get-market-candlesticks
- Historical data overview: https://docs.kalshi.com/getting_started/historical_data
- Historical candles: https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks

## Pull Kalshi Data

The project is configured for an hourly workflow by default:

- Kalshi candles: `--period-interval 60`
- Notebook aggregation: `AGG_FREQ = "1H"`
- Prediction horizons: `HORIZONS = [1, 3, 7]`


Download live candles for a chosen market:

```bash
python scripts/fetch_kalshi_market_data.py \
  --endpoint live \
  --series-ticker YOUR_SERIES_TICKER \
  --market-ticker YOUR_MARKET_TICKER \
  --start 2024-10-01T00:00:00Z \
  --end 2024-11-06T00:00:00Z \
  --period-interval 60
```

Download archived candles for an older settled market:

```bash
python scripts/fetch_kalshi_market_data.py \
  --endpoint historical \
  --market-ticker YOUR_MARKET_TICKER \
  --start 2024-10-01T00:00:00Z \
  --end 2024-11-06T00:00:00Z \
  --period-interval 60
```

Both commands write notebook-ready data to `data/raw/market_data.csv` by default. For this particular project, we used this command to get the Kalshi Market Data for the 2024 presidential election given that Kamala Harris would win:

```bash
python scripts/fetch_kalshi_market_data.py \
  --endpoint historical \
  --market-ticker PRES-2024-KH \
  --start 2024-10-01T00:00:00Z \
  --end 2024-11-06T00:00:00Z \
  --period-interval 1440 \
  --event-id election_2024 \
  --out data/raw/market_data-KH.csv

```

## Public Election Dataset

We used a public dataset from `sinking8/x-24-us-election` instead of scraping X directly, which is an extremely large download which we had problems with. To combat that, weread the data directly from the Hugging Face mirror. By creating a script we were able to read the data and filter out relevant tweets based on timestamp and specific keywords (which you can leave blank if you do not want to flter for words). This is how you can use this script:

```bash
python scripts/prepare_election_dataset.py \
  --hf-dataset deadbirds/usc-x-24-us-election-parquet \
  --hf-split train \
  --streaming \
  --start 2024-10-01T00:00:00Z \
  --end 2024-12-01T00:00:00Z \
  --event-id election_2024 \
  --keywords kamala harris democrat democrats trump election poll debate president \
  --out data/raw/tweets_data.csv
```

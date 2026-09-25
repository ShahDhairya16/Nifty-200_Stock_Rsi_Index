# Deploying the NIFTY 200 RSI dashboard

The Streamlit entry point is `frontend/streamlit_app.py`. It reads existing stock, price, and RSI records from MongoDB. It does not run a historical backfill or recompute all RSI data at startup. The sidebar's **Refresh & Update Data** action explicitly checks missing weekdays, fetches NSE Bhavcopy data, stores NIFTY 200 prices, and recomputes RSI when new prices arrive. NSE does not publish data for every weekday (market holidays are skipped).

## Local development

From the repository root:

```bash
python -m venv venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source venv/bin/activate
```

Install dependencies and start Streamlit from the repository root:

```bash
pip install -r requirements.txt
streamlit run frontend/streamlit_app.py
```

The current Community Cloud default is Python 3.12. No `runtime.txt` is included so Cloud can use its supported default; the app's dependencies should be validated under Python 3.12 before deployment.

## Configuration

For local use, copy `.env.example` to `.env` and set the values you need. The configuration lookup order is Streamlit secrets, environment variables, then defaults; `python-dotenv` loads `.env` for local development. The default URI remains `mongodb://localhost:27017/`.

| Name | Purpose | Default |
| --- | --- | --- |
| `MONGO_URI` | MongoDB connection URI | `mongodb://localhost:27017/` |
| `MONGO_DB_NAME` | Database name | `cnx200_rsi_dashboard` |
| `LOG_LEVEL` | Python logging level | `INFO` |
| `HISTORICAL_START_DATE` | Optional default start date for historical backfills (`YYYY-MM-DD`) | Empty (one year ago) |
| `HISTORICAL_END_DATE` | Optional default end date for historical backfills (`YYYY-MM-DD`) | Empty (today) |
| `NSE_MAX_RETRIES` | Number of NSE request attempts | `3` |
| `NSE_RETRY_MIN_WAIT` | Minimum exponential retry wait, seconds | `2` |
| `NSE_RETRY_MAX_WAIT` | Maximum exponential retry wait, seconds | `10` |

Keep `.env` and `.streamlit/secrets.toml` out of Git. `.streamlit/secrets.toml.example` is a placeholder template only.

## MongoDB Atlas setup

1. Create a MongoDB Atlas cluster.
2. Create a database user with a strong password and only the permissions required for this app.
3. Configure Atlas Network Access to allow connections from Streamlit Community Cloud. For a public Community Cloud app, Atlas may require a broad IP range because the app's outbound address is not a fixed client IP; use the narrowest range Atlas and your hosting setup allow.
4. Copy the cluster's application connection string and replace its username/password placeholders. URL-encode special characters in the password.
5. Put the URI in the Streamlit Cloud Secrets field as `MONGO_URI`; do not commit it or send it to clients.

## Initial Atlas population

The database commands are defined in `main.py`. Run these from a local checkout configured to point to Atlas in `.env` (or set `MONGO_URI` and `MONGO_DB_NAME` in the shell). The order for a fresh database is:

```bash
python main.py --init-db
python main.py --sync-universe
python main.py --backfill-historical
python main.py --compute-rsi
```

The backfill defaults to the last year and processes all active NIFTY 200 stocks, so it can take a while. You can provide `--start-date YYYY-MM-DD --end-date YYYY-MM-DD` to limit the range. These operations are intentionally manual and must not be run as part of website startup. To migrate the repository's legacy CSV/JSON files instead, `python scripts/migrate_to_mongodb.py` initializes indexes and upserts those local files; inspect the files and target database first. `--recover-missing` is a historical range backfill alias in the current code, not the dashboard's daily Bhavcopy updater.

## Streamlit Community Cloud

Deploy these settings from [share.streamlit.io](https://share.streamlit.io/):

- Repository: `ShahDhairya16/Nifty-200_Stock_Rsi_Index`
- Branch: `main`
- Main file: `frontend/streamlit_app.py`
- Python: choose 3.12 in Advanced settings (the current Community Cloud default)

Paste the following TOML in the app's **Advanced settings → Secrets**, replacing only the placeholder URI with your Atlas connection string:

```toml
MONGO_URI = "mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority"
MONGO_DB_NAME = "cnx200_rsi_dashboard"
LOG_LEVEL = "INFO"
HISTORICAL_START_DATE = ""
HISTORICAL_END_DATE = ""
NSE_MAX_RETRIES = 3
NSE_RETRY_MIN_WAIT = 2
NSE_RETRY_MAX_WAIT = 10
```

After saving secrets, deploy the app. The dashboard pages show a safe user-facing database error when database access fails. Confirm Atlas network access and credentials in Cloud settings if the connection cannot be established.

## Production smoke checklist

- The public HTTPS URL opens and the dashboard pages render.
- Atlas accepts the Cloud app connection; the expected database and collections exist.
- Stock list and latest RSI rankings are populated, and dates match the imported data.
- Stock filters, chart ranges, and RSI rankings respond as expected.
- The Reports page generates and downloads an `.xlsx` workbook.
- **Refresh & Update Data** can be explicitly invoked; inspect its summary and logs if NSE has an outage or no new market data is available.
- Opening or reloading the website does not start a historical backfill.
- No MongoDB credentials are committed to Git or shown to clients.

This repository preparation does not deploy the app. GitHub, Streamlit Cloud, and Atlas account access and production credentials are required for the remaining account-level steps.

"""Simple scheduled client to fetch forex data and store into MySQL.

The scheduler intervals are configured via the ``FETCH_INTERVALS``
environment variable (comma separated minutes). Database connection
details are also taken from the environment.  This client uses the
``forexpy`` sources directly to obtain data and persists it using
``pandas.to_sql``.

Example environment variables (see `.env.example`):

```
DB_HOST=db
DB_PORT=3306
DB_USER=root
DB_PASSWORD=example
DB_NAME=forex
DB_TABLE=forex_data
FETCH_INTERVALS=1,2,3,5,15,30,60
SYMBOL=EURUSD
START_DATE=20220101
```
"""

from __future__ import annotations

import os
import sys
import time
from typing import List

import pandas as pd
import schedule
from sqlalchemy import create_engine, text

# Add path so ``sources`` can be imported without installation
SRC_PATH = os.path.join(os.path.dirname(__file__), "forexpy", "src")
sys.path.append(SRC_PATH)

from sources.dukascopy import fetch_from_dukascopy  # type: ignore  # noqa:E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "example")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_TABLE = os.getenv("DB_TABLE", "forex_data")

SYMBOL = os.getenv("SYMBOL", "EURUSD")
START_DATE = os.getenv("START_DATE", "20220101")
END_DATE = os.getenv("END_DATE", "")


def _parse_intervals(env_var: str) -> List[int]:
    """Return list of minute intervals from comma separated string."""

    values: List[int] = []
    for item in env_var.split(","):
        item = item.strip()
        if item.isdigit():
            values.append(int(item))
    return values or [1]


FETCH_INTERVALS = _parse_intervals(os.getenv("FETCH_INTERVALS", "1"))


def get_engine():
    """Create the SQLAlchemy engine and ensure database/table exist."""

    root_engine = create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}"
    )
    with root_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))

    engine = create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    create_table_sql = text(
        f"""
        CREATE TABLE IF NOT EXISTS `{DB_TABLE}` (
            date DATETIME,
            ask FLOAT,
            bid FLOAT,
            ask_vol FLOAT,
            bid_vol FLOAT
        )
        """
    )
    with engine.connect() as conn:
        conn.execute(create_table_sql)

    return engine


ENGINE = get_engine()


def fetch_and_store(interval: int) -> None:
    """Fetch data and save it to MySQL."""

    df: pd.DataFrame = fetch_from_dukascopy(
        SYMBOL, START_DATE, END_DATE, tf="1m", keep="F"
    )
    if df.empty:
        print("No data fetched")
        return

    df.to_sql(DB_TABLE, con=ENGINE, if_exists="append", index=False)
    print(f"Stored {len(df)} rows for interval {interval}m")


for interval in FETCH_INTERVALS:
    schedule.every(interval).minutes.do(fetch_and_store, interval)


if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(1)


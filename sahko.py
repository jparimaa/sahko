#!/usr/bin/env python3
import requests
import pandas as pd
import json
import time
import datetime

# use zoneinfo when available (py3.9+). Fallback to naive +2h if not.
try:
    from zoneinfo import ZoneInfo
    HAVE_ZONEINFO = True
except Exception:
    HAVE_ZONEINFO = False

def to_local(dt_utc):
    """Convert a timezone-aware UTC datetime to Europe/Helsinki (or +02:00 fallback)."""
    if HAVE_ZONEINFO:
        return dt_utc.astimezone(ZoneInfo("Europe/Helsinki"))
    else:
        return dt_utc + datetime.timedelta(hours=2)

def parse_iso(s):
    """Parse ISO8601 timestamp strings like '2025-10-07T21:45:00.000Z' to tz-aware datetime."""
    # replace Z with +00:00 so fromisoformat yields an aware datetime
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

def log(msg):
    date = datetime.datetime.now()
    stamped_msg = f"{date}: {msg}"
    print(stamped_msg)
    with open("sahko.log", "a", encoding="utf-8") as myfile:
        myfile.write(stamped_msg + "\n")

def sleep_until_17():
    t = datetime.datetime.today()
    future = datetime.datetime(t.year, t.month, t.day, 17, 0)
    if t.hour >= 17:
        future += datetime.timedelta(days=1)
    log("Sleeping until " + str(future) + " and after that query new data")
    sleep_time = (future - t).total_seconds()
    time.sleep(sleep_time)

URL = "https://api.porssisahko.net/v2/latest-prices.json"
log("This program will get the latest electricity prices from {} and write the data to an excel file called hinnat.xlsx. " \
"The file should not be open at the time of writing. Data is queried at program startup and then daily at 17:00.".format(URL))

filename = "hinnat.xlsx"

while True:
    try:
        response = requests.get(URL)
    except Exception as e:
        log(f"ERROR: network error when requesting data - {e}. Trying again in 15 minutes.")
        time.sleep(15*60)
        continue

    if response.status_code != 200:
        log(f"ERROR: Unable to get data from server. Return code = {response.status_code}. Trying again in 15 minutes.")
        time.sleep(15*60)
        continue

    log(f"Data obtained from {URL}")
    try:
        json_data = response.json()
    except ValueError as e:
        log(f"ERROR: Failed to decode JSON - {e}. Dumping raw response.")
        with open("latest_prices.raw", "wb") as f:
            f.write(response.content)
        time.sleep(15*60)
        continue

    dates = []
    times = []
    prices = []
    last_date = None

    for price_data in json_data.get("prices", []):
        price = price_data.get("price")
        start_dt_utc = parse_iso(price_data["startDate"])
        end_dt_utc = parse_iso(price_data["endDate"])
        start_local = to_local(start_dt_utc)
        end_local = to_local(end_dt_utc)

        # round up end time to next minute if it contains seconds/microseconds (so 21:59:59.999 -> 22:00)
        if end_local.second != 0 or end_local.microsecond != 0:
            end_local = end_local + datetime.timedelta(minutes=1)
            end_local = end_local.replace(second=0, microsecond=0)

        time_str = f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}"

        # Show date only once per day (first row for that date), otherwise blank
        start_date_only = start_local.date()
        if start_date_only != last_date:
            date_str = start_local.strftime("%Y-%m-%d")
            last_date = start_date_only
        else:
            date_str = ""

        dates.append(date_str)
        times.append(time_str)
        prices.append(price)

    d = {"pvm": dates, "klo": times, "hinta snt / kWh, sis. alv.": prices}
    df = pd.DataFrame(data=d)

    log("Writing latest data to " + filename)
    try:
        df.to_excel(filename, index=False)
        log("File write completed")
        sleep_until_17()
    except PermissionError:
        log("ERROR: Permission error - Unable to write file. Maybe the file is already open? Trying again in 15 minutes.")
        time.sleep(15*60)
    except FileNotFoundError:
        log("ERROR: File not found error - Check if the directory exists.")
    except ValueError as e:
        log(f"ERROR: Value error - {e}")
    except OSError as e:
        log(f"ERROR: OS error - {e}")
    except Exception as e:
        log(f"ERROR: An unexpected error occurred - {e}")

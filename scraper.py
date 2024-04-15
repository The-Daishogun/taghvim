import httpx
from bs4 import BeautifulSoup
import json
import tqdm
import time
from pathlib import Path
import os
import jdatetime
from itertools import product

import tqdm.asyncio

TIME_IR_URL = "https://www.time.ir/"
PERSIAN_DIGITS = {
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
}


def convert_persian_to_english(text):
    english_text = ""
    for char in text.strip():
        english_text += PERSIAN_DIGITS[char]
    return english_text


def is_text_english(value: str) -> bool:
    try:
        value.encode(encoding="utf-8").decode("ascii")
        return True
    except UnicodeDecodeError:
        return False


def get_data_key(
    year_jalali: int | str, month_jalali: int | str, day_jalali: int | str
):
    return f"{year_jalali}/{month_jalali}/{day_jalali}"


def get_data_for_month(year_jalali: int, month_jalali: int, client: httpx.Client):
    payload = {
        "Year": year_jalali,
        "Month": month_jalali,
        "Base1": 0,
        "Base2": 1,
        "Base3": 2,
        "Responsive": True,
    }

    while True:
        try:
            response = client.post(TIME_IR_URL, data=payload)
            if response.status_code == httpx.codes.OK:
                break
        except httpx.TimeoutException:
            pass
        print("Error, Status:", response.status_code, "sleeping for 1 second...")
        time.sleep(1)

    soup = BeautifulSoup(response.text, "html.parser")
    event_list = soup.find("ul", {"class": "list-unstyled"})
    lis = event_list.find_all("li")
    data = {}
    for li in lis:
        _, date_str, event_name, details, *_ = list(li.children)
        day_jalali = convert_persian_to_english(date_str.text[:2])
        event = event_name.text.strip()
        details: str = details.text.replace("[", "").replace("]", "").strip()
        is_holiday = "eventHoliday" in li.attrs.get("class", "")
        is_religious = not is_text_english(details) if details else False

        key = get_data_key(year_jalali, month_jalali, day_jalali)
        data[key] = data.get(key, []) + [
            {
                "is_holiday": is_holiday,
                "is_religious": is_religious,
                "event": event,
                "details": details if details else None,
            }
        ]
    return data


def main(start_year: int, target_year: int, out_dir: Path):
    with httpx.Client(http2=True) as httpx_client:
        jobs_todo = product(range(start_year, target_year), range(1, 13))
        for year, month in tqdm.tqdm(
            jobs_todo,
            desc="Scraping time.ir",
            total=(target_year - start_year) * 12,
            colour="green",
        ):
            year_path = out_dir / str(year)
            year_path.mkdir(parents=True, exist_ok=True)
            month_data = get_data_for_month(year, month, httpx_client)
            with open(year_path / f"{month}.json", "w") as file:
                file.write(json.dumps(month_data, ensure_ascii=False))


if __name__ == "__main__":
    start_from = os.getenv("START_FROM", None)
    if start_from is None:
        raise ValueError(
            "START_FROM cannot be None. did you forget to set the environment variable START_FROM?\npossible values for first argument are: today / beginning"
        )
    elif start_from not in ["today", "beginning"]:
        raise ValueError("possible values for first argument are: today / beginning")

    if start_from == "today":
        START_YEAR = jdatetime.date.today().year
    else:
        START_YEAR = 1

    TARGET_YEAR = os.getenv("TARGET_YEAR", None)
    if TARGET_YEAR is None:
        raise ValueError(
            "TARGET_YEAR cannot be None. did you forget to set the environment variable TARGET_YEAR?\nit should be an integer."
        )
    if not TARGET_YEAR.isdigit():
        raise ValueError("second argument must be an integer")
    TARGET_YEAR = int(TARGET_YEAR)

    if START_YEAR > TARGET_YEAR or START_YEAR == TARGET_YEAR:
        raise ValueError("target year must be greater than start year")

    OUT_DIR = Path("./out")

    main(START_YEAR, TARGET_YEAR, OUT_DIR)

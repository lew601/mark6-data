#!/usr/bin/env python3
# marksix_full_crawler.py

import requests
import json
import os
import sys
import time
import argparse
from datetime import date, datetime, timedelta, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://info.cld.hkjc.com/graphql/base/"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20
HISTORY_LIMIT = 120
ARCHIVE_FILENAME = "docs/archive/marksix_history.json"
ARCHIVE_START_DATE = date(1993, 1, 1)
ARCHIVE_WINDOW_DAYS = 60
# A short overlap window is enough for frequent scheduled updates while
# covering delayed or missed GitHub Actions runs.
RECENT_UPDATE_DAYS = 7
ARCHIVE_REQUEST_DELAY_SECONDS = 0.25
GRAPHQL_ATTEMPTS = 3
GRAPHQL_RETRY_DELAY_SECONDS = 2

HEADERS_RESULTS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://bet.hkjc.com",
    "Referer": "https://bet.hkjc.com/ch/marksix/results",
}

HEADERS_HOME = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://bet.hkjc.com",
    "Referer": "https://bet.hkjc.com/ch/marksix/home",
}

DRAWS_FRAGMENT = """
fragment lotteryDrawsFragment on LotteryDraw {
  id
  year
  no
  openDate
  closeDate
  drawDate
  status
  snowballCode
  snowballName_en
  snowballName_ch
  lotteryPool {
    sell
    status
    totalInvestment
    jackpot
    unitBet
    estimatedPrize
    derivedFirstPrizeDiv
    lotteryPrizes {
      type
      winningUnit
      dividend
    }
  }
  drawResult {
    drawnNo
    xDrawnNo
  }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1) 完整歷史查詢 (marksixResult)
QUERY_HISTORY = DRAWS_FRAGMENT + """
query marksixResult($lastNDraw: Int, $startDate: String, $endDate: String, $drawType: LotteryDrawType) {
  lotteryDraws(
    lastNDraw: $lastNDraw
    startDate: $startDate
    endDate: $endDate
    drawType: $drawType
  ) {
    ...lotteryDrawsFragment
  }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 2) 完整「上期/下期 + timeOffset」查詢 (marksixDraw)
QUERY_DRAWS = DRAWS_FRAGMENT + """
query marksixDraw {
  timeOffset {
    m6
    ts
  }
  lotteryDraws {
    ...lotteryDrawsFragment
  }
}
"""


def build_session():
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def graphql_request(session, operation_name, query, variables, headers):
    payload = {
        "operationName": operation_name,
        "query": query,
        "variables": variables,
    }

    for attempt in range(1, GRAPHQL_ATTEMPTS + 1):
        try:
            resp = session.post(
                URL,
                json=payload,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            if attempt == GRAPHQL_ATTEMPTS:
                raise RuntimeError(f"{operation_name} request failed") from exc
            print(
                f"{operation_name}: request failed on attempt {attempt}/{GRAPHQL_ATTEMPTS}, retrying...",
                file=sys.stderr,
            )
            time.sleep(GRAPHQL_RETRY_DELAY_SECONDS * attempt)
            continue

        try:
            js = resp.json()
        except ValueError as exc:
            if attempt == GRAPHQL_ATTEMPTS:
                raise RuntimeError(f"{operation_name} returned invalid JSON") from exc
            print(
                f"{operation_name}: invalid JSON on attempt {attempt}/{GRAPHQL_ATTEMPTS}, retrying...",
                file=sys.stderr,
            )
            time.sleep(GRAPHQL_RETRY_DELAY_SECONDS * attempt)
            continue

        if "errors" in js:
            if attempt == GRAPHQL_ATTEMPTS:
                raise RuntimeError(f"{operation_name} failed: {js['errors']}")
            print(
                f"{operation_name}: response contained errors on attempt {attempt}/{GRAPHQL_ATTEMPTS}, retrying...",
                file=sys.stderr,
            )
            time.sleep(GRAPHQL_RETRY_DELAY_SECONDS * attempt)
            continue

        data = js.get("data")
        if data is not None:
            return data

        if attempt == GRAPHQL_ATTEMPTS:
            raise RuntimeError(f"{operation_name} response is missing data")
        print(
            f"{operation_name}: response missing data on attempt {attempt}/{GRAPHQL_ATTEMPTS}, retrying...",
            file=sys.stderr,
        )
        time.sleep(GRAPHQL_RETRY_DELAY_SECONDS * attempt)

    raise RuntimeError(f"{operation_name} failed after retries")


def draw_sort_key(draw):
    return (draw.get("drawDate") or "", draw.get("no") or -1)


def draw_sort_key(draw):
    return (draw.get("drawDate") or "", draw.get("no") or -1)


def has_drawn_numbers(draw):
    result = draw.get("drawResult") if isinstance(draw, dict) else None
    drawn_numbers = result.get("drawnNo") if isinstance(result, dict) else None
    return isinstance(drawn_numbers, list) and bool(drawn_numbers)


def normalize_prizes(prizes):
    if not isinstance(prizes, list):
        return

    for prize in prizes:
        if not isinstance(prize, dict):
            continue

        raw = prize.get("winningUnit", 0)
        try:
            prize["winningUnit"] = round(float(raw) / 10, 1)
        except (TypeError, ValueError):
            prize["winningUnit"] = 0.0


def pick_draws(draws_data):
    draws = draws_data.get("lotteryDraws")
    if not isinstance(draws, list) or len(draws) < 2:
        raise RuntimeError("marksixDraw returned fewer than 2 lotteryDraws")

    sorted_draws = sorted(draws, key=draw_sort_key)
    last_draw = next(
        (
            draw
            for draw in reversed(sorted_draws)
            if draw.get("status") == "Result" or has_drawn_numbers(draw)
        ),
        None,
    )
    next_draw = next(
        (
            draw
            for draw in sorted_draws
            if draw.get("id") != (last_draw or {}).get("id")
            and not has_drawn_numbers(draw)
        ),
        None,
    )

    if last_draw is not None and next_draw is not None:
        return last_draw, next_draw

    return sorted_draws[-2], sorted_draws[-1]


def fetch_history(session, last_n=HISTORY_LIMIT):
    """Fetch the most recent `last_n` draws in bounded date windows."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=ARCHIVE_WINDOW_DAYS - 1)
    draws_by_id = {}

    while len(draws_by_id) < last_n and end_date >= ARCHIVE_START_DATE:
        for draw in fetch_history_window(session, start_date, end_date):
            draw_id = draw.get("id")
            if draw_id:
                draws_by_id[draw_id] = draw

        if len(draws_by_id) >= last_n:
            break

        end_date = start_date - timedelta(days=1)
        start_date = max(
            ARCHIVE_START_DATE,
            end_date - timedelta(days=ARCHIVE_WINDOW_DAYS - 1),
        )
        time.sleep(ARCHIVE_REQUEST_DELAY_SECONDS)

    return sorted(draws_by_id.values(), key=draw_sort_key, reverse=True)[:last_n]


def fetch_history_window(session, start_date, end_date):
    """Fetch result draws for one date window accepted by HKJC."""
    data = graphql_request(
        session,
        "marksixResult",
        QUERY_HISTORY,
        {
            "lastNDraw": None,
            "startDate": start_date.strftime("%Y%m%d"),
            "endDate": end_date.strftime("%Y%m%d"),
            "drawType": "All",
        },
        HEADERS_RESULTS,
    )
    draws = data.get("lotteryDraws")
    if not isinstance(draws, list):
        raise RuntimeError("marksixResult response is missing lotteryDraws")
    return sorted(draws, key=draw_sort_key, reverse=True)


def fetch_full_history(session, start_date=ARCHIVE_START_DATE, end_date=None):
    """Fetch the complete available history in bounded date windows."""
    end_date = end_date or datetime.now(timezone.utc).date()
    all_draws = {}
    window_start = start_date

    while window_start <= end_date:
        window_end = min(
            window_start + timedelta(days=ARCHIVE_WINDOW_DAYS - 1),
            end_date,
        )
        print(
            f"Fetching history window "
            f"{window_start:%Y-%m-%d} to {window_end:%Y-%m-%d}",
            file=sys.stderr,
        )
        for draw in fetch_history_window(session, window_start, window_end):
            draw_id = draw.get("id")
            if draw_id:
                all_draws[draw_id] = draw
        window_start = window_end + timedelta(days=1)
        if window_start <= end_date:
            time.sleep(ARCHIVE_REQUEST_DELAY_SECONDS)

    return sorted(all_draws.values(), key=draw_sort_key, reverse=True)


def merge_history(existing, updates):
    """Merge draws by id, preferring the newest response."""
    merged = {
        draw.get("id"): draw
        for draw in existing
        if isinstance(draw, dict) and draw.get("id")
    }
    for draw in updates:
        draw_id = draw.get("id") if isinstance(draw, dict) else None
        if draw_id:
            merged[draw_id] = merge_draw_data(merged.get(draw_id), draw)
    return sorted(merged.values(), key=draw_sort_key, reverse=True)


def merge_draw_data(existing, update):
    """Merge a newer draw response without discarding known fields."""
    if isinstance(existing, dict) and isinstance(update, dict):
        merged = dict(existing)
        for key, value in update.items():
            merged[key] = merge_draw_data(merged.get(key), value)
        return merged

    if isinstance(existing, list) and isinstance(update, list):
        if not update:
            return existing

        if all(isinstance(item, dict) and item.get("type") is not None for item in update):
            existing_by_type = {
                item.get("type"): item
                for item in existing
                if isinstance(item, dict) and item.get("type") is not None
            }
            merged = [
                merge_draw_data(existing_by_type.get(item.get("type")), item)
                if item.get("type") in existing_by_type
                else item
                for item in update
            ]
            updated_types = {item.get("type") for item in update}
            merged.extend(
                item
                for item in existing
                if isinstance(item, dict)
                and item.get("type") is not None
                and item.get("type") not in updated_types
            )
            return merged

        return update

    if update is None or update == "":
        return existing
    return update


def normalize_history(history):
    for draw in history:
        pool = draw.get("lotteryPool", {})
        normalize_prizes(pool.get("lotteryPrizes", []))


def load_archive(filename=ARCHIVE_FILENAME):
    if not os.path.exists(filename):
        return []
    with open(filename, encoding="utf-8") as f:
        archive = json.load(f)
    history = archive.get("history") if isinstance(archive, dict) else None
    if not isinstance(history, list):
        raise RuntimeError(f"{filename} has an invalid archive schema")
    return history


def write_json_atomic(payload, filename):
    output_dir = os.path.dirname(filename)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    temporary = f"{filename}.tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temporary, filename)


def save_archive(history, filename=ARCHIVE_FILENAME):
    write_json_atomic(
        {
            "schemaVersion": 1,
            "source": "HKJC",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "history": history,
        },
        filename,
    )


def fetch_draws(session):
    """Fetch both lastDraw, nextDraw and timeOffset in one go."""
    return graphql_request(session, "marksixDraw", QUERY_DRAWS, {}, HEADERS_HOME)


def save_full(history, draws_data, filename="docs/marksix_all.json"):
    """Combine history and draws_data into one JSON and save."""
    output_dir = os.path.dirname(filename)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    last_draw, next_draw = pick_draws(draws_data)
    history_by_id = {
        draw.get("id"): draw
        for draw in history
        if isinstance(draw, dict) and draw.get("id")
    }
    last_draw = merge_draw_data(history_by_id.get(last_draw.get("id")), last_draw)
    time_offset = draws_data.get("timeOffset")
    if not isinstance(time_offset, dict):
        raise RuntimeError("marksixDraw response is missing timeOffset")

    all_out = {
        "timeOffset": time_offset,
        "lastDraw": last_draw,
        "nextDraw": next_draw,
        "history": history,
    }

    # 调整 lastDraw
    last_pool = all_out["lastDraw"].get("lotteryPool", {})
    normalize_prizes(last_pool.get("lotteryPrizes", []))

    # 调整 nextDraw
    next_pool = all_out["nextDraw"].get("lotteryPool", {})
    normalize_prizes(next_pool.get("lotteryPrizes", []))

    write_json_atomic(all_out, filename)

    print(f"Saved combined data to {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill-history",
        action="store_true",
        help="Fetch all available history from 1993 in date windows.",
    )
    args = parser.parse_args()

    try:
        with build_session() as session:
            today = datetime.now(timezone.utc).date()
            if args.backfill_history:
                archive_history = fetch_full_history(session)
                normalize_history(archive_history)
                history = archive_history[:HISTORY_LIMIT]
            else:
                archive_history = load_archive()
                if not archive_history:
                    raise RuntimeError(
                        "History archive is missing; run with "
                        "--backfill-history first"
                    )
                recent_history = fetch_history_window(
                    session,
                    today - timedelta(days=RECENT_UPDATE_DAYS - 1),
                    today,
                )
                normalize_history(recent_history)
                archive_history = merge_history(
                    archive_history,
                    recent_history,
                )
            draws_data = fetch_draws(session)
            live_last_draw, _ = pick_draws(draws_data)
            if has_drawn_numbers(live_last_draw):
                normalize_history([live_last_draw])
                archive_history = merge_history(
                    archive_history,
                    [live_last_draw],
                )
            history = archive_history[:HISTORY_LIMIT]
        save_archive(archive_history)
        save_full(history, draws_data)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)

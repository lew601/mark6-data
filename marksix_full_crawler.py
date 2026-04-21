#!/usr/bin/env python3
# marksix_full_crawler.py

import requests
import json
import os
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://info.cld.hkjc.com/graphql/base/"
REQUEST_TIMEOUT = 10
HISTORY_LIMIT = 120

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
    resp = session.post(URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    try:
        js = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation_name} returned invalid JSON") from exc

    if "errors" in js:
        raise RuntimeError(f"{operation_name} failed: {js['errors']}")

    data = js.get("data")
    if data is None:
        raise RuntimeError(f"{operation_name} response is missing data")

    return data


def normalize_prizes(prizes):
    for prize in prizes:
        raw = prize.get("winningUnit", 0)
        prize["winningUnit"] = round(raw / 10, 1)


def pick_draws(draws_data):
    draws = draws_data.get("lotteryDraws")
    if not isinstance(draws, list) or len(draws) < 2:
        raise RuntimeError("marksixDraw returned fewer than 2 lotteryDraws")

    sorted_draws = sorted(draws, key=lambda draw: draw.get("drawDate") or "")
    return sorted_draws[0], sorted_draws[-1]


def fetch_history(session, last_n=HISTORY_LIMIT):
    """Fetch the most recent `last_n` draws (history)."""
    data = graphql_request(
        session,
        "marksixResult",
        QUERY_HISTORY,
        {
            "lastNDraw": last_n,
            "startDate": None,
            "endDate": None,
            "drawType": "All",
        },
        HEADERS_RESULTS,
    )
    draws = data.get("lotteryDraws")
    if not isinstance(draws, list):
        raise RuntimeError("marksixResult response is missing lotteryDraws")
    return draws


def fetch_draws(session):
    """Fetch both lastDraw, nextDraw and timeOffset in one go."""
    return graphql_request(session, "marksixDraw", QUERY_DRAWS, {}, HEADERS_HOME)


def save_full(history, draws_data, filename="docs/marksix_all.json"):
    """Combine history and draws_data into one JSON and save."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    last_draw, next_draw = pick_draws(draws_data)
    time_offset = draws_data.get("timeOffset")
    if not isinstance(time_offset, dict):
        raise RuntimeError("marksixDraw response is missing timeOffset")

    all_out = {
        "timeOffset": time_offset,
        "lastDraw": last_draw,
        "nextDraw": next_draw,
        "history": history,
    }

    # 调整 history 里每一期的奖池
    for draw in all_out["history"]:
        pool = draw.get("lotteryPool", {})
        normalize_prizes(pool.get("lotteryPrizes", []))

    # 调整 lastDraw
    last_pool = all_out["lastDraw"].get("lotteryPool", {})
    normalize_prizes(last_pool.get("lotteryPrizes", []))

    # 调整 nextDraw
    next_pool = all_out["nextDraw"].get("lotteryPool", {})
    normalize_prizes(next_pool.get("lotteryPrizes", []))

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_out, f, ensure_ascii=False, indent=2)

    print(f"Saved combined data to {filename}")


if __name__ == "__main__":
    try:
        with build_session() as session:
            history = fetch_history(session)
            draws_data = fetch_draws(session)
        save_full(history, draws_data)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)

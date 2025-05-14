#!/usr/bin/env python3
# marksix_full_crawler.py

import requests
import json
import os
import sys

URL = "https://info.cld.hkjc.com/graphql/base/"

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

# ─────────────────────────────────────────────────────────────────────────────
# 1) 完整「歷史 30 期」查詢 (marksixResult)
QUERY_HISTORY = """
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
QUERY_DRAWS = """
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

def fetch_history(last_n=30):
    """Fetch the most recent `last_n` draws (history)."""
    payload = {
        "operationName": "marksixResult",
        "query": QUERY_HISTORY,
        "variables": {
            "lastNDraw": last_n,
            "startDate": None,
            "endDate": None,
            "drawType": "All"
        }
    }
    resp = requests.post(URL, json=payload, headers=HEADERS_RESULTS, timeout=10)
    resp.raise_for_status()
    js = resp.json()
    if "errors" in js:
        raise RuntimeError(js["errors"])
    return js["data"]["lotteryDraws"]

def fetch_draws():
    """Fetch both lastDraw, nextDraw and timeOffset in one go."""
    payload = {
        "operationName": "marksixDraw",
        "query": QUERY_DRAWS,
        "variables": {}
    }
    resp = requests.post(URL, json=payload, headers=HEADERS_HOME, timeout=10)
    resp.raise_for_status()
    js = resp.json()
    if "errors" in js:
        raise RuntimeError(js["errors"])
    return js["data"]

def save_full(history, draws_data, filename="docs/marksix_all.json"):
    """Combine history and draws_data into one JSON and save."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # draws_data["lotteryDraws"][0] is lastDraw; [1] is nextDraw
    all_out = {
        "timeOffset":   draws_data["timeOffset"],
        "lastDraw":     draws_data["lotteryDraws"][0],
        "nextDraw":     draws_data["lotteryDraws"][1],
        "history":      history
    }

    def adjust(prizes):
        for p in prizes:
            raw = p.get("winningUnit", 0)
            # 除以 10 并保留1位小数
            p["winningUnit"] = round(raw / 10, 1)

    # 调整 history 里每一期的奖池
    for draw in all_out["history"]:
        pool = draw.get("lotteryPool", {})
        adjust(pool.get("lotteryPrizes", []))

    # 调整 lastDraw
    last_pool = all_out["lastDraw"].get("lotteryPool", {})
    adjust(last_pool.get("lotteryPrizes", []))

    # 调整 nextDraw
    next_pool = all_out["nextDraw"].get("lotteryPool", {})
    adjust(next_pool.get("lotteryPrizes", []))

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_out, f, ensure_ascii=False, indent=2)

    print(f"Saved combined data to {filename}")

if __name__ == "__main__":
    try:
        history    = fetch_history(30)
        draws_data = fetch_draws()
        save_full(history, draws_data)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)

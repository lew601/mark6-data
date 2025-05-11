import requests
import json
import sys

# endpoint
URL = "https://info.cld.hkjc.com/graphql/base/"

# 完整 copy 自 DevTools 的 query + fragment
QUERY = """
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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://bet.hkjc.com",
    "Referer": "https://bet.hkjc.com/ch/marksix/results",
}


def fetch_draws(last_n=30, start_date=None, end_date=None, draw_type="All"):
    payload = {
        "operationName": "marksixResult",
        "query": QUERY,
        "variables": {
            "lastNDraw": last_n,
            "startDate": start_date,
            "endDate": end_date,
            "drawType": draw_type
        }
    }
    resp = requests.post(URL, json=payload, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["lotteryDraws"]


def save_json(draws, filename="marksix_last30.json"):
    output = []
    for d in draws:
        period = f"{d['year']}-{int(d['no']):03d}"
        output.append({
            "period": period,
            "drawDate": d["drawDate"],
            "numbers": d["drawResult"]["drawnNo"],
            "special": d["drawResult"]["xDrawnNo"]
        })
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已儲存最近 {len(output)} 期至 {filename}")


if __name__ == "__main__":
    try:
        draws = fetch_draws(last_n=30)
        save_json(draws)
    except Exception as e:
        print("發生錯誤：", e, file=sys.stderr)
        sys.exit(1)

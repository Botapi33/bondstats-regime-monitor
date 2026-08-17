import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ["FRED_API_KEY"]

SERIES = {
    "policy": "DGS2",
    "long_yield": "DGS10",
    "real_yield": "DFII10",
    "credit": "NFCICREDIT",
    "inflation": "T5YIE",
}

def fred(series_id):
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": "2024-01-01",
        "sort_order": "asc",
    })

    url = (
        "https://api.stlouisfed.org/fred/series/observations?"
        + params
    )

    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)

    points = []

    for obs in data["observations"]:
        if obs["value"] == ".":
            continue

        points.append({
            "date": obs["date"],
            "value": float(obs["value"]),
        })

    return points

def latest(points):
    return points[-1]

def lag(points, periods):
    if len(points) <= periods:
        return points[0]
    return points[-1-periods]

def change(points, periods):
    return latest(points)["value"] - lag(points, periods)["value"]

def policy_signal(points):
    current = latest(points)["value"]
    d20 = change(points, 20)

    if d20 <= -0.25:
        return {
            "label": "EASING PRICED",
            "tone": "positive",
            "detail": f"{d20:.2f} pp / 20 sessions",
        }

    if d20 >= 0.25:
        return {
            "label": "TIGHTENING PRICED",
            "tone": "negative",
            "detail": f"+{d20:.2f} pp / 20 sessions",
        }

    return {
        "label": "STABLE",
        "tone": "neutral",
        "detail": f"{current:.2f}%",
    }

def curve_signal(two_year, ten_year):
    current_curve = latest(ten_year)["value"] - latest(two_year)["value"]
    old_curve = lag(ten_year, 20)["value"] - lag(two_year, 20)["value"]
    delta = current_curve - old_curve

    if delta >= 0.20:
        label = "STEEPENING"
        tone = "positive"
    elif delta <= -0.20:
        label = "FLATTENING"
        tone = "negative"
    elif current_curve < -0.10:
        label = "INVERTED"
        tone = "negative"
    elif current_curve <= 0.25:
        label = "FLAT"
        tone = "neutral"
    else:
        label = "POSITIVE"
        tone = "positive"

    return {
        "label": label,
        "tone": tone,
        "detail": f"{round(current_curve * 100)} bp",
    }

def real_yield_signal(points):
    current = latest(points)["value"]

    if current >= 1.5:
        label = "RESTRICTIVE"
        tone = "negative"
    elif current <= 0.5:
        label = "SUPPORTIVE"
        tone = "positive"
    else:
        label = "NEUTRAL"
        tone = "neutral"

    return {
        "label": label,
        "tone": tone,
        "detail": f"{current:.2f}%",
    }

def credit_signal(points):
    current = latest(points)["value"]
    d4 = change(points, 4)

    if current >= 0.25 or d4 >= 0.15:
        label = "TIGHTENING"
        tone = "negative"
    elif current <= -0.25 and d4 <= 0:
        label = "EASING"
        tone = "positive"
    else:
        label = "STABLE"
        tone = "neutral"

    return {
        "label": label,
        "tone": tone,
        "detail": f"{current:.2f} index",
    }

def inflation_signal(points):
    current = latest(points)["value"]
    d20 = change(points, 20)

    if d20 >= 0.15:
        label = "REACCELERATING"
        tone = "negative"
    elif d20 <= -0.15:
        label = "COOLING"
        tone = "positive"
    else:
        label = "STABLE"
        tone = "neutral"

    return {
        "label": label,
        "tone": tone,
        "detail": f"{current:.2f}%",
    }

def determine_regime(s):
    policy = s["policy"]["label"]
    curve = s["curve"]["label"]
    real = s["realRates"]["label"]
    credit = s["credit"]["label"]
    inflation = s["inflation"]["label"]

    if credit == "TIGHTENING" and policy == "EASING PRICED":
        return {
            "name": "STRESS / RISK-OFF",
            "description":
                "Rates markets are moving toward easier policy while credit conditions deteriorate. The combination is consistent with rising growth or financial-stress risk."
        }

    if (
        policy == "EASING PRICED"
        and curve == "STEEPENING"
        and credit != "TIGHTENING"
        and inflation != "REACCELERATING"
    ):
        return {
            "name": "EASING TRANSITION",
            "description":
                "The front end is pricing easier policy while the curve is steepening and credit remains contained. The configuration is consistent with a transition away from peak restriction."
        }

    if policy == "EASING PRICED":
        return {
            "name": "SLOWDOWN",
            "description":
                "Short-term rates are beginning to price easier policy, but confirmation from the curve and credit markets remains incomplete."
        }

    if (
        (policy == "TIGHTENING PRICED" or real == "RESTRICTIVE")
        and curve in ["FLATTENING", "INVERTED", "FLAT"]
    ):
        return {
            "name": "LATE-CYCLE TIGHTENING",
            "description":
                "Real rates remain restrictive and the curve is signalling limited room for policy to stay tight indefinitely. Financial conditions remain late-cycle."
        }

    if credit == "EASING" and curve in ["POSITIVE", "STEEPENING"]:
        return {
            "name": "EXPANSION",
            "description":
                "Credit conditions are supportive and the curve remains constructive. Fixed income is not signalling broad financial stress."
        }

    return {
        "name": "BALANCED TRANSITION",
        "description":
            "The major fixed-income signals are mixed. Policy, inflation and credit conditions are not yet pointing decisively toward a single regime."
    }

policy = fred(SERIES["policy"])
long_yield = fred(SERIES["long_yield"])
real_yield = fred(SERIES["real_yield"])
credit = fred(SERIES["credit"])
inflation = fred(SERIES["inflation"])

signals = {
    "policy": policy_signal(policy),
    "curve": curve_signal(policy, long_yield),
    "realRates": real_yield_signal(real_yield),
    "credit": credit_signal(credit),
    "inflation": inflation_signal(inflation),
}

regime = determine_regime(signals)

dates = sorted([
    latest(policy)["date"],
    latest(long_yield)["date"],
    latest(real_yield)["date"],
    latest(credit)["date"],
    latest(inflation)["date"],
])

data = {
    "ok": True,
    "title": "Bond Market Regime Monitor",
    "asOf": dates[0],
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "regime": regime,
    "signals": signals,
    "raw": {
        "twoYear": round(latest(policy)["value"], 2),
        "tenYear": round(latest(long_yield)["value"], 2),
        "curve": round(
            latest(long_yield)["value"] - latest(policy)["value"],
            2
        ),
        "realYield10Y": round(latest(real_yield)["value"], 2),
        "creditIndex": round(latest(credit)["value"], 3),
        "breakeven5Y": round(latest(inflation)["value"], 2),
    }
}

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)

print(json.dumps(data, indent=2))

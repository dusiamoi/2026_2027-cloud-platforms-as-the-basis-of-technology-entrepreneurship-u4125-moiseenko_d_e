"""Illustrative monthly cost model for Travelio Booking. Python 3, stdlib only."""
import json
from pathlib import Path

# USD/month; planning assumptions, not a vendor quote.
STAGES = {
    "pilot": {"mau": 1000, "searches": 20000, "run": 12, "sql": 15, "elastic": 55, "redis": 0, "edge": 0, "events": 2, "network": 5, "observability": 5, "staging": 0},
    "partners": {"mau": 20000, "searches": 400000, "run": 55, "sql": 85, "elastic": 260, "redis": 40, "edge": 0, "events": 8, "network": 30, "observability": 20, "staging": 55},
    "production": {"mau": 200000, "searches": 4000000, "run": 300, "sql": 310, "elastic": 1150, "redis": 190, "edge": 65, "events": 40, "network": 220, "observability": 65, "staging": 120},
}
RESERVE = 0.20

def calculate():
    rows = {}
    for stage, s in STAGES.items():
        names = ("run", "sql", "elastic", "redis", "edge", "events", "network", "observability", "staging")
        items = {key: s[key] for key in names}
        subtotal = round(sum(items.values()), 2)
        reserve = round(subtotal * RESERVE, 2)
        rows[stage] = {
            "mau": s["mau"], "searches_per_month": s["searches"],
            "cost_items_usd_month": items, "subtotal_usd_month": subtotal,
            "reserve_20pct_usd_month": reserve, "budget_usd_month": round(subtotal + reserve, 2),
            "cost_per_1000_searches_usd": round(subtotal / s["searches"] * 1000, 4),
        }
    return rows

if __name__ == "__main__":
    result = calculate()
    Path("cost_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Stage       Searches/mo    Subtotal USD    Budget +20% USD")
    for stage, row in result.items():
        print(f"{stage:12} {row['searches_per_month']:>12,} {row['subtotal_usd_month']:>15,.2f} {row['budget_usd_month']:>18,.2f}")

from datetime import timedelta
from typing import Any, Dict, Optional

import pandas as pd

from app.database.repositories import PriceRepository, RSIRepository, StockRepository


class MarketContextService:
    """Build the compact NIFTY 200 market snapshot sent to Gemini."""

    SYSTEM_INSTRUCTION = """You are the AI assistant inside a NIFTY 200 RSI analytics dashboard.

Your job:
1. Answer questions about the NIFTY 200 constituents and their RSI momentum.
2. Help the user think through stock purchase decisions using only the supplied market snapshot.
3. Explain the data clearly, including uncertainty and risks.

Hard rules:
- Use ONLY the supplied snapshot for prices, RSI values, and stock names. Never invent numbers, news, fundamentals, valuations, or events.
- RSI is a momentum indicator, not a valuation or a guarantee. Explain what the reading means and its limitations.
- Never promise returns or call any stock a "sure" investment.
- You are an educational tool, not a SEBI-registered investment adviser. Recommend diversifying and doing independent research.
- If the user asks for something the snapshot does not contain (news, P/E, earnings, support/resistance), say the dashboard does not have that data.
- Use INR (₹) for prices. Keep answers practical and reasonably concise.
- When discussing a purchase, state the action (BUY / ACCUMULATE / WATCH / AVOID / HOLD), the evidence from RSI 22/44/66 and the 30-day change, and the main risk.
"""

    RECOMMENDATION_INSTRUCTION = """You produce evidence-based stock screening suggestions for a NIFTY 200 RSI dashboard.

Rules:
- Use only the supplied snapshot. Do not invent fundamentals, news, or price levels.
- RSI is momentum, not valuation. Balance oversold signals with trend confirmation and diversification.
- The user's risk profile and horizon matter:
  * Conservative: prefer neutral/positive RSI with stable momentum; flag high volatility.
  * Balanced: blend oversold candidates with neutral/positive momentum.
  * Aggressive: may consider deeply oversold names, but must highlight falling-knife risk.
- Never guarantee returns. This is educational, not SEBI-registered investment advice.
- Allocate at most 100 percent of any stated budget across suggestions.
- Return ONLY valid JSON, with no markdown fences or commentary outside the JSON object.
"""

    @staticmethod
    def _zone(value: Any) -> str:
        if value is None or pd.isna(value):
            return "No RSI"
        value = float(value)
        if value < 30:
            return "Oversold"
        if value < 45:
            return "Weak"
        if value <= 55:
            return "Neutral"
        if value <= 70:
            return "Positive"
        return "Overbought"

    @classmethod
    def get_snapshot(cls) -> pd.DataFrame:
        """Return one row per active stock with RSI, latest close, and 30-day change."""
        ranking = RSIRepository.get_latest_rsi_rankings()
        if ranking is None or ranking.empty:
            active = StockRepository.get_active_stocks()
            ranking = pd.DataFrame(
                [
                    {
                        "symbol": stock["symbol"],
                        "company_name": stock.get("company_name") or stock["symbol"],
                        "trade_date": None,
                        "rsi_22": None,
                        "rsi_44": None,
                        "rsi_66": None,
                        "average_rsi": None,
                    }
                    for stock in active
                ]
            )
        if ranking.empty:
            return ranking

        ranking = ranking.copy()
        ranking["symbol"] = ranking["symbol"].astype(str).str.strip().str.upper()

        prices = PriceRepository.load_prices()
        if prices is not None and not prices.empty:
            prices = prices.copy()
            prices["symbol"] = prices["symbol"].astype(str).str.strip().str.upper()
            prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.date
            prices = prices.sort_values(["symbol", "trade_date"])
            latest_date = prices["trade_date"].max()

            latest = prices.groupby("symbol", as_index=False).tail(1)[
                ["symbol", "trade_date", "close_price"]
            ].rename(columns={"trade_date": "price_date", "close_price": "latest_close"})

            cutoff = latest_date - timedelta(days=30)
            history = prices[prices["trade_date"] <= cutoff]
            if not history.empty:
                baseline = history.groupby("symbol", as_index=False).tail(1)[
                    ["symbol", "close_price"]
                ].rename(columns={"close_price": "close_30d_ago"})
            else:
                baseline = pd.DataFrame(columns=["symbol", "close_30d_ago"])

            latest = latest.merge(baseline, on="symbol", how="left")
            latest["change_30d_pct"] = (
                (latest["latest_close"] / latest["close_30d_ago"] - 1.0) * 100.0
            )
            ranking = ranking.merge(latest, on="symbol", how="left")
        else:
            ranking["price_date"] = None
            ranking["latest_close"] = None
            ranking["change_30d_pct"] = None

        ranking["zone"] = ranking["average_rsi"].map(cls._zone)

        numeric_columns = [
            "latest_close",
            "change_30d_pct",
            "rsi_22",
            "rsi_44",
            "rsi_66",
            "average_rsi",
        ]
        for column in numeric_columns:
            if column in ranking.columns:
                ranking[column] = pd.to_numeric(ranking[column], errors="coerce").round(2)

        return ranking

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None or pd.isna(value):
            return "-"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    @classmethod
    def build_context_text(cls, snapshot: Optional[pd.DataFrame] = None) -> str:
        if snapshot is None:
            snapshot = cls.get_snapshot()
        if snapshot is None or snapshot.empty:
            return (
                "Market snapshot: no active NIFTY 200 RSI data is currently available. "
                "Tell the user to refresh the dashboard data first."
            )

        snapshot = snapshot.sort_values("average_rsi", ascending=False, na_position="last")
        latest_date = None
        if "price_date" in snapshot.columns:
            dates = [value for value in snapshot["price_date"].dropna().tolist()]
            if dates:
                latest_date = max(dates)
        latest_label = latest_date.isoformat() if hasattr(latest_date, "isoformat") else str(latest_date or "-")

        lines = [
            f"Market snapshot: {len(snapshot)} active NIFTY 200 stocks. Latest price date: {latest_label}.",
            "Columns: Symbol | Company | Close (INR) | 30D change % | RSI22 | RSI44 | RSI66 | Avg RSI | Zone",
        ]
        for row in snapshot.itertuples(index=False):
            company = str(getattr(row, "company_name", "") or getattr(row, "symbol", ""))[:48]
            lines.append(
                " | ".join(
                    [
                        str(getattr(row, "symbol", "")),
                        company,
                        cls._format_value(getattr(row, "latest_close", None)),
                        cls._format_value(getattr(row, "change_30d_pct", None)),
                        cls._format_value(getattr(row, "rsi_22", None)),
                        cls._format_value(getattr(row, "rsi_44", None)),
                        cls._format_value(getattr(row, "rsi_66", None)),
                        cls._format_value(getattr(row, "average_rsi", None)),
                        str(getattr(row, "zone", "No RSI")),
                    ]
                )
            )

        counts = snapshot["zone"].value_counts()
        lines.append(
            "Zone counts: "
            + ", ".join(f"{zone}={int(counts.get(zone, 0))}" for zone in [
                "Oversold",
                "Weak",
                "Neutral",
                "Positive",
                "Overbought",
                "No RSI",
            ])
        )
        return "\n".join(lines)

    @classmethod
    def get_prompt_context(cls) -> Dict[str, Any]:
        snapshot = cls.get_snapshot()
        return {
            "snapshot": snapshot,
            "context_text": cls.build_context_text(snapshot),
            "system_instruction": cls.SYSTEM_INSTRUCTION,
        }

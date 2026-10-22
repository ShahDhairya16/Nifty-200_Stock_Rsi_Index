import time

import pandas as pd
import streamlit as st

from app.config import config
from app.services.gemini_service import GeminiError, GeminiService
from frontend.utils.data_loader import get_ai_market_context


DEFAULT_RISK_PROFILE = "Balanced"
DEFAULT_HORIZON = "Medium term (6-12 months)"
DEFAULT_MAX_PICKS = 5
ERROR_RETRY_SECONDS = 300


def _service(api_key: str = "") -> GeminiService:
    return GeminiService(api_key=api_key or config.GEMINI_API_KEY)


@st.cache_data(ttl=21600, show_spinner=False)
def _get_auto_recommendations_cached(
    risk_profile: str,
    horizon: str,
    max_picks: int,
    budget: float,
    holdings: str,
    api_key: str,
):
    service = _service(api_key)
    if not service.is_configured:
        raise GeminiError(
            "Gemini API key is missing. Add GEMINI_API_KEY to Streamlit secrets "
            "or your local .env file."
        )

    _snapshot, context_text = get_ai_market_context()
    result = service.recommend(
        risk_profile=risk_profile,
        horizon=horizon,
        max_picks=max_picks,
        budget=budget or None,
        holdings=holdings,
        context_text=context_text,
    )
    result["_model"] = service.active_model or service.model
    return result


def get_auto_recommendations(
    risk_profile: str = DEFAULT_RISK_PROFILE,
    horizon: str = DEFAULT_HORIZON,
    max_picks: int = DEFAULT_MAX_PICKS,
    budget: float = 0.0,
    holdings: str = "",
    api_key: str = "",
):
    """Auto-generated market shortlist, cached only when the call succeeds."""
    cache_key = (
        "recommendations",
        risk_profile,
        horizon,
        max_picks,
        round(float(budget or 0.0), 2),
        holdings,
        bool(api_key),
    )
    cached_error = _recent_error(cache_key)
    if cached_error:
        return {"error": cached_error, "recommendations": []}

    try:
        result = _get_auto_recommendations_cached(
            risk_profile,
            horizon,
            max_picks,
            budget,
            holdings,
            api_key,
        )
        _clear_error(cache_key)
        return result
    except GeminiError as exc:
        message = str(exc)
        _store_error(cache_key, message)
        return {"error": message, "recommendations": []}
    except Exception:
        message = "The AI suggestion request failed unexpectedly."
        _store_error(cache_key, message)
        return {"error": message, "recommendations": []}


@st.cache_data(ttl=21600, show_spinner=False)
def _get_auto_stock_assessment_cached(symbol: str, api_key: str):
    service = _service(api_key)
    if not service.is_configured:
        raise GeminiError(
            "Gemini API key is missing. Add GEMINI_API_KEY to Streamlit secrets "
            "or your local .env file."
        )

    snapshot, _context_text = get_ai_market_context()
    if snapshot is None or snapshot.empty:
        raise GeminiError("No RSI snapshot is available.")

    zone_counts = snapshot["zone"].value_counts()
    market_summary = (
        f"Market context: {len(snapshot)} active NIFTY 200 stocks. Zone counts: "
        + ", ".join(
            f"{zone}={int(zone_counts.get(zone, 0))}"
            for zone in ["Oversold", "Weak", "Neutral", "Positive", "Overbought", "No RSI"]
        )
    )

    symbol = str(symbol).strip().upper()
    matches = snapshot[snapshot["symbol"].astype(str).str.upper() == symbol]
    if matches.empty:
        raise GeminiError(f"{symbol} is not in the current NIFTY 200 snapshot.")

    row = matches.iloc[0]
    stock_row = (
        f"Close: {_value(row.get('latest_close'))} | "
        f"30D change: {_value(row.get('change_30d_pct'))}% | "
        f"RSI22: {_value(row.get('rsi_22'))} | "
        f"RSI44: {_value(row.get('rsi_44'))} | "
        f"RSI66: {_value(row.get('rsi_66'))} | "
        f"Average RSI: {_value(row.get('average_rsi'))} | "
        f"Zone: {row.get('zone', 'No RSI')}"
    )

    result = service.assess_stock(
        symbol=symbol,
        company_name=str(row.get("company_name") or symbol),
        stock_row=stock_row,
        context_text=market_summary,
    )
    result["_model"] = service.active_model or service.model
    return result


def get_auto_stock_assessment(symbol: str, api_key: str = ""):
    """Auto-generated view for a single stock, cached only on success."""
    symbol = str(symbol).strip().upper()
    cache_key = ("assessment", symbol, bool(api_key))
    cached_error = _recent_error(cache_key)
    if cached_error:
        return {"error": cached_error}

    try:
        result = _get_auto_stock_assessment_cached(symbol, api_key)
        _clear_error(cache_key)
        return result
    except GeminiError as exc:
        message = str(exc)
        _store_error(cache_key, message)
        return {"error": message}
    except Exception:
        message = "The AI assessment request failed unexpectedly."
        _store_error(cache_key, message)
        return {"error": message}


def _recent_error(cache_key) -> str:
    cache = st.session_state.get("_ai_error_cache") or {}
    entry = cache.get(cache_key)
    if not entry:
        return ""
    timestamp, message = entry
    if time.time() - timestamp > ERROR_RETRY_SECONDS:
        cache.pop(cache_key, None)
        st.session_state["_ai_error_cache"] = cache
        return ""
    return message


def _store_error(cache_key, message: str) -> None:
    cache = dict(st.session_state.get("_ai_error_cache") or {})
    cache[cache_key] = (time.time(), message)
    st.session_state["_ai_error_cache"] = cache


def _clear_error(cache_key) -> None:
    cache = st.session_state.get("_ai_error_cache") or {}
    if cache_key in cache:
        cache = dict(cache)
        cache.pop(cache_key, None)
        st.session_state["_ai_error_cache"] = cache


def _value(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)

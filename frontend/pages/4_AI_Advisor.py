import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.config import config
from app.services.gemini_service import GeminiError, GeminiService
from frontend.components.ai_panel import normalize_confidence
from frontend.components.sidebar import render_sidebar
from frontend.utils.ai_loader import get_auto_recommendations
from frontend.utils.data_loader import get_ai_market_context

render_sidebar()
st.title("AI Advisor")
st.caption(
    "Ask questions about the NIFTY 200 RSI data or generate a purchase shortlist. "
    "Educational analysis only — not SEBI-registered investment advice."
)

if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""

api_key = st.session_state["gemini_api_key"] or config.GEMINI_API_KEY

if not api_key:
    with st.container(border=True):
        st.subheader("Connect Gemini")
        st.write(
            "Add your Google Gemini API key to use the chatbot and recommendation engine. "
            "You can save it permanently in Streamlit secrets or paste it for this session only."
        )
        entered_key = st.text_input(
            "Gemini API key",
            type="password",
            placeholder="AIza...",
            help="Get a key from Google AI Studio. It is never written to the repository.",
        )
        if st.button("Use key for this session", type="primary"):
            if entered_key.strip():
                st.session_state["gemini_api_key"] = entered_key.strip()
                st.rerun()
            else:
                st.warning("Enter a valid Gemini API key.")
        st.caption(
            "Permanent options: add GEMINI_API_KEY to .streamlit/secrets.toml "
            "(Streamlit Cloud: App settings → Secrets) or to your local .env file."
        )
    st.stop()

try:
    with st.spinner("Loading market snapshot..."):
        snapshot, context_text = get_ai_market_context()
except Exception:
    st.error(
        "Unable to load the NIFTY 200 market snapshot. Check the MongoDB settings "
        "and refresh the dashboard data, then try again."
    )
    st.stop()

gemini = GeminiService(api_key=api_key)

with st.sidebar:
    st.divider()
    st.caption(f"Gemini model\n{gemini.model}")
    if st.button("Disconnect session key", width="stretch"):
        st.session_state["gemini_api_key"] = ""
        st.rerun()

chat_tab, recommendations_tab, snapshot_tab = st.tabs(
    ["💬 Chat", "🎯 Buy Recommendations", "📊 Market Snapshot"]
)

with chat_tab:
    st.subheader("Chat with your market data")
    st.caption(
        "The assistant sees the current RSI 22/44/66 values, average RSI, latest close, "
        "and 30-day change for every active NIFTY 200 stock."
    )

    portfolio_context = st.text_area(
        "Optional context for the assistant",
        key="ai_portfolio_context",
        placeholder=(
            "Examples: I hold INFY and TCS. My horizon is 2 years. "
            "I want to add 2 stocks with moderate risk and a ₹50,000 budget."
        ),
        height=90,
    )

    if "ai_messages" not in st.session_state:
        st.session_state["ai_messages"] = []

    suggestions = [
        "Which NIFTY 200 stocks are most oversold right now?",
        "Compare the top 3 momentum stocks and their risks.",
        "Build a balanced watchlist for a 12-month horizon.",
        "Explain how RSI 22, RSI 44 and RSI 66 differ.",
    ]
    suggestion_columns = st.columns(2)
    for index, suggestion in enumerate(suggestions):
        if suggestion_columns[index % 2].button(
            suggestion, key=f"ai_suggestion_{index}", width="stretch"
        ):
            st.session_state["ai_pending_prompt"] = suggestion

    for message in st.session_state["ai_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask about a stock, a sector, or a purchase decision...")
    if st.session_state.get("ai_pending_prompt"):
        prompt = st.session_state.pop("ai_pending_prompt")

    if prompt:
        history = list(st.session_state["ai_messages"])
        st.session_state["ai_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking with the latest RSI snapshot..."):
                try:
                    answer = gemini.chat(
                        prompt,
                        history=history,
                        context_text=context_text,
                        portfolio=portfolio_context,
                    )
                except GeminiError as exc:
                    answer = f"⚠️ {exc}"
                except Exception:
                    answer = "⚠️ The Gemini request failed unexpectedly. Please try again."
            st.markdown(answer)
        st.session_state["ai_messages"].append({"role": "assistant", "content": answer})

    if st.session_state["ai_messages"]:
        if st.button("Clear conversation"):
            st.session_state["ai_messages"] = []
            st.rerun()

with recommendations_tab:
    st.subheader("Generate a purchase shortlist")
    st.caption(
        "Gemini screens the current NIFTY 200 RSI snapshot against your risk profile, "
        "horizon and budget. All suggestions are educational and require your own research."
    )

    with st.form("ai_recommendation_form"):
        left, right = st.columns(2)
        with left:
            risk_profile = st.selectbox(
                "Risk profile", ["Conservative", "Balanced", "Aggressive"], index=1
            )
            horizon = st.selectbox(
                "Investment horizon",
                [
                    "Short term (under 3 months)",
                    "Medium term (6-12 months)",
                    "Long term (1-3 years)",
                    "Very long term (3+ years)",
                ],
                index=1,
            )
        with right:
            max_picks = st.slider("Maximum suggestions", 3, 10, 5)
            budget = st.number_input(
                "Budget (₹, optional)", min_value=0.0, step=10000.0, value=0.0
            )
        holdings = st.text_area(
            "Existing holdings or constraints (optional)",
            placeholder="e.g. I already hold RELIANCE and HDFCBANK. Avoid PSU banks.",
            height=90,
        )
        submitted = st.form_submit_button("Generate recommendations", type="primary")

    if submitted:
        with st.spinner("Screening the NIFTY 200 snapshot..."):
            try:
                result = gemini.recommend(
                    risk_profile=risk_profile,
                    horizon=horizon,
                    max_picks=max_picks,
                    budget=budget or None,
                    holdings=holdings,
                    context_text=context_text,
                )
                st.session_state["ai_recommendations"] = result
                st.session_state["ai_recommendations_auto"] = False
            except GeminiError as exc:
                st.error(str(exc))
                st.session_state.pop("ai_recommendations", None)
            except Exception:
                st.error("The recommendation request failed unexpectedly. Please try again.")
                st.session_state.pop("ai_recommendations", None)

    if "ai_recommendations" not in st.session_state:
        with st.spinner("Gemini is preparing an initial shortlist..."):
            session_key = st.session_state.get("gemini_api_key", "")
            st.session_state["ai_recommendations"] = get_auto_recommendations(
                api_key=session_key
            )
        st.session_state["ai_recommendations_auto"] = True

    result = st.session_state.get("ai_recommendations")
    if result and result.get("error"):
        st.warning(f"AI suggestions are temporarily unavailable: {result['error']}")
        result = None
    if result:
        if st.session_state.get("ai_recommendations_auto"):
            st.caption(
                "Auto-generated for a Balanced risk profile and 6-12 month horizon. "
                "Adjust the controls above and regenerate for a personalized view."
            )
        summary = str(result.get("summary") or "").strip()
        if summary:
            st.markdown(summary)

        recommendations = result.get("recommendations") or []
        if recommendations:
            table = pd.DataFrame(recommendations)
            for numeric_column in ("confidence", "allocation_percent"):
                if numeric_column in table.columns:
                    table[numeric_column] = pd.to_numeric(
                        table[numeric_column], errors="coerce"
                    )
            if "confidence" in table.columns:
                table["confidence"] = table["confidence"].map(normalize_confidence)
            if "allocation_percent" in table.columns:
                table["allocation_percent"] = table["allocation_percent"].fillna(0).clip(0, 100)
            preferred_columns = [
                "symbol",
                "company_name",
                "action",
                "confidence",
                "allocation_percent",
                "rationale",
                "risks",
            ]
            available = [column for column in preferred_columns if column in table.columns]
            table = table[available].rename(
                columns={
                    "symbol": "Symbol",
                    "company_name": "Company",
                    "action": "Action",
                    "confidence": "Confidence",
                    "allocation_percent": "Allocation %",
                    "rationale": "Rationale",
                    "risks": "Main risk",
                }
            )
            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
                column_config={
                    "Confidence": st.column_config.ProgressColumn(
                        "Confidence", min_value=0, max_value=100, format="%d"
                    ),
                    "Allocation %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Rationale": st.column_config.TextColumn(width="large"),
                    "Main risk": st.column_config.TextColumn(width="large"),
                },
            )

            valid_symbols = set(snapshot["symbol"].astype(str).str.upper())
            suggested_symbols = {
                str(item.get("symbol", "")).strip().upper() for item in recommendations
            }
            unknown = sorted(suggested_symbols - valid_symbols)
            if unknown:
                st.warning(f"Ignore suggestions outside the current NIFTY 200 list: {', '.join(unknown)}")

            csv_data = table.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download shortlist (CSV)",
                data=csv_data,
                file_name="nifty200_ai_shortlist.csv",
                mime="text/csv",
            )
        else:
            st.warning(
                "Gemini did not return a structured shortlist. Review the response above "
                "and try generating again."
            )

        portfolio_note = str(result.get("portfolio_note") or "").strip()
        if portfolio_note:
            st.info(portfolio_note)
        disclaimer = str(result.get("disclaimer") or "").strip()
        st.caption(
            disclaimer
            or "Educational information only. Verify independently before investing."
        )

with snapshot_tab:
    st.subheader("Current NIFTY 200 RSI snapshot")
    if snapshot is None or snapshot.empty:
        st.info("No active RSI data is available. Refresh the dashboard data first.")
    else:
        view = snapshot.copy()
        view["zone"] = view["zone"].fillna("No RSI")
        zone_filter = st.multiselect(
            "Filter by RSI zone",
            ["Oversold", "Weak", "Neutral", "Positive", "Overbought", "No RSI"],
            default=["Oversold", "Weak", "Neutral", "Positive", "Overbought", "No RSI"],
        )
        view = view[view["zone"].isin(zone_filter)]
        view = view.sort_values("average_rsi", ascending=False, na_position="last")
        display = view[
            [
                "symbol",
                "company_name",
                "latest_close",
                "change_30d_pct",
                "rsi_22",
                "rsi_44",
                "rsi_66",
                "average_rsi",
                "zone",
            ]
        ].rename(
            columns={
                "symbol": "Symbol",
                "company_name": "Company",
                "latest_close": "Close (₹)",
                "change_30d_pct": "30D change %",
                "rsi_22": "RSI 22",
                "rsi_44": "RSI 44",
                "rsi_66": "RSI 66",
                "average_rsi": "Average RSI",
                "zone": "Zone",
            }
        )
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config={
                "Close (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                "30D change %": st.column_config.NumberColumn(format="%.2f%%"),
                "RSI 22": st.column_config.NumberColumn(format="%.2f"),
                "RSI 44": st.column_config.NumberColumn(format="%.2f"),
                "RSI 66": st.column_config.NumberColumn(format="%.2f"),
                "Average RSI": st.column_config.NumberColumn(format="%.2f"),
            },
        )

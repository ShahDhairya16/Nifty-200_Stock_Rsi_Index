import streamlit as st

st.title("NIFTY Market Tools")
st.write("Choose a project to open its pages and navigation.")

left, right = st.columns(2, gap="large")
with left:
    with st.container(border=True):
        st.subheader("📊 NIFTY 750 RSI Index")
        st.write("RSI dashboard, stock ranking, individual stock analysis, AI advisor, and reports.")
        if st.button("Open NIFTY 750 RSI", type="primary", width="stretch", key="open_nifty200"):
            st.session_state["selected_project"] = "nifty200"
            st.rerun()

with right:
    with st.container(border=True):
        st.subheader("📉 NIFTY 750 Bollinger Band Strategy")
        st.write("Weekly Bollinger calculations, upper-band ranking, and Excel download.")
        if st.button("Open NIFTY 750 Bollinger", type="primary", width="stretch", key="open_nifty750"):
            st.session_state["selected_project"] = "nifty750"
            st.rerun()

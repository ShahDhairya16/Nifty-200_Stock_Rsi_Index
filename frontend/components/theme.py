import streamlit as st


def apply_theme():
    colors = {
        "background": "#07111f",
        "surface": "#0d1b2e",
        "surface_alt": "#11243b",
        "text": "#e8f0fb",
        "muted": "#91a4bb",
        "border": "#1e3550",
        "accent": "#4d8dff",
    }
    st.markdown(f"""
    <style>
    :root {{ color-scheme: dark; }}
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"] {{
        background: {colors['background']} !important; color: {colors['text']} !important; }}
    header[data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stDecoration"], [data-testid="stBottomBlockContainer"] {{
        background: {colors['background']} !important; color: {colors['text']} !important; }}
    .block-container {{ max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }}
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
        background: {colors['surface']} !important; border-right: 1px solid {colors['border']}; }}
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {{ color: {colors['text']} !important; }}
    [data-testid="stSidebar"] h2 {{ color: {colors['accent']} !important; letter-spacing: .08em; }}
    [data-testid="stMetric"] {{ background: {colors['surface']}; border: 1px solid {colors['border']};
        border-left: 3px solid {colors['accent']}; border-radius: 6px; padding: 1rem 1.1rem; }}
    [data-testid="stMetricLabel"] {{ color: {colors['muted']} !important; }}
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{
        color: {colors['text']} !important; font-size: 1.45rem !important;
        line-height: 1.2 !important; white-space: nowrap !important;
        overflow: visible !important; text-overflow: clip !important; }}
    .stDataFrame {{ border: 1px solid {colors['border']}; border-radius: 6px; overflow: hidden; }}
    [data-testid="stDataFrame"] {{ background: {colors['surface']} !important; }}
    [data-testid="stSidebarNav"] span, [data-testid="stSidebarNav"] svg {{
        color: {colors['text']} !important; fill: {colors['text']} !important; }}
    h1, h2, h3, p, label, [data-testid="stMarkdownContainer"] {{
        color: {colors['text']} !important; letter-spacing: 0; }}
    h1 {{ font-weight: 700; }}
    .stCaption, [data-testid="stCaptionContainer"] {{ color: {colors['muted']} !important; }}
    input, textarea, [data-baseweb="select"] > div, [data-baseweb="input"] > div {{
        background: {colors['surface_alt']} !important; color: {colors['text']} !important;
        border-color: {colors['border']} !important; }}
    button, button[kind="secondary"] {{
        background: {colors['surface']} !important; border: 1px solid {colors['border']} !important;
        color: {colors['text']} !important; box-shadow: none !important; }}
    button:hover {{ border-color: {colors['accent']} !important; color: {colors['accent']} !important; }}
    [data-testid="stBaseButton-secondary"] {{ background: {colors['surface']} !important; }}
    [data-testid="stAlert"] {{ background: {colors['surface_alt']} !important; }}
    </style>
    """, unsafe_allow_html=True)


def is_dark():
    return True
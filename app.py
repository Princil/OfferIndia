"""TrackOffer — Streamlit app to find >50% off deals across Amazon, Flipkart, Myntra."""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from trackoffer.models import SearchQuery
from trackoffer.fetchers import build_fetchers
from trackoffer import llm

# Load .env from the same directory as this script, regardless of cwd
_script_dir = Path(__file__).resolve().parent
_env_path = _script_dir / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path), override=True)
else:
    load_dotenv(override=True)  # fallback to cwd

# Hard fallback: manually parse .env and set any missing vars
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and not os.getenv(key):
                    os.environ[key] = val

# ─── Load Streamlit secrets (for Streamlit Cloud deployment) ────────
try:
    if hasattr(st, "secrets") and st.secrets:
        for key, val in st.secrets.items():
            if isinstance(val, str) and val:
                os.environ.setdefault(key, val)
except Exception:
    pass

st.set_page_config(
    page_title="TrackOffer India",
    page_icon="🔥",
    layout="wide",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": None,
    },
)

# Hide Streamlit toolbar (GitHub, edit, share icons)
st.markdown(
    """
    <style>
        .stAppHeader { display: none !important; }
        header[data-testid="stHeader"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Data source (internal, not shown to user) ───────────────────
os.environ["DATA_SOURCE"] = os.getenv("DATA_SOURCE", "free").lower()
st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Header ─────────────────────────────────────────────────────
st.title("🔥 TrackOffer India")
st.markdown(
    "Find products with **>50% off** across **Amazon, Flipkart & Myntra** — ranked by deal quality."
)
st.divider()

# ─── Search / query input ────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    nl_query = st.text_input(
        "Search or ask naturally",
        placeholder="e.g. bluetooth headphones under 2000 with 60% off",
    )
with col2:
    st.write("")
    st.write("")
    search_clicked = st.button("🔍 Search Deals", type="primary", use_container_width=True)

# ─── Advanced filters (expander) ─────────────────────────────────
with st.expander("Advanced Filters"):
    c1, c2, c3 = st.columns(3)
    with c1:
        min_discount = st.slider("Min Discount %", 0, 90, 50, 5)
    with c2:
        min_price = st.number_input("Min Price (₹)", 0, 500000, 0, 100)
    with c3:
        max_price = st.number_input("Max Price (₹)", 0, 500000, 0, 100)
    if max_price == 0:
        max_price = None

    sources = st.multiselect(
        "Sources",
        ["amazon", "flipkart", "myntra", "ajio", "tatacliq", "nykaa", "meesho", "snapdeal"],
        default=["amazon", "flipkart", "myntra", "ajio", "tatacliq", "nykaa", "meesho", "snapdeal"],
    )

# ─── Run search ──────────────────────────────────────────────────
if search_clicked and nl_query:
    with st.spinner("Parsing query & fetching deals …"):
        # 1) Parse natural language
        base_q = llm.parse_query(nl_query)
        # 2) Override with advanced filters
        q = SearchQuery(
            keywords=base_q.keywords or nl_query,
            min_discount=min_discount,
            max_price=max_price if max_price else base_q.max_price,
            min_price=min_price if min_price else base_q.min_price,
            category=base_q.category,
            sources=sources,
            min_rating=base_q.min_rating,
        )

        fetchers = build_fetchers()
        all_products: list = []
        source_counts: dict[str, int] = {}
        google_error = None
        for f in fetchers:
            if f.source_name in q.sources or f.source_name in ("google", "playwright"):
                try:
                    batch = f.search(q)
                    all_products.extend(batch)
                    # Count by actual product source, not fetcher name
                    for p in batch:
                        source_counts[p.source] = source_counts.get(p.source, 0) + 1
                    # Check for stored API error on Google fetcher
                    if f.source_name == "google" and hasattr(f, "_last_error") and f._last_error:
                        google_error = f._last_error
                except Exception as e:
                    source_counts[f.source_name] = 0
                    st.error(f"Error fetching from {f.source_name}: {e}")

        if google_error:
            st.error(f"⚠️ Google Custom Search error: {google_error}")

        # Show source breakdown
        st.caption(
            "Sources used: "
            + " | ".join(f"**{k}**: {v}" for k, v in sorted(source_counts.items()))
        )
        # Warn if only mock data returned
        if all(p.source in ("amazon", "flipkart", "myntra") for p in all_products[:5]):
            # Check if URLs look mock-generated
            mock_count = sum(1 for p in all_products if "/product/" in p.url and p.source in ("amazon", "flipkart", "myntra"))
            if mock_count > 0:
                st.warning(
                    f"⚠️ {mock_count} result(s) appear to be mock/demo data. "
                    "Make sure sidebar is set to 'Free (Google + PA-API)' and your Google credentials are correct."
                )

        # 3) Rank
        ranked = llm.rank_deals(all_products)

    st.divider()
    st.subheader(f"🎯 {len(ranked)} deals found (≥{q.min_discount}% off)")

    if not ranked:
        st.info("No deals matched your criteria. Try lowering the discount or broadening keywords.")
    else:
        # Prep DataFrame
        df = pd.DataFrame([
            {
                "Source": p.source.upper(),
                "Title": p.title,
                "Price (₹)": p.price,
                "MRP (₹)": p.mrp,
                "Discount %": f"{p.discount_pct}%",
                "Savings (₹)": p.savings,
                "Rating": p.rating,
                "Reviews": p.reviews,
                "Link": p.url,
                "Image": p.image,
            }
            for p in ranked
        ])

        # Optional: apply max price
        if q.max_price:
            df = df[df["Price (₹)"] <= q.max_price]
        if q.min_price:
            df = df[df["Price (₹)"] >= q.min_price]
        if q.min_rating:
            df = df[df["Rating"] >= q.min_rating]

        # Download
        csv = df.to_csv(index=False).encode("utf-8")
        fname = f"trackoffer_deals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name=fname,
            mime="text/csv",
        )

        # Display cards
        for _, row in df.iterrows():
            with st.container(border=True):
                c_img, c_info, c_price = st.columns([1, 3, 2])
                with c_img:
                    if row["Image"]:
                        try:
                            st.image(row["Image"], use_container_width=True)
                        except Exception:
                            pass
                with c_info:
                    st.markdown(f"**{row['Title']}**")
                    st.caption(f"📦 {row['Source']}  |  ⭐ {row['Rating']} ({row['Reviews']} reviews)")
                    st.link_button("🔗 Open on site", url=row["Link"], use_container_width=False)
                with c_price:
                    st.markdown(f"### ₹{row['Price (₹)']}")
                    st.markdown(
                        f"<span style='text-decoration:line-through;color:grey;'>₹{row['MRP (₹)']}</span>"
                        f"&nbsp;&nbsp;<span style='color:green;font-weight:bold;'>{row['Discount %']} OFF</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"💰 **Save ₹{row['Savings (₹)']}**")

        # Summary stats
        st.divider()
        c_a, c_b, c_c = st.columns(3)
        with c_a:
            st.metric("Total Deals", len(df))
        with c_b:
            avg_disc = round(df["Discount %"].str.replace("%", "").astype(float).mean(), 1) if len(df) else 0
            st.metric("Avg Discount", f"{avg_disc}%")
        with c_c:
            max_savings = df["Savings (₹)"].max() if len(df) else 0
            st.metric("Max Savings", f"₹{max_savings}")

elif search_clicked and not nl_query:
    st.warning("Please enter a search query.")

# ─── Footer ─────────────────────────────────────────────────────
st.divider()
st.caption("Built with ❤️ for Indian shoppers. Data is approximate; verify on the retailer site before buying.")

"""TrackOffer — Streamlit app to find >50% off deals across Amazon, Flipkart, Myntra."""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html
from dotenv import load_dotenv

from trackoffer.models import SearchQuery
from trackoffer.fetchers import build_fetchers
from trackoffer.featured_deals import get_all_featured_deals
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
    "Find products with **>50% off** across **Amazon, Flipkart, OPPO, realme, boAt, Dot&Key & more** — ranked by deal quality."
)
st.divider()

# ─── Featured Brand Deals (D2C) ──────────────────────────────────
featured_deals = get_all_featured_deals(min_discount=50.0)
if featured_deals:
    st.subheader("⭐ Featured Brand Deals")
    st.caption("Hand-picked deals from boAt, OPPO, realme, Dot&Key — updated weekly")
    
    # Show top 6 featured deals in a grid
    for i in range(0, min(6, len(featured_deals)), 3):
        cols = st.columns(3)
        for j, deal in enumerate(featured_deals[i:i+3]):
            with cols[j]:
                brand_emoji = {"ajio": "👕", "boat": "🎧", "oppo": "📱", "realme": "📱", "dotandkey": "🧴"}.get(deal.source, "🏷️")
                st.markdown(f"**{brand_emoji} {deal.brand or deal.source.title()}**")
                st.markdown(f"[{deal.title}]({deal.url})")
                st.markdown(
                    f"<span style='color:#e74c3c;font-size:1.3em;font-weight:bold;'>₹{deal.price}</span> "
                    f"<span style='text-decoration:line-through;color:grey;'>₹{deal.mrp}</span> "
                    f"<span style='color:green;font-weight:bold;'>-{deal.discount_pct:.0f}%</span>",
                    unsafe_allow_html=True,
                )
                st.link_button("🔗 Open Deal", url=deal.url, use_container_width=True)
                st.write("")
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

# ─── Hidden defaults (advanced filters disabled for now) ─────────
min_discount = 50
min_price = 0
max_price = None
sources = ["amazon", "flipkart", "myntra", "ajio", "tatacliq", "nykaa", "meesho", "snapdeal", "shopclues", "limeroad", "oppo", "realme", "boat", "dotandkey"]

# ─── Bubble Game HTML (injected during loading) ──────────────────
BUBBLE_GAME_HTML = """
<div id="bubble-game-container" style="text-align:center;font-family:sans-serif;">
  <div style="font-size:1.1em;color:#666;margin-bottom:8px;">🫧 Pop the bubbles while we find deals!</div>
  <div style="font-size:0.9em;color:#888;margin-bottom:10px;">Score: <span id="score" style="font-weight:bold;color:#e74c3c;">0</span></div>
  <canvas id="bubbleCanvas" width="700" height="350" style="border-radius:12px;cursor:pointer;background:linear-gradient(180deg,#e3f2fd 0%,#bbdefb 100%);"></canvas>
</div>
<script>
(function(){
  var canvas = document.getElementById('bubbleCanvas');
  var ctx = canvas.getContext('2d');
  var scoreEl = document.getElementById('score');
  var score = 0;
  var bubbles = [];
  var particles = [];
  var colors = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD','#87CEEB','#FF69B4'];

  function rand(a,b){return Math.random()*(b-a)+a;}

  function createBubble(){
    var r = rand(18,36);
    bubbles.push({
      x: rand(r, canvas.width-r),
      y: canvas.height + r,
      r: r,
      speed: rand(0.8,2.2),
      wobble: rand(0, Math.PI*2),
      wobbleSpeed: rand(0.02,0.06),
      color: colors[Math.floor(rand(0,colors.length))],
      popped: false
    });
  }

  for(var i=0;i<12;i++) createBubble();

  canvas.addEventListener('click', function(e){
    var rect = canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    for(var i=bubbles.length-1;i>=0;i--){
      var b = bubbles[i];
      if(!b.popped && Math.hypot(mx-b.x, my-b.y) < b.r+8){
        b.popped = true;
        score++;
        scoreEl.textContent = score;
        for(var j=0;j<8;j++){
          particles.push({
            x: b.x, y: b.y,
            vx: rand(-3,3), vy: rand(-3,3),
            life: 1.0,
            color: b.color,
            size: rand(2,5)
          });
        }
        break;
      }
    }
  });

  function draw(){
    ctx.clearRect(0,0,canvas.width,canvas.height);

    // Draw particles
    for(var i=particles.length-1;i>=0;i--){
      var p = particles[i];
      p.x += p.vx; p.y += p.vy;
      p.life -= 0.04;
      if(p.life <= 0){ particles.splice(i,1); continue; }
      ctx.globalAlpha = p.life;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x,p.y,p.size,0,Math.PI*2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Draw bubbles
    for(var i=bubbles.length-1;i>=0;i--){
      var b = bubbles[i];
      if(b.popped){ bubbles.splice(i,1); continue; }
      b.y -= b.speed;
      b.wobble += b.wobbleSpeed;
      b.x += Math.sin(b.wobble)*0.6;
      if(b.y < -b.r){ bubbles.splice(i,1); continue; }

      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI*2);
      ctx.fillStyle = b.color + '44';
      ctx.fill();
      ctx.strokeStyle = b.color;
      ctx.lineWidth = 2;
      ctx.stroke();

      // shine
      ctx.beginPath();
      ctx.arc(b.x-b.r*0.25, b.y-b.r*0.25, b.r*0.2, 0, Math.PI*2);
      ctx.fillStyle = '#fff';
      ctx.fill();
    }

    if(bubbles.length < 12) createBubble();
    requestAnimationFrame(draw);
  }
  draw();
})();
</script>
"""

# ─── Run search ──────────────────────────────────────────────────
if search_clicked and nl_query:
    # Show bubble game while fetching
    st.markdown("**Parsing query & fetching deals …** 🫧")
    html(BUBBLE_GAME_HTML, height=420)

    # Run search in background
    base_q = llm.parse_query(nl_query)
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
                for p in batch:
                    source_counts[p.source] = source_counts.get(p.source, 0) + 1
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

elif search_clicked and not nl_query:
    st.warning("Please enter a search query.")

# ─── Footer ─────────────────────────────────────────────────────
st.divider()
st.caption("Built with ❤️ for Indian shoppers. Data is approximate; verify on the retailer site before buying.")
st.caption(
    "All product names, logos, and brands are property of their respective owners. "
    "Use of these names, logos, and brands does not imply endorsement."
)

# 🔥 TrackOffer India

Find products with **>50% off** across **Amazon, Flipkart & Myntra** using AI-powered search and deal ranking.

## Features
- **Natural Language Search** — "bluetooth headphones under ₹2000 with 60% off"
- **AI Deal Ranking** — OpenAI GPT re-ranks deals by quality (discount + rating + reviews)
- **Multi-source** — Amazon, Flipkart, Myntra
- **Free Data Mode** — Google Custom Search + Amazon PA-API (no paid API fees)
- **Advanced Filters** — min discount %, price range, source selection
- **CSV Export** — download filtered results
- **Clean UI** — built with Streamlit

## Quick Start (Demo Mode)

```bash
cd d:\Windsurf\Applications\TrackOffer
pip install -r requirements.txt
streamlit run app.py
```

The app runs in **Mock Mode** by default — it generates realistic demo products so you can use it immediately without any API keys.

## Data Sources

### 1. Free Mode (Recommended — no recurring cost)
This searches across all Indian e-commerce sites **without paid RapidAPI fees**.

| Component | What it does | Cost |
|-----------|-------------|------|
| **Google Custom Search** | Discovers products across Amazon.in, Flipkart, Myntra | **Free** (100 queries/day) |
| **Amazon PA-API** | Accurate Amazon prices, images, ratings | **Free** with Associates account |
| **Mock (Flipkart/Myntra)** | Simulated data for sites with no free API | Free |

**Setup:**
1. **Google Custom Search** (5 min)
   - Create a search engine at [programmablesearchengine.google.com](https://programmablesearchengine.google.com/)
   - Enable "Search the entire web" + restrict to `amazon.in`, `flipkart.com`, `myntra.com` if desired
   - Get your **Search Engine ID (CX)**
   - Get a **Google Cloud API Key** at [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) (enable Custom Search API)
2. **Amazon PA-API** (optional but recommended for real Amazon data)
   - Sign up for [Amazon Associates India](https://affiliate-program.amazon.in/)
   - Generate PA-API credentials at [webservices.amazon.com](https://webservices.amazon.com/paapi5/documentation/)
3. Copy `.env.example` → `.env` and fill in `GOOGLE_API_KEY`, `GOOGLE_CX`, and optionally `AMAZON_*` keys
4. In the app sidebar, switch to **Free (Google + PA-API)**

### 2. RapidAPI Mode (Paid)
1. Sign up at [rapidapi.com](https://rapidapi.com)
2. Subscribe to Real-Time Amazon Data + Real-Time Flipkart API
3. Copy `.env.example` → `.env` and fill `RAPIDAPI_KEY`
4. In the app sidebar, switch to **RapidAPI (paid)**

### 3. LLM Features (Optional)
Add your OpenAI key to `.env` for natural-language query parsing and AI deal ranking:
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Without this, the app falls back to simple keyword search and heuristic deal ranking.

## Project Structure

```
trackoffer/
├── __init__.py      # package marker
├── models.py        # Product & SearchQuery Pydantic models
├── fetchers.py      # Mock + Google Custom Search + Amazon PA-API + RapidAPI fetchers
└── llm.py           # Natural language query parsing + deal ranking
app.py               # Streamlit UI
requirements.txt     # dependencies
.env.example         # configuration template
```

## Deploy to Streamlit Cloud (Free + Custom Domain)

The easiest way to host this app publicly is **Streamlit Community Cloud**.

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/trackoffer.git
git push -u origin main
```

### 2. Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app** → select your repo
4. Set **Main file path** to `app.py`
5. Click **Deploy**

### 3. Add Secrets (Environment Variables)
In Streamlit Cloud dashboard → **Settings** → **Secrets**:
```toml
AMAZON_AFFILIATE_TAG = "princil-21"
DATA_SOURCE = "free"
# Optional:
# GOOGLE_API_KEY = "..."
# GOOGLE_CX = "..."
```

### 4. Add Custom Domain
1. In Streamlit Cloud dashboard → **Settings** → **Custom Domain**
2. Enter your domain (e.g., `deals.yourdomain.com`)
3. Add the CNAME record Streamlit gives you to your DNS provider
4. Wait for SSL certificate to be issued (usually instant)

### Important: Playwright Browser Install
After deployment, the first run may take 2-3 minutes as Streamlit Cloud installs Chromium system dependencies (defined in `packages.txt`). Subsequent runs are fast.

## Notes
- Flipkart and Myntra have no public free APIs; the app uses Playwright headless browser scraping for live data.
- Google Custom Search may not always extract exact prices from snippets.
- Always verify on the actual retailer site before purchasing.
- This app uses **Playwright** (headless Chromium) for web scraping — this requires Linux system libraries which are installed via `packages.txt` on Streamlit Cloud.

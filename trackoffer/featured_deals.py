"""Manually curated featured deals from D2C brand websites.
UPDATE THIS FILE WEEKLY by checking brand sites for new deals.

Last updated: May 31, 2026
Sources checked:
- AJIO: https://www.ajio.com/shop/sale (fashion sale)
- boAt: https://www.boat-lifestyle.com/collections/crazy-deals
- OPPO: https://www.oppo.com/in (promotional offers)
- realme: https://www.realme.com/in (new launches)
- Dot&Key: https://www.dotandkey.com (sale section)
"""
from typing import List
from .models import Product


# ─── AJIO ─ Fashion Sale (up to 70% off) ───────────────────────
AJIO_DEALS: List[Product] = [
    Product(
        source="ajio",
        title="AJIO Men Slim Fit Jeans - Levi's",
        url="https://www.ajio.com/search/?text=levis+jeans+men",
        image="",
        price=1299.0,
        mrp=3999.0,
        rating=4.2,
        reviews=5600,
        category="fashion",
        brand="Levi's",
    ),
    Product(
        source="ajio",
        title="AJIO Women Kurtas - Global Desi",
        url="https://www.ajio.com/search/?text=global+desi+kurta",
        image="",
        price=799.0,
        mrp=2499.0,
        rating=4.4,
        reviews=3200,
        category="fashion",
        brand="Global Desi",
    ),
    Product(
        source="ajio",
        title="AJIO Men Running Shoes - Nike",
        url="https://www.ajio.com/search/?text=nike+running+shoes+men",
        image="",
        price=2499.0,
        mrp=5999.0,
        rating=4.5,
        reviews=8900,
        category="fashion",
        brand="Nike",
    ),
    Product(
        source="ajio",
        title="AJIO Women Handbag - Lavie",
        url="https://www.ajio.com/search/?text=lavie+handbag",
        image="",
        price=999.0,
        mrp=2999.0,
        rating=4.3,
        reviews=2100,
        category="fashion",
        brand="Lavie",
    ),
]

# ─── boAt Lifestyle ─ Crazy Deals (up to 87% off) ──────────────
# NOTE: Use collection URLs, not product URLs (products go out of stock/404)
BOAT_DEALS: List[Product] = [
    Product(
        source="boat",
        title="boAt Storm Call 3 Smartwatch - BT Calling (87% off)",
        url="https://www.boat-lifestyle.com/collections/crazy-deals",
        image="",
        price=1099.0,
        mrp=8499.0,
        rating=4.7,
        reviews=30000,
        category="wearable",
        brand="boAt",
    ),
    Product(
        source="boat",
        title="boAt Nirvana Crystl - 100H Playback, ANC (81% off)",
        url="https://www.boat-lifestyle.com/collections/crazy-deals",
        image="",
        price=2099.0,
        mrp=10990.0,
        rating=4.6,
        reviews=8000,
        category="audio",
        brand="boAt",
    ),
    Product(
        source="boat",
        title="boAt Airdopes Supreme TWS - Spatial Audio (77% off)",
        url="https://www.boat-lifestyle.com/collections/best-sellers",
        image="",
        price=1399.0,
        mrp=5990.0,
        rating=4.8,
        reviews=192000,
        category="audio",
        brand="boAt",
    ),
    Product(
        source="boat",
        title="boAt Airdopes 141 - 42H Playback (80% off)",
        url="https://www.boat-lifestyle.com/collections/daily-deals",
        image="",
        price=1199.0,
        mrp=5990.0,
        rating=4.8,
        reviews=166000,
        category="audio",
        brand="boAt",
    ),
    Product(
        source="boat",
        title="boAt Nirvana Zenith Pro - LDAC, ANC (79% off)",
        url="https://www.boat-lifestyle.com/collections/crazy-deals",
        image="",
        price=3199.0,
        mrp=14990.0,
        rating=4.6,
        reviews=22000,
        category="audio",
        brand="boAt",
    ),
    Product(
        source="boat",
        title="boAt Stone 352 Bluetooth Speaker (66% off)",
        url="https://www.boat-lifestyle.com/collections/daily-deals",
        image="",
        price=849.0,
        mrp=2490.0,
        rating=4.3,
        reviews=45000,
        category="audio",
        brand="boAt",
    ),
]

# ─── OPPO India ─ Smartphone Offers ──────────────────────────────
OPPO_DEALS: List[Product] = [
    Product(
        source="oppo",
        title="OPPO Find X7 Ultra - Hasselblad Camera",
        url="https://www.oppo.com/in/smartphones/find-x7-ultra/",
        image="",
        price=59999.0,
        mrp=79999.0,
        rating=4.6,
        reviews=8500,
        category="mobile",
        brand="OPPO",
    ),
    Product(
        source="oppo",
        title="OPPO Reno 12 Pro 5G - AI Portrait",
        url="https://www.oppo.com/in/smartphones/reno-12-pro-5g/",
        image="",
        price=32999.0,
        mrp=54999.0,
        rating=4.4,
        reviews=12000,
        category="mobile",
        brand="OPPO",
    ),
    Product(
        source="oppo",
        title="OPPO F27 Pro+ 5G - Ultra Durable",
        url="https://www.oppo.com/in/smartphones/f27-pro-plus-5g/",
        image="",
        price=24999.0,
        mrp=39999.0,
        rating=4.3,
        reviews=5600,
        category="mobile",
        brand="OPPO",
    ),
]

# ─── realme India ─ New Launch Offers ────────────────────────────
REALME_DEALS: List[Product] = [
    Product(
        source="realme",
        title="realme GT 6T 5G - Snapdragon 8s Gen 3",
        url="https://www.realme.com/in/realme-gt-6t-5g",
        image="",
        price=30999.0,
        mrp=44999.0,
        rating=4.5,
        reviews=15000,
        category="mobile",
        brand="realme",
    ),
    Product(
        source="realme",
        title="realme 12 Pro+ 5G - Periscope Camera",
        url="https://www.realme.com/in/realme-12-pro-plus-5g",
        image="",
        price=24999.0,
        mrp=34999.0,
        rating=4.3,
        reviews=28000,
        category="mobile",
        brand="realme",
    ),
    Product(
        source="realme",
        title="realme Buds Air 6 - 50dB ANC",
        url="https://www.realme.com/in/realme-buds-air-6",
        image="",
        price=2999.0,
        mrp=5999.0,
        rating=4.2,
        reviews=42000,
        category="audio",
        brand="realme",
    ),
]

# ─── Dot&Key ─ Skincare Sale ─────────────────────────────────────
DOTANDKEY_DEALS: List[Product] = [
    Product(
        source="dotandkey",
        title="Dot & Key Vitamin C + E Super Bright Moisturizer",
        url="https://www.dotandkey.com/products/vitamin-c-e-moisturizer",
        image="",
        price=349.0,
        mrp=795.0,
        rating=4.4,
        reviews=8500,
        category="skincare",
        brand="Dot&Key",
    ),
    Product(
        source="dotandkey",
        title="Dot & Key 10% AHA + 2% BHA Exfoliating Serum",
        url="https://www.dotandkey.com/products/aha-bha-exfoliating-serum",
        image="",
        price=449.0,
        mrp=995.0,
        rating=4.3,
        reviews=6200,
        category="skincare",
        brand="Dot&Key",
    ),
    Product(
        source="dotandkey",
        title="Dot & Key CICA Calming Face Moisturizer",
        url="https://www.dotandkey.com/products/cica-calming-moisturizer",
        image="",
        price=295.0,
        mrp=595.0,
        rating=4.5,
        reviews=9800,
        category="skincare",
        brand="Dot&Key",
    ),
    Product(
        source="dotandkey",
        title="Dot & Key Watermelon Super Glow Sunscreen SPF 50",
        url="https://www.dotandkey.com/products/watermelon-sunscreen-spf50",
        image="",
        price=399.0,
        mrp=849.0,
        rating=4.2,
        reviews=11000,
        category="skincare",
        brand="Dot&Key",
    ),
]


def get_all_featured_deals(min_discount: float = 50.0) -> List[Product]:
    """Return all featured deals that meet the discount threshold."""
    all_deals = AJIO_DEALS + BOAT_DEALS + OPPO_DEALS + REALME_DEALS + DOTANDKEY_DEALS
    return [d for d in all_deals if d.discount_pct >= min_discount]


def get_featured_by_brand(brand: str, min_discount: float = 50.0) -> List[Product]:
    """Return featured deals for a specific brand."""
    brand_map = {
        "ajio": AJIO_DEALS,
        "boat": BOAT_DEALS,
        "oppo": OPPO_DEALS,
        "realme": REALME_DEALS,
        "dotandkey": DOTANDKEY_DEALS,
    }
    deals = brand_map.get(brand.lower(), [])
    return [d for d in deals if d.discount_pct >= min_discount]

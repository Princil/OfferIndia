#!/usr/bin/env python3
"""Scrape deals from multiple sites and save to deals.json for app to serve.
Run this locally or via GitHub Actions every 2 hours.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Add trackoffer to path
sys.path.insert(0, str(Path(__file__).parent))
from trackoffer.models import Product, SearchQuery


def _extract_price(text: str) -> tuple[float, float]:
    """Extract price and MRP from text."""
    # Find ₹ prices
    prices = re.findall(r"[₹Rs\.\s]*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    nums = []
    for p in prices:
        try:
            nums.append(float(p.replace(",", "")))
        except ValueError:
            continue
    # Also find standalone numbers (3-6 digits)
    if len(nums) < 2:
        standalone = re.findall(r"\b([\d,]{3,6}(?:\.\d{1,2})?)\b", text)
        for s in standalone:
            try:
                v = float(s.replace(",", ""))
                if 50 <= v <= 500000 and v not in nums:
                    nums.append(v)
            except ValueError:
                continue
    if len(nums) >= 2:
        return min(nums), max(nums)
    if len(nums) == 1:
        return nums[0], nums[0] * 1.5
    return 0.0, 0.0


def _make_product(
    title: str,
    url: str,
    price: float,
    mrp: float,
    source: str,
    image: str | None = None,
    rating: float | None = None,
    brand: str | None = None,
) -> Product:
    p = Product(
        source=source,
        title=title,
        url=url,
        image=image,
        price=price,
        mrp=mrp if mrp > price else price * 1.5,
        rating=rating,
        reviews=None,
        category=None,
        brand=brand,
    )
    return p


def scrape_flipkart(page, keyword: str) -> List[Product]:
    """Scrape Flipkart deals."""
    products = []
    try:
        kw = keyword.replace(" ", "%20")
        page.goto(f"https://www.flipkart.com/search?q={kw}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        # Close login popup if present
        try:
            close_btn = page.query_selector("button._2KpZ6l._2doB4z")
            if close_btn:
                close_btn.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

        items = page.query_selector_all("[data-id]")
        for item in items[:10]:
            try:
                link_el = item.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.flipkart.com" + href

                # Title
                title = ""
                t_el = item.query_selector("div._4rR01T, div.s1Q9rs, a[title]")
                if t_el:
                    title = t_el.get_attribute("title") or t_el.inner_text().strip()

                # Price
                price_el = item.query_selector("div._30jeq3")
                price = 0.0
                if price_el:
                    txt = price_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        price = float(match.group().replace(",", ""))

                # MRP
                mrp_el = item.query_selector("div._3I9_wc")
                mrp = 0.0
                if mrp_el:
                    txt = mrp_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        mrp = float(match.group().replace(",", ""))

                # Discount %
                disc_el = item.query_selector("div._3Ay6Sb")
                disc = 0
                if disc_el:
                    txt = disc_el.inner_text().strip()
                    match = re.search(r"(\d+)", txt)
                    if match:
                        disc = int(match.group())

                # Image
                img_el = item.query_selector("img")
                image = img_el.get_attribute("src") if img_el else None

                if not mrp or mrp < price:
                    mrp = price / (1 - disc / 100) if disc else price * 1.5

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "flipkart", image=image)
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[Flipkart] error: {e}")
    return products


def scrape_amazon(page, keyword: str) -> List[Product]:
    """Scrape Amazon deals."""
    products = []
    try:
        kw = keyword.replace(" ", "+")
        page.goto(f"https://www.amazon.in/s?k={kw}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all("[data-component-type='s-search-result']")
        for item in items[:10]:
            try:
                link_el = item.query_selector("h2 a")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.amazon.in" + href

                title_el = item.query_selector("h2 a span")
                title = title_el.inner_text().strip() if title_el else ""

                # Price
                price_el = item.query_selector(".a-price .a-offscreen")
                price = 0.0
                if price_el:
                    txt = price_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        price = float(match.group().replace(",", ""))

                # MRP
                mrp_el = item.query_selector(".a-text-price .a-offscreen")
                mrp = 0.0
                if mrp_el:
                    txt = mrp_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        mrp = float(match.group().replace(",", ""))

                # Image
                img_el = item.query_selector("img.s-image")
                image = img_el.get_attribute("src") if img_el else None

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "amazon", image=image)
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[Amazon] error: {e}")
    return products


def scrape_boat(page) -> List[Product]:
    """Scrape boAt deals from collections."""
    products = []
    try:
        page.goto("https://www.boat-lifestyle.com/collections/crazy-deals", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all(".product-card")
        for item in items[:8]:
            try:
                link_el = item.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.boat-lifestyle.com" + href

                title_el = item.query_selector(".product-card__title, .product-title, h3")
                title = title_el.inner_text().strip() if title_el else ""

                price_el = item.query_selector(".price--on-sale .price-item--sale, .sale-price")
                price = 0.0
                if price_el:
                    txt = price_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        price = float(match.group().replace(",", ""))

                mrp_el = item.query_selector(".price-item--regular, .original-price")
                mrp = 0.0
                if mrp_el:
                    txt = mrp_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        mrp = float(match.group().replace(",", ""))

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "boat", brand="boAt")
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[boAt] error: {e}")
    return products


def scrape_dotandkey(page) -> List[Product]:
    """Scrape Dot&Key deals."""
    products = []
    try:
        page.goto("https://www.dotandkey.com/collections/all", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all(".product-card")
        for item in items[:8]:
            try:
                link_el = item.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.dotandkey.com" + href

                title_el = item.query_selector(".product-card__title, .product-title, h3")
                title = title_el.inner_text().strip() if title_el else ""

                price_el = item.query_selector(".price--on-sale .price-item--sale, .sale-price")
                price = 0.0
                if price_el:
                    txt = price_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        price = float(match.group().replace(",", ""))

                mrp_el = item.query_selector(".price-item--regular, .original-price")
                mrp = 0.0
                if mrp_el:
                    txt = mrp_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        mrp = float(match.group().replace(",", ""))

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "dotandkey", brand="Dot&Key")
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[Dot&Key] error: {e}")
    return products


def scrape_snapdeal(page, keyword: str) -> List[Product]:
    """Scrape Snapdeal deals."""
    products = []
    try:
        kw = keyword.replace(" ", "%20")
        page.goto(f"https://www.snapdeal.com/search?keyword={kw}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all(".product-tuple-listing")
        for item in items[:8]:
            try:
                link_el = item.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""

                title_el = item.query_selector(".product-title")
                title = title_el.inner_text().strip() if title_el else ""

                price_el = item.query_selector(".product-price")
                price = 0.0
                if price_el:
                    txt = price_el.inner_text().strip()
                    match = re.search(r"[\d,]+", txt)
                    if match:
                        price = float(match.group().replace(",", ""))

                # MRP from "Rs. MRPRs. sale_price X% Off" text
                mrp = 0.0
                disc = 0
                price_text = item.inner_text()
                match = re.search(r"(\d+)%\s*Off", price_text)
                if match:
                    disc = int(match.group(1))
                if disc and price > 0:
                    mrp = price / (1 - disc / 100)

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "snapdeal")
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[Snapdeal] error: {e}")
    return products


def scrape_shopclues(page, keyword: str) -> List[Product]:
    """Scrape Shopclues deals."""
    products = []
    try:
        kw = keyword.replace(" ", "%20")
        page.goto(f"https://www.shopclues.com/search?q={kw}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all(".column.col3")
        for item in items[:8]:
            try:
                link_el = item.query_selector("a")
                full_text = link_el.inner_text().strip() if link_el else ""
                href = link_el.get_attribute("href") if link_el else ""

                # Title before first ₹
                title_match = re.match(r"^(.*?)(?:[₹])", full_text)
                title = title_match.group(1).strip() if title_match else full_text[:50]

                # Prices from text
                prices = re.findall(r"[₹Rs\.\s]*([\d,]+)", full_text, re.IGNORECASE)
                nums = []
                for p_str in prices:
                    try:
                        nums.append(float(p_str.replace(",", "")))
                    except ValueError:
                        continue

                price = min(nums) if nums else 0.0
                mrp = max(nums) if len(nums) > 1 else price * 1.5

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "shopclues")
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[Shopclues] error: {e}")
    return products


def scrape_tatacliq(page, keyword: str) -> List[Product]:
    """Scrape Tata CLiQ deals."""
    products = []
    try:
        kw = keyword.replace(" ", "%20")
        page.goto(f"https://www.tatacliq.com/search/?searchCategory=all&text={kw}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        items = page.query_selector_all(".ProductModule__base")
        for item in items[:8]:
            try:
                desc_el = item.query_selector(".ProductDescription__base")
                if not desc_el:
                    continue
                text = desc_el.inner_text().strip()

                link_el = item.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.tatacliq.com" + href

                # Title = first line
                lines = text.split("\n")
                title = lines[0].strip() if lines else ""

                # Extract prices
                prices = re.findall(r"[₹Rs\.\s]*([\d,]+)", text, re.IGNORECASE)
                nums = []
                for p_str in prices:
                    try:
                        nums.append(float(p_str.replace(",", "")))
                    except ValueError:
                        continue

                price = min(nums) if nums else 0.0
                mrp = max(nums) if len(nums) > 1 else price * 1.5

                if title and price > 0:
                    p = _make_product(title, href, price, mrp, "tatacliq")
                    if p.discount_pct >= 40:
                        products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"[TataCLiQ] error: {e}")
    return products


def main():
    """Main scrape loop."""
    print(f"[{datetime.now()}] Starting deal scrape...")

    # Keywords to scrape for
    keywords = [
        "mobile phone deals",
        "smartwatch offers",
        "headphones discount",
        "laptop deals",
        "skincare products offers",
        "fashion sale",
        "electronics offers",
    ]

    all_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-http2",
                "--disable-features=NetworkService,NetworkServiceInProcess",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Brand sites (don't need keywords)
        print("Scraping boAt...")
        page = browser.new_page()
        all_products.extend(scrape_boat(page))
        page.close()

        print("Scraping Dot&Key...")
        page = browser.new_page()
        all_products.extend(scrape_dotandkey(page))
        page.close()

        # Search-based sites
        for keyword in keywords:
            print(f"Scraping for: {keyword}")

            for scraper_fn, site_name in [
                (scrape_flipkart, "Flipkart"),
                (scrape_amazon, "Amazon"),
                (scrape_snapdeal, "Snapdeal"),
                (scrape_shopclues, "Shopclues"),
                (scrape_tatacliq, "TataCLiQ"),
            ]:
                try:
                    page = browser.new_page()
                    products = scraper_fn(page, keyword)
                    all_products.extend(products)
                    print(f"  {site_name}: {len(products)} products")
                    page.close()
                except Exception as e:
                    print(f"  {site_name} error: {e}")

        browser.close()

    # Deduplicate by URL
    seen_urls = set()
    unique_products = []
    for p in all_products:
        if p.url and p.url not in seen_urls:
            seen_urls.add(p.url)
            unique_products.append(p)

    # Sort by discount % desc
    unique_products.sort(key=lambda x: x.discount_pct, reverse=True)

    # Convert to dict for JSON
    deals_data = {
        "last_updated": datetime.now().isoformat(),
        "total": len(unique_products),
        "products": [
            {
                "source": p.source,
                "title": p.title,
                "url": p.url,
                "image": p.image,
                "price": p.price,
                "mrp": p.mrp,
                "discount_pct": p.discount_pct,
                "savings": p.savings,
                "rating": p.rating,
                "brand": p.brand,
            }
            for p in unique_products[:200]  # Keep top 200
        ],
    }

    # Save
    output_path = Path(__file__).parent / "deals.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deals_data, f, ensure_ascii=False, indent=2)

    print(f"\n[{datetime.now()}] Saved {len(unique_products)} unique deals to {output_path}")
    print(f"Top discounts: {[p.discount_pct for p in unique_products[:10]]}")


if __name__ == "__main__":
    main()

"""Product fetchers: mock data + RapidAPI adapters + web scrapers."""
from __future__ import annotations
import os
import random
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from urllib.parse import quote_plus, parse_qs, unquote

import requests

from .models import Product, SearchQuery

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except Exception:
    _HAS_BS4 = False


# ─── Helpers ────────────────────────────────────────────────────────────
def _extract_amazon_real_url(href: str, base_url: str = "https://www.amazon.in") -> str:
    """Extract real product URL from Amazon redirect/click-tracking links."""
    if not href:
        return ""
    # Sponsored products: /sspa/click?...&url=%2Fdp%2F...
    if "/sspa/click" in href:
        try:
            qs = href.split("?", 1)[1] if "?" in href else ""
            params = parse_qs(qs)
            real_path = params.get("url", [""])[0]
            if real_path:
                return base_url + unquote(real_path)
        except Exception:
            pass
    # Normal product links
    if href.startswith("http"):
        return href
    return base_url + href


def _add_amazon_affiliate(url: str) -> str:
    """Append Amazon affiliate tracking tag to product URLs."""
    if not url or "amazon.in" not in url:
        return url
    tag = os.getenv("AMAZON_AFFILIATE_TAG", "").strip()
    if not tag:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tag={tag}"


# ─── Constants ──────────────────────────────────────────────────────────
MOCK_CATEGORIES = [
    "Electronics", "Fashion", "Home & Kitchen", "Footwear", "Watches",
    "Beauty", "Mobiles", "Laptops", "TV & Appliances", "Sports"
]

MOCK_BRANDS = {
    "Electronics": ["Samsung", "Sony", "LG", "Boat", "Noise", "JBL"],
    "Fashion": ["Levi's", "Puma", "Adidas", "Nike", "US Polo", "Van Heusen"],
    "Home & Kitchen": ["Prestige", "Hawkins", "Milton", "Nirlon", "Sleepwell"],
    "Footwear": ["Bata", "Woodland", "Red Chief", "Puma", "Nike", "Adidas"],
    "Watches": ["Fastrack", "Titan", "Sonata", "Casio", "Timex"],
    "Beauty": ["Lakme", "Maybelline", "L'Oreal", "Nykaa", "Mamaearth"],
    "Mobiles": ["Samsung", "Xiaomi", "Realme", "Vivo", "Oppo", "Apple"],
    "Laptops": ["HP", "Dell", "Lenovo", "Asus", "Acer"],
    "TV & Appliances": ["LG", "Samsung", "Sony", "Panasonic", "Whirlpool"],
    "Sports": ["Nivia", "Cosco", "Yonex", "SG", "SS"],
}


# ─── Base Fetcher ───────────────────────────────────────────────────────
class ProductFetcher(ABC):
    source_name: str = ""

    @abstractmethod
    def search(self, q: SearchQuery) -> List[Product]:
        ...


# ─── Mock Fetchers ──────────────────────────────────────────────────────
class MockFetcher(ProductFetcher):
    """Generates realistic demo products for the given site."""

    def __init__(self, source_name: str, base_url: str, seed: int = 42):
        self.source_name = source_name
        self.base_url = base_url
        self._rng = random.Random(seed + hash(source_name))

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        n = self._rng.randint(8, 24)  # realistic result count

        for i in range(n):
            cat = self._rng.choice(MOCK_CATEGORIES)
            brand = self._rng.choice(MOCK_BRANDS.get(cat, ["Generic"]))
            title = self._generate_title(cat, brand)
            price, mrp = self._generate_prices()
            # Ensure discount requested
            if mrp == price:
                mrp = round(price * (1 + self._rng.uniform(0.55, 2.0)), 2)

            p = Product(
                source=self.source_name,
                title=title,
                url=f"{self.base_url}/product/{self._rng.randint(100000,999999)}",
                image=f"https://via.placeholder.com/200?text={self.source_name}+{cat.replace(' ','+')}",
                price=price,
                mrp=mrp,
                rating=round(self._rng.uniform(3.5, 4.9), 1),
                reviews=self._rng.randint(10, 5000),
                category=cat,
                brand=brand,
            )
            # filter by min_discount
            if p.discount_pct >= q.min_discount:
                results.append(p)
        return results

    def _generate_title(self, cat: str, brand: str) -> str:
        adjectives = ["Premium", "Original", "Trendy", "Stylish", "Durable",
                      "Lightweight", "Waterproof", "Smart", "Classic", "Modern"]
        suffixes = {
            "Electronics": "Bluetooth Speaker / Earbuds / Power Bank",
            "Fashion": "Shirt / Jeans / T-Shirt / Jacket / Kurta",
            "Home & Kitchen": "Cookware Set / Non-Stick Pan / Dinner Set",
            "Footwear": "Running Shoes / Casual Sneakers / Formal Shoes",
            "Watches": "Analog Watch / Digital Watch / Smartwatch",
            "Beauty": "Face Cream / Serum / Lipstick / Shampoo",
            "Mobiles": "Smartphone (64GB / 128GB)",
            "Laptops": "Laptop (i5 / 8GB RAM / 512GB SSD)",
            "TV & Appliances": "LED TV 43\" / Refrigerator / Washing Machine",
            "Sports": "Cricket Bat / Badminton Racket / Football",
        }
        adj = self._rng.choice(adjectives)
        return f"{brand} {adj} {suffixes.get(cat, 'Product')}"

    def _generate_prices(self) -> tuple[float, float]:
        price = round(self._rng.uniform(299, 4999), 2)
        mrp = round(price * (1 + self._rng.uniform(0.55, 2.5)), 2)
        return price, mrp


# ─── RapidAPI Adapters ───────────────────────────────────────────────────
class RapidAPIAmazonFetcher(ProductFetcher):
    """Amazon search via RapidAPI real-time-amazon-data endpoint."""

    source_name = "amazon"

    def __init__(self, api_key: str, host: str = "real-time-amazon-data.p.rapidapi.com"):
        self.api_key = api_key
        self.host = host
        self.base_url = f"https://{host}"
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": host,
        }

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        try:
            # This maps to the typical RapidAPI Amazon search endpoint.
            # Adjust query parameters per your RapidAPI plan.
            resp = requests.get(
                f"{self.base_url}/search",
                headers=self.headers,
                params={
                    "query": q.keywords,
                    "country": "IN",
                    "page": "1",
                    "category_id": q.category or "aps",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("products", [])
            for item in data:
                try:
                    price = self._parse_price(item.get("product_price", "0"))
                    mrp = self._parse_price(item.get("product_original_price", "0")) or price
                    rating = self._to_float(item.get("product_star_rating"))
                    reviews = int(item.get("product_num_ratings", 0) or 0)
                    p = Product(
                        source="amazon",
                        title=item.get("product_title", "") or "",
                        url=item.get("product_url", "") or "",
                        image=item.get("product_photo", ""),
                        price=price,
                        mrp=mrp,
                        rating=rating,
                        reviews=reviews,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            # Return empty so UI can show a warning
            print(f"[Amazon RapidAPI] error: {e}")
        return results

    @staticmethod
    def _parse_price(val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace("₹", "").replace(",", "").replace("$", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _to_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


class RapidAPIFlipkartFetcher(ProductFetcher):
    """Flipkart search via RapidAPI real-time-flipkart-api endpoint."""

    source_name = "flipkart"

    def __init__(self, api_key: str, host: str = "real-time-flipkart-api.p.rapidapi.com"):
        self.api_key = api_key
        self.host = host
        self.base_url = f"https://{host}"
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": host,
        }

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        try:
            resp = requests.get(
                f"{self.base_url}/search",
                headers=self.headers,
                params={
                    "query": q.keywords,
                    "page": "1",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("products", [])
            for item in data:
                try:
                    price = self._parse_price(item.get("price", "0"))
                    mrp = self._parse_price(item.get("original_price", "0")) or price
                    rating = self._to_float(item.get("rating"))
                    reviews = int(item.get("number_of_reviews", 0) or 0)
                    p = Product(
                        source="flipkart",
                        title=item.get("title", "") or "",
                        url=item.get("url", "") or "",
                        image=item.get("thumbnail", ""),
                        price=price,
                        mrp=mrp,
                        rating=rating,
                        reviews=reviews,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[Flipkart RapidAPI] error: {e}")
        return results

    @staticmethod
    def _parse_price(val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace("₹", "").replace(",", "").replace("$", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _to_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


# ─── Google Custom Search (free 100 queries/day) ───────────────────────
class GoogleCustomSearchFetcher(ProductFetcher):
    """Search across Indian e-commerce sites via Google Custom Search.
    Free tier: 100 queries/day.
    Setup: https://programmablesearchengine.google.com/ + Google Cloud API key.
    """

    source_name = "google"

    def __init__(self, api_key: str, cx: str):
        self.api_key = api_key
        self.cx = cx
        self.base_url = "https://www.googleapis.com/customsearch/v1"

    # Map source names to actual domains for Google site: filter
    _SITE_DOMAINS = {
        "amazon": "amazon.in",
        "flipkart": "flipkart.com",
        "myntra": "myntra.com",
        "ajio": "ajio.com",
        "tatacliq": "tatacliq.com",
        "nykaa": "nykaafashion.com",
        "meesho": "meesho.com",
        "snapdeal": "snapdeal.com",
        "shopclues": "shopclues.com",
        "limeroad": "limeroad.com",
        "shopsy": "shopsy.in",
        "oppo": "oppo.com",
        "realme": "realme.com",
        "boat": "boat-lifestyle.com",
        "dotandkey": "dotandkey.com",
    }

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        api_error: str | None = None
        try:
            # Restrict to Indian shopping sites using real domains
            site_filter = " OR ".join(
                f"site:{self._SITE_DOMAINS.get(s, s)}"
                for s in q.sources
                if s in self._SITE_DOMAINS
            )
            query = f"{q.keywords} ({site_filter})" if site_filter else q.keywords

            resp = requests.get(
                self.base_url,
                params={
                    "key": self.api_key,
                    "cx": self.cx,
                    "q": query,
                    "num": 10,
                    "gl": "in",  # India geo
                    "hl": "en",
                },
                timeout=20,
            )
            # Log API errors but don't crash the whole search
            if resp.status_code != 200:
                try:
                    err = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    err = resp.text
                api_error = f"Google API error ({resp.status_code}): {err}"
                print(api_error)
                self._last_error = api_error
                return results

            data = resp.json()
            items = data.get("items", [])

            for item in items:
                try:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    snippet = item.get("snippet", "")
                    pagemap = item.get("pagemap", {})

                    # Try to extract price from rich snippets or snippet text
                    price, mrp = self._extract_price(title + " " + snippet)
                    if price == 0:
                        price, mrp = self._extract_price_from_pagemap(pagemap)

                    # Detect source from URL
                    source = self._detect_source(link)

                    # Try to extract rating from snippet
                    rating = self._extract_rating(snippet)

                    p = Product(
                        source=source,
                        title=title,
                        url=link,
                        image=None,
                        price=price,
                        mrp=mrp if mrp > price else price * 1.5,
                        rating=rating,
                        reviews=None,
                        category=q.category,
                        brand=None,
                    )
                    # Include if we have real prices and discount matches,
                    # OR if price extraction failed (Google already found relevant results)
                    if price > 0 and p.discount_pct >= q.min_discount:
                        results.append(p)
                    elif price == 0:
                        # Can't extract price from snippet, but Google found it — include it
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            api_error = api_error or str(e)
            print(f"[Google Custom Search] error: {api_error}")
            # Store error so the UI can show it
            self._last_error = api_error
        return results

    @staticmethod
    def _detect_source(url: str) -> str:
        url_l = url.lower()
        if "amazon" in url_l:
            return "amazon"
        if "flipkart" in url_l:
            return "flipkart"
        if "myntra" in url_l:
            return "myntra"
        return "other"

    @staticmethod
    def _extract_price(text: str) -> tuple[float, float]:
        """Extract ₹ price patterns from text."""
        import re
        # Look for ₹1,999 / Rs. 1999 / INR 1999 / Price: 1,999 / MRP: 1,999
        pattern = r"(?:₹|Rs\.?|INR|MRP|Price)[\s\.]*([\d,]+(?:\.\d{1,2})?)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        nums = []
        for m in matches:
            try:
                nums.append(float(m.replace(",", "")))
            except ValueError:
                continue
        # Also grab standalone 4-digit numbers (likely prices in Indian context)
        if len(nums) < 2:
            standalone = re.findall(r"\b([\d,]{3,5}(?:\.\d{1,2})?)\b", text)
            for m in standalone:
                try:
                    v = float(m.replace(",", ""))
                    if 100 <= v <= 500000 and v not in nums:  # Reasonable price range
                        nums.append(v)
                except ValueError:
                    continue
        if len(nums) >= 2:
            return min(nums), max(nums)
        if len(nums) == 1:
            return nums[0], nums[0] * 1.5
        return 0.0, 0.0

    @staticmethod
    def _extract_price_from_pagemap(pagemap: dict) -> tuple[float, float]:
        """Try rich snippet price data."""
        offer = pagemap.get("offer", [{}])[0]
        price_str = offer.get("price") or offer.get("lowprice") or offer.get("highprice")
        if price_str:
            try:
                price = float(str(price_str).replace(",", ""))
                return price, price * 1.5
            except ValueError:
                pass
        return 0.0, 0.0

    @staticmethod
    def _extract_rating(text: str) -> Optional[float]:
        import re
        m = re.search(r"(\d\.\d)\s*star", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None


# ─── Amazon PA-API (free with Associates account) ────────────────────────
class AmazonPAAPIFetcher(ProductFetcher):
    """Amazon Product Advertising API v5 — free if you have an Amazon Associates account.
    Docs: https://webservices.amazon.com/paapi5/documentation/
    """

    source_name = "amazon"

    def __init__(self, access_key: str, secret_key: str, partner_tag: str, region: str = "in"):
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.region = region
        self.host = f"webservices.amazon.{region}"
        self.base_url = f"https://{self.host}"

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        try:
            payload = {
                "Keywords": q.keywords,
                "SearchIndex": "All",
                "ItemPage": 1,
                "Resources": [
                    "Images.Primary.Large",
                    "ItemInfo.Title",
                    "Offers.Listings.Price",
                    "CustomerReviews.StarRating",
                ],
                "PartnerTag": self.partner_tag,
                "PartnerType": "Associates",
                "Marketplace": f"www.amazon.{self.region}",
            }
            resp = self._signed_request("/paapi5/searchitems", payload)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("SearchResult", {}).get("Items", [])
            for item in items:
                try:
                    info = item.get("ItemInfo", {})
                    title = info.get("Title", {}).get("DisplayValue", "")
                    offers = item.get("Offers", {}).get("Listings", [{}])[0]
                    price_data = offers.get("Price", {})
                    price = self._parse_amt(price_data.get("Amount"))
                    currency = price_data.get("Currency", "INR")
                    # For MRP, use Savings.BasePrice if available, else estimate
                    savings = offers.get("SavingBasis", {})
                    mrp = self._parse_amt(savings.get("Amount")) or price * 1.5
                    reviews = item.get("CustomerReviews", {})
                    rating = self._to_float(reviews.get("StarRating", {}).get("Value"))
                    image = item.get("Images", {}).get("Primary", {}).get("Large", {}).get("URL")
                    p = Product(
                        source="amazon",
                        title=title,
                        url=item.get("DetailPageURL", ""),
                        image=image,
                        price=price,
                        mrp=mrp,
                        rating=rating,
                        reviews=None,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[Amazon PA-API] error: {e}")
        return results

    def _signed_request(self, path: str, payload: dict):
        """Sign request with AWS SigV4 for PA-API."""
        import hashlib
        import hmac
        import json
        from datetime import datetime

        service = "ProductAdvertisingAPI"
        region = self.region
        amz_date = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        date_stamp = datetime.utcnow().strftime("%Y%m%d")

        body = json.dumps(payload, separators=(",", ":"))
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers = {
            "Host": self.host,
            "Content-Type": "application/json; charset=utf-8",
            "X-Amz-Date": amz_date,
            "X-Amz-Target": f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
        }

        # Canonical request
        canonical_headers = ""
        signed_headers_list = ["content-type", "host", "x-amz-date", "x-amz-target"]
        for h in signed_headers_list:
            canonical_headers += f"{h}:{headers[h]}\n"
        signed_headers = ";".join(signed_headers_list)

        canonical_request = (
            f"POST\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        # String to sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = (
            f"{algorithm}\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # Signing key
        k_date = hmac.new(
            f"AWS4{self.secret_key}".encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

        # Signature
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        auth_header = (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers["Authorization"] = auth_header

        return requests.post(f"{self.base_url}{path}", headers=headers, data=body, timeout=20)

    @staticmethod
    def _parse_amt(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _to_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


# ─── Scraper fetchers (no API keys needed) ──────────────────────────────
class AmazonScraperFetcher(ProductFetcher):
    """Scrape Amazon India search results directly."""
    source_name = "amazon"

    def __init__(self, base_url: str = "https://www.amazon.in"):
        self.base_url = base_url.rstrip("/")

    def search(self, q: SearchQuery) -> List[Product]:
        if not _HAS_BS4:
            return []
        results: list[Product] = []
        try:
            kw = quote_plus(q.keywords)
            url = f"{self.base_url}/s?k={kw}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Amazon uses data-component-type="s-search-result" for search items
            items = soup.find_all("div", attrs={"data-component-type": "s-search-result"})
            for item in items[:10]:
                try:
                    link_tag = item.find("a", class_="a-link-normal")
                    href = link_tag.get("href", "") if link_tag else ""
                    if href:
                        href = _extract_amazon_real_url(href, self.base_url)
                    href = _add_amazon_affiliate(href)

                    title_tag = item.find("span", class_="a-text-normal") or item.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else ""

                    price_whole = item.find("span", class_="a-price-whole")
                    price_frac = item.find("span", class_="a-price-fraction")
                    price = 0.0
                    if price_whole:
                        p_text = price_whole.get_text(strip=True).replace(",", "").replace("₹", "")
                        if price_frac:
                            p_text += "." + price_frac.get_text(strip=True).replace(",", "")
                        try:
                            price = float(p_text)
                        except ValueError:
                            pass

                    # MRP from a-text-price (strikethrough)
                    mrp_tag = item.find("span", class_="a-text-price")
                    mrp = 0.0
                    if mrp_tag:
                        mrp_span = mrp_tag.find("span", class_="a-offscreen")
                        if mrp_span:
                            try:
                                mrp = float(
                                    mrp_span.get_text(strip=True).replace("₹", "").replace(",", "")
                                )
                            except ValueError:
                                pass

                    if not mrp or mrp < price:
                        mrp = price * 1.5 if price else 999

                    img_tag = item.find("img", class_="s-image")
                    image = img_tag.get("src") if img_tag else None

                    p = Product(
                        source="amazon",
                        title=title,
                        url=href,
                        image=image,
                        price=price,
                        mrp=mrp,
                        rating=None,
                        reviews=None,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[AmazonScraper] error: {e}")
        return results


class FlipkartScraperFetcher(ProductFetcher):
    """Scrape Flipkart search results directly."""
    source_name = "flipkart"

    def __init__(self, base_url: str = "https://www.flipkart.com"):
        self.base_url = base_url.rstrip("/")

    def search(self, q: SearchQuery) -> List[Product]:
        if not _HAS_BS4:
            return []
        results: list[Product] = []
        try:
            kw = quote_plus(q.keywords)
            url = f"{self.base_url}/search?q={kw}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Flipkart product rows
            items = soup.find_all("div", class_=re.compile("_1AtVbE|_2kHMtA"))
            for item in items[:10]:
                try:
                    link_tag = item.find("a", class_=re.compile("_1fQZEK|s1Q9rs"))
                    href = link_tag.get("href", "") if link_tag else ""
                    if href and not href.startswith("http"):
                        href = self.base_url + href

                    title_tag = item.find("div", class_=re.compile("_4rR01T|s1Q9rs"))
                    title = title_tag.get_text(strip=True) if title_tag else ""

                    price_tag = item.find("div", class_=re.compile("_30jeq3"))
                    price = 0.0
                    if price_tag:
                        try:
                            price = float(
                                price_tag.get_text(strip=True).replace("₹", "").replace(",", "")
                            )
                        except ValueError:
                            pass

                    mrp_tag = item.find("div", class_=re.compile("_3I9_wc"))
                    mrp = 0.0
                    if mrp_tag:
                        try:
                            mrp = float(
                                mrp_tag.get_text(strip=True).replace("₹", "").replace(",", "")
                            )
                        except ValueError:
                            pass

                    if not mrp or mrp < price:
                        mrp = price * 1.5 if price else 999

                    img_tag = item.find("img", class_=re.compile("_396cs4|_2r_T1I"))
                    image = img_tag.get("src") if img_tag else None

                    p = Product(
                        source="flipkart",
                        title=title,
                        url=href,
                        image=image,
                        price=price,
                        mrp=mrp,
                        rating=None,
                        reviews=None,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[FlipkartScraper] error: {e}")
        return results


class MyntraScraperFetcher(ProductFetcher):
    """Scrape Myntra search results directly."""
    source_name = "myntra"

    def __init__(self, base_url: str = "https://www.myntra.com"):
        self.base_url = base_url.rstrip("/")

    def search(self, q: SearchQuery) -> List[Product]:
        if not _HAS_BS4:
            return []
        results: list[Product] = []
        try:
            kw = q.keywords.replace(" ", "-")
            url = f"{self.base_url}/{kw}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            items = soup.find_all("li", class_=re.compile("product-base"))
            for item in items[:10]:
                try:
                    link_tag = item.find("a")
                    href = link_tag.get("href", "") if link_tag else ""
                    if href and not href.startswith("http"):
                        href = self.base_url + href

                    title_tag = item.find("h3", class_=re.compile("product-brand")) or item.find("h4", class_=re.compile("product-product"))
                    title = title_tag.get_text(strip=True) if title_tag else ""

                    # Myntra prices
                    price_tag = item.find("span", class_=re.compile("product-discountedPrice")) or item.find("span", class_=re.compile("product-price"))
                    price = 0.0
                    if price_tag:
                        try:
                            price = float(
                                price_tag.get_text(strip=True).replace("Rs. ", "").replace("₹", "").replace(",", "")
                            )
                        except ValueError:
                            pass

                    mrp_tag = item.find("span", class_=re.compile("product-strike"))
                    mrp = 0.0
                    if mrp_tag:
                        try:
                            mrp = float(
                                mrp_tag.get_text(strip=True).replace("Rs. ", "").replace("₹", "").replace(",", "")
                            )
                        except ValueError:
                            pass

                    if not mrp or mrp < price:
                        mrp = price * 1.5 if price else 999

                    img_tag = item.find("img", class_=re.compile("img-responsive"))
                    image = img_tag.get("src") if img_tag else None

                    p = Product(
                        source="myntra",
                        title=title,
                        url=href,
                        image=image,
                        price=price,
                        mrp=mrp,
                        rating=None,
                        reviews=None,
                        category=q.category,
                        brand=None,
                    )
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[MyntraScraper] error: {e}")
        return results


# ─── Playwright scraper (handles JS-rendered sites) ─────────────────────
try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except Exception:
    _HAS_PLAYWRIGHT = False


class PlaywrightScraperFetcher(ProductFetcher):
    """Headless browser scraper using Playwright. Handles JS-rendered pages."""
    source_name = "playwright"

    def __init__(self, target_sites=None):
        self.target_sites = target_sites

    def _scrape_site(self, page, url: str, selectors: dict, source: str, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(3000)  # Wait for JS to load content

            # Try to find product containers
            items = page.query_selector_all(selectors["container"])
            if not items:
                # Fallback: try alternative selectors
                for alt in selectors.get("alt_containers", []):
                    items = page.query_selector_all(alt)
                    if items:
                        break

            for item in items[:12]:
                try:
                    # Title
                    title_el = item.query_selector(selectors["title"])
                    title = title_el.inner_text().strip() if title_el else ""

                    # Link
                    link_el = item.query_selector(selectors["link"])
                    href = ""
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                    if href:
                        href = _extract_amazon_real_url(href, selectors.get("base_url", "https://www.amazon.in"))
                    href = _add_amazon_affiliate(href)

                    # Price
                    price = 0.0
                    price_el = item.query_selector(selectors["price"])
                    if price_el:
                        p_text = price_el.inner_text().strip().replace("₹", "").replace(",", "").replace("Rs.", "").replace(" ", "")
                        try:
                            price = float(p_text)
                        except ValueError:
                            pass

                    # MRP
                    mrp = 0.0
                    mrp_el = item.query_selector(selectors["mrp"])
                    if mrp_el:
                        m_text = mrp_el.inner_text().strip().replace("₹", "").replace(",", "").replace("Rs.", "").replace(" ", "")
                        try:
                            mrp = float(m_text)
                        except ValueError:
                            pass

                    if not mrp or mrp < price:
                        mrp = price * 1.5 if price else 999

                    # Image
                    img = ""
                    img_el = item.query_selector(selectors["image"])
                    if img_el:
                        img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                    if title and href and price > 0:
                        p = Product(
                            source=source,
                            title=title,
                            url=href,
                            image=img,
                            price=price,
                            mrp=mrp,
                            rating=None,
                            reviews=None,
                            category=q.category,
                            brand=None,
                        )
                        if p.discount_pct >= q.min_discount:
                            results.append(p)
                except Exception:
                    continue
        except Exception as e:
            print(f"[Playwright {source}] error: {e}")
        return results

    def search(self, q: SearchQuery) -> List[Product]:
        if not _HAS_PLAYWRIGHT:
            print("[Playwright] not installed — run: python -m playwright install chromium")
            return []

        # If configured for specific sites only, filter sources
        if self.target_sites:
            q = SearchQuery(
                keywords=q.keywords,
                min_discount=q.min_discount,
                max_price=q.max_price,
                min_price=q.min_price,
                category=q.category,
                sources=[s for s in q.sources if s in self.target_sites],
                min_rating=q.min_rating,
            )

        results: list[Product] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-http2",
                    "--disable-features=NetworkService,NetworkServiceInProcess",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            # Short page timeout — sites that don't load in 10s won't load in 30s
            PAGE_TIMEOUT = 10000
            kw = quote_plus(q.keywords)

            # Amazon - separate page to avoid cross-site contamination
            if "amazon" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                results.extend(self._scrape_site(
                    page,
                    f"https://www.amazon.in/s?k={kw}",
                    {
                        "base_url": "https://www.amazon.in",
                        "container": "[data-component-type='s-search-result']",
                        "alt_containers": [".s-result-item"],
                        "title": "h2 a span, .a-text-normal",
                        "link": "h2 a, .a-link-normal",
                        "price": ".a-price .a-offscreen, .a-price-whole",
                        "mrp": ".a-text-price .a-offscreen",
                        "image": ".s-image",
                    },
                    "amazon",
                    q,
                ))
                ctx.close()

            # Flipkart - separate page
            if "flipkart" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                page.goto(f"https://www.flipkart.com/search?q={kw}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                page.wait_for_timeout(3000)
                try:
                    close_btn = page.query_selector("button._2KpZ6l._2doB4z")
                    if close_btn:
                        close_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                items = page.query_selector_all("[data-id]")
                for item in items[:12]:
                    try:
                        title = ""
                        href = ""
                        links = item.query_selector_all("a")
                        for link in links:
                            text = link.inner_text().strip()
                            if text and len(text) > 10:
                                title = text
                                href = link.get_attribute("href") or ""
                                break
                        if href and not href.startswith("http"):
                            href = "https://www.flipkart.com" + href

                        # Extract prices from individual elements to avoid text concatenation
                        price = 0.0
                        mrp = 0.0
                        nums = []
                        # Find all child elements containing currency symbol
                        for el in item.query_selector_all("*"):
                            try:
                                text = el.inner_text().strip()
                                if "\u20b9" not in text and "Rs." not in text:
                                    continue
                                # Skip if this element contains "off" (discount text)
                                if "% off" in text.lower():
                                    continue
                                # Extract number from this element
                                found = re.findall(r"[\u20b9Rs.]*\s*(\d[\d,]*(?:\.\d+)?)", text)
                                for f in found:
                                    try:
                                        val = float(f.replace(",", ""))
                                        if 10 < val < 100000:
                                            nums.append(val)
                                    except ValueError:
                                        pass
                            except Exception:
                                pass

                        if nums:
                            nums = sorted(set(nums))
                            price = nums[0]
                            mrp = nums[-1] if len(nums) > 1 else price * 1.5

                        if not mrp or mrp < price:
                            mrp = price * 1.5 if price else 999

                        img = ""
                        img_el = item.query_selector("img")
                        if img_el:
                            img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                        if title and href and price > 0:
                            p = Product(
                                source="flipkart",
                                title=title,
                                url=href,
                                image=img,
                                price=price,
                                mrp=mrp,
                                rating=None,
                                reviews=None,
                                category=q.category,
                                brand=None,
                            )
                            if p.discount_pct >= q.min_discount:
                                results.append(p)
                    except Exception:
                        continue
                ctx.close()

            # Myntra - separate page
            if "myntra" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    results.extend(self._scrape_site(
                        page,
                        f"https://www.myntra.com/{q.keywords.replace(' ', '-')}",
                        {
                            "base_url": "https://www.myntra.com",
                            "container": "li.product-base",
                            "alt_containers": [".product-base"],
                            "title": "h3.product-brand, h4.product-product",
                            "link": "a",
                            "price": "span.product-discountedPrice, span.product-price",
                            "mrp": "span.product-strike",
                            "image": "img.img-responsive",
                        },
                        "myntra",
                        q,
                    ))
                except Exception as e:
                    print(f"[Playwright myntra] error: {e}")
                ctx.close()

            # Ajio
            if "ajio" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    results.extend(self._scrape_site(
                        page,
                        f"https://www.ajio.com/search/?text={kw}",
                        {
                            "base_url": "https://www.ajio.com",
                            "container": ".item.rilrtl-products-list__item, .product",
                            "alt_containers": [".rilrtl-products-list__item", ".plp-product-card"],
                            "title": ".name, .nameCls, h2",
                            "link": "a",
                            "price": ".price, .orginal-price, .discounted-price",
                            "mrp": ".orginal-price, .striked-price, .line-through",
                            "image": "img",
                        },
                        "ajio",
                        q,
                    ))
                except Exception as e:
                    print(f"[Playwright ajio] error: {e}")
                ctx.close()

            # Tata CLiQ
            if "tatacliq" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto(f"https://www.tatacliq.com/search/?searchCategory=all&text={kw}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    page_title = page.title()
                    page_url = page.url
                    items = page.query_selector_all(".ProductModule__base")
                    print(f"[Playwright tatacliq] Page: {page_url} | Title: {page_title} | Items found: {len(items)}")
                    for item in items[:12]:
                        try:
                            desc_el = item.query_selector(".ProductDescription__base")
                            if not desc_el:
                                continue
                            text = desc_el.inner_text().strip()

                            # Extract prices from text (e.g., "BrandTitle₹1499" or "Title₹1724₹249931%")
                            prices = re.findall(r'[₹]\s*([\d,]+)', text)
                            if len(prices) >= 2:
                                price = float(prices[0].replace(",", ""))
                                # Second price may be MRP + discount% concatenated (e.g., "249931" = 2499 + 31%)
                                mrp_str = prices[1].replace(",", "")
                                mrp_val = float(mrp_str)
                                if mrp_val > price * 10:
                                    # Find split where left part is a reasonable MRP (> price)
                                    for i in range(1, len(mrp_str)):
                                        left = float(mrp_str[:i])
                                        if left > price:
                                            mrp = left
                                            break
                                    else:
                                        mrp = mrp_val
                                else:
                                    mrp = mrp_val
                            elif len(prices) == 1:
                                price = float(prices[0].replace(",", ""))
                                mrp = price * 1.5
                            else:
                                continue

                            # Title is everything before first ₹
                            title_match = re.match(r'^(.*?)(?:[₹])', text)
                            title = title_match.group(1).strip() if title_match else text

                            # Link
                            link_el = item.query_selector("a")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = "https://www.tatacliq.com" + href

                            # Image - skip icons and empty placeholders
                            img = ""
                            for img_candidate in item.query_selector_all("img"):
                                src = img_candidate.get_attribute("src") or img_candidate.get_attribute("data-src") or ""
                                # Skip non-product images (icons, stars, empty placeholders)
                                if not src or "star" in src.lower() or "icon" in src.lower() or "placeholder" in src.lower():
                                    continue
                                if src.startswith("//img.tatacliq.com"):
                                    img = "https:" + src
                                    break
                                elif src.startswith("//"):
                                    img = "https:" + src
                                    break
                                elif src.startswith("http"):
                                    img = src
                                    break
                                elif src.startswith("/") and "." in src.split("/")[-1]:
                                    # Relative product image path
                                    img = "https://www.tatacliq.com" + src
                                    break

                            if not mrp or mrp < price:
                                mrp = price * 1.5 if price else 999

                            if title and href and price > 0:
                                p = Product(
                                    source="tatacliq",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand=None,
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright tatacliq] error: {e}")
                ctx.close()

            # Nykaa Fashion
            if "nykaa" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    results.extend(self._scrape_site(
                        page,
                        f"https://www.nykaafashion.com/search/?q={kw}",
                        {
                            "base_url": "https://www.nykaafashion.com",
                            "container": ".productWrapper, .product-wrapper, .css-1rd7evk",
                            "alt_containers": [".css-1rd7evk", ".product-base"],
                            "title": ".css-xrzmfa, .product-title, h3",
                            "link": "a",
                            "price": ".css-1jczs19, .price, .discounted-price",
                            "mrp": ".css-17x46, .mrp, .striked-price",
                            "image": "img",
                        },
                        "nykaa",
                        q,
                    ))
                except Exception as e:
                    print(f"[Playwright nykaa] error: {e}")
                ctx.close()

            # Meesho
            if "meesho" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    results.extend(self._scrape_site(
                        page,
                        f"https://www.meesho.com/search?q={kw}",
                        {
                            "base_url": "https://www.meesho.com",
                            "container": ".NewProductCard, .ProductList__GridCol, .product-card",
                            "alt_containers": [".product-card", ".ProductCard"],
                            "title": ".ProductCard__Title, h4, .product-title",
                            "link": "a",
                            "price": ".ProductCard__Price, .price, .discounted-price",
                            "mrp": ".ProductCard__DiscountedPrice, .mrp, .original-price",
                            "image": "img",
                        },
                        "meesho",
                        q,
                    ))
                except Exception as e:
                    print(f"[Playwright meesho] error: {e}")
                ctx.close()

            # Snapdeal
            if "snapdeal" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto(f"https://www.snapdeal.com/search?keyword={kw}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    items = page.query_selector_all(".product-tuple-listing")
                    for item in items[:12]:
                        try:
                            title_el = item.query_selector(".product-title")
                            title = title_el.inner_text().strip() if title_el else ""

                            link_el = item.query_selector("a")
                            href = link_el.get_attribute("href") if link_el else ""

                            # Price text contains "Rs. MRPRs. sale_price X% Off"
                            price_el = item.query_selector(".product-price")
                            mrp_el = item.query_selector(".product-mrp")

                            price = 0.0
                            mrp = 0.0

                            if price_el:
                                p_text = price_el.inner_text().strip()
                                nums = re.findall(r'Rs\.\s*([\d,]+)', p_text)
                                if len(nums) >= 2:
                                    # First number is MRP (struck), second is sale price
                                    mrp = float(nums[0].replace(",", ""))
                                    # Second number may be sale price + discount% concatenated
                                    price_str = nums[1].replace(",", "")
                                    price_val = float(price_str)
                                    if price_val > mrp:
                                        # Find split where left part is a reasonable sale price (< mrp)
                                        for i in range(1, len(price_str)):
                                            left = float(price_str[:i])
                                            if left < mrp and left > 0:
                                                price = left
                                                break
                                        else:
                                            price = price_val
                                    else:
                                        price = price_val
                                elif len(nums) == 1:
                                    price = float(nums[0].replace(",", ""))
                                    mrp = price * 1.5

                            if mrp_el and mrp == 0:
                                m_text = mrp_el.inner_text().strip()
                                m_nums = re.findall(r'[\d,]+', m_text.replace("Rs.", "").replace(" ", ""))
                                if m_nums:
                                    mrp = float(m_nums[0].replace(",", ""))

                            if not mrp or mrp < price:
                                mrp = price * 1.5 if price else 999

                            # Image
                            img_el = item.query_selector("img")
                            img = ""
                            if img_el:
                                img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                            if title and href and price > 0:
                                p = Product(
                                    source="snapdeal",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand=None,
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright snapdeal] error: {e}")
                ctx.close()

            # Shopclues
            if "shopclues" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto(f"https://www.shopclues.com/search?q={kw}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    items = page.query_selector_all(".column.col3")
                    for item in items[:12]:
                        try:
                            # Title from anchor text - everything before first ₹
                            link_el = item.query_selector("a")
                            full_text = link_el.inner_text().strip() if link_el else ""
                            title_match = re.match(r'^(.*?)(?:[₹])', full_text)
                            title = title_match.group(1).strip() if title_match else full_text

                            # Link
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and href.startswith("//"):
                                href = "https:" + href

                            # Price
                            price = 0.0
                            price_el = item.query_selector(".p_price")
                            if price_el:
                                p_text = price_el.inner_text().strip()
                                nums = re.findall(r'[₹]\s*([\d,]+)', p_text)
                                if nums:
                                    price = float(nums[0].replace(",", ""))

                            # MRP from full item text
                            mrp = 0.0
                            all_text = item.inner_text().strip()
                            prices = re.findall(r'[₹]\s*([\d,]+)', all_text)
                            if len(prices) >= 2:
                                mrp = float(prices[1].replace(",", ""))
                            elif price > 0:
                                mrp = price * 2

                            if not mrp or mrp < price:
                                mrp = price * 2 if price else 999

                            # Image
                            img = ""
                            img_el = item.query_selector("img")
                            if img_el:
                                img = img_el.get_attribute("src") or ""

                            if title and href and price > 0:
                                p = Product(
                                    source="shopclues",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand=None,
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright shopclues] error: {e}")
                ctx.close()

            # Limeroad
            if "limeroad" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto(f"https://www.limeroad.com/search?q={kw}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    # Scroll to trigger lazy loading
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        page.wait_for_timeout(1000)
                    items = page.query_selector_all(".plpTile, .product-card, .plp-card, .plp-product-card")
                    for item in items[:12]:
                        try:
                            title_el = item.query_selector(".name, .product-name, .product-title")
                            title = title_el.inner_text().strip() if title_el else ""

                            link_el = item.query_selector("a")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = "https://www.limeroad.com" + href

                            price = 0.0
                            mrp = 0.0
                            price_el = item.query_selector(".selling-price, .price")
                            if price_el:
                                p_text = price_el.inner_text().strip()
                                nums = re.findall(r'[₹]\s*([\d,]+)', p_text)
                                if nums:
                                    price = float(nums[0].replace(",", ""))

                            mrp_el = item.query_selector(".mrp, .original-price")
                            if mrp_el:
                                m_text = mrp_el.inner_text().strip()
                                m_nums = re.findall(r'[₹]\s*([\d,]+)', m_text)
                                if m_nums:
                                    mrp = float(m_nums[0].replace(",", ""))

                            if not mrp or mrp < price:
                                mrp = price * 1.5 if price else 999

                            img = ""
                            img_el = item.query_selector("img")
                            if img_el:
                                img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                            if title and href and price > 0:
                                p = Product(
                                    source="limeroad",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand=None,
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright limeroad] error: {e}")
                ctx.close()

            # Shopsy (Flipkart's social commerce platform)
            if "shopsy" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    results.extend(self._scrape_site(
                        page,
                        f"https://www.shopsy.in/search?q={kw}",
                        {
                            "base_url": "https://www.shopsy.in",
                            "container": "._1AtVbE, ._2kHMtA, .CXW8mj",
                            "alt_containers": ["._1fQZEK", "._1xHGtK", "._4ddWXP"],
                            "title": "._4rR01T, .s1Q9rs, .IRpwTa",
                            "link": "a",
                            "price": "._30jeq3, ._8VNy32, .Nx9bqj",
                            "mrp": "._3I9_wc, ._3Ay6Sb",
                            "image": "img",
                        },
                        "shopsy",
                        q,
                    ))
                except Exception as e:
                    print(f"[Playwright shopsy] error: {e}")
                ctx.close()

            # OPPO India (D2C brand site)
            if "oppo" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto("https://www.oppo.com/in/smartphones/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    
                    # OPPO page structure: look for divs/spans containing both model name and price
                    # Try common product container patterns
                    containers = page.query_selector_all(".product-card, .product-item, .goods-item, .phone-item, .model-card, div[class*='product']")
                    if not containers:
                        # Fallback: look for any elements with both OPPO model and ₹
                        all_divs = page.query_selector_all("div, span, p")
                        seen = set()
                        for elem in all_divs:
                            try:
                                text = elem.inner_text().strip()
                                if text in seen or len(text) < 20 or len(text) > 300:
                                    continue
                                seen.add(text)
                                
                                if re.search(r'OPPO|Find\s+\w+|Reno\s+\w+', text, re.I) and "₹" in text:
                                    prices = re.findall(r'[₹]\s*([\d,]+)', text)
                                    if len(prices) >= 1:
                                        price = float(prices[0].replace(",", ""))
                                        mrp = float(prices[1].replace(",", "")) if len(prices) > 1 else price * 1.3
                                        
                                        # Extract title
                                        title = text[:text.find("₹")].strip() if "₹" in text else text
                                        title = re.sub(r'\s+', ' ', title).strip()
                                        # Truncate to reasonable length
                                        title = title[:80]
                                        
                                        link_el = elem.query_selector("a")
                                        href = link_el.get_attribute("href") if link_el else "https://www.oppo.com/in/smartphones/"
                                        if not href.startswith("http"):
                                            href = "https://www.oppo.com/in" + href
                                        
                                        img = ""
                                        img_el = elem.query_selector("img")
                                        if img_el:
                                            img = img_el.get_attribute("src") or ""
                                        
                                        if title and len(title) > 5 and price > 0:
                                            p = Product(
                                                source="oppo",
                                                title=title,
                                                url=href,
                                                image=img,
                                                price=price,
                                                mrp=mrp,
                                                rating=None,
                                                reviews=None,
                                                category=q.category,
                                                brand="OPPO",
                                            )
                                            if p.discount_pct >= q.min_discount:
                                                results.append(p)
                            except Exception:
                                continue
                    else:
                        for container in containers[:12]:
                            try:
                                text = container.inner_text().strip()
                                prices = re.findall(r'[₹]\s*([\d,]+)', text)
                                if len(prices) >= 1:
                                    price = float(prices[0].replace(",", ""))
                                    mrp = float(prices[1].replace(",", "")) if len(prices) > 1 else price * 1.3
                                    
                                    title = text[:text.find("₹")].strip() if "₹" in text else text
                                    title = re.sub(r'\s+', ' ', title).strip()[:80]
                                    
                                    link_el = container.query_selector("a")
                                    href = link_el.get_attribute("href") if link_el else ""
                                    if href and not href.startswith("http"):
                                        href = "https://www.oppo.com/in" + href
                                    
                                    img = ""
                                    img_el = container.query_selector("img")
                                    if img_el:
                                        img = img_el.get_attribute("src") or ""
                                    
                                    if title and len(title) > 5 and price > 0:
                                        p = Product(
                                            source="oppo",
                                            title=title,
                                            url=href,
                                            image=img,
                                            price=price,
                                            mrp=mrp,
                                            rating=None,
                                            reviews=None,
                                            category=q.category,
                                            brand="OPPO",
                                        )
                                        if p.discount_pct >= q.min_discount:
                                            results.append(p)
                            except Exception:
                                continue
                except Exception as e:
                    print(f"[Playwright oppo] error: {e}")
                ctx.close()

            # realme India (D2C brand site)
            if "realme" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    page.goto("https://www.realme.com/in/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    
                    # realme products: links have title, prices in parent/sibling
                    links = page.query_selector_all("a[href*='/realme-']")
                    for link in links[:12]:
                        try:
                            text = link.inner_text().strip()
                            href = link.get_attribute("href") or ""
                            
                            # Clean title (remove NEW prefix)
                            title = re.sub(r'^(NEW)', '', text).strip()
                            if not title or len(title) < 5:
                                continue
                            
                            # Look for prices in parent container
                            parent = link.query_selector("xpath=..")
                            price_text = ""
                            if parent:
                                price_text = parent.inner_text().strip()
                            
                            prices = re.findall(r'[₹]\s*([\d,]+)', price_text)
                            if len(prices) >= 2:
                                price = float(prices[0].replace(",", ""))
                                mrp = float(prices[1].replace(",", ""))
                            elif len(prices) == 1:
                                price = float(prices[0].replace(",", ""))
                                mrp = price * 1.5
                            else:
                                # No prices found, skip
                                continue
                            
                            if not href.startswith("http"):
                                href = "https://www.realme.com/in" + href
                            
                            img = ""
                            img_el = link.query_selector("img")
                            if img_el:
                                img = img_el.get_attribute("src") or ""
                            
                            if title and price > 0:
                                p = Product(
                                    source="realme",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand="realme",
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright realme] error: {e}")
                ctx.close()

            # boAt Lifestyle (D2C Shopify site)
            if "boat" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    # boAt uses Shopify - use collections/all page
                    page.goto("https://www.boat-lifestyle.com/collections/all", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    
                    items = page.query_selector_all(".product-card")
                    for item in items[:12]:
                        try:
                            link_el = item.query_selector("a")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = "https://www.boat-lifestyle.com" + href
                            
                            title_el = item.query_selector(".product-card__title, .product-title, h3")
                            title = title_el.inner_text().strip() if title_el else ""
                            
                            # boAt uses "Sale price" and "Regular price" text labels
                            price = 0.0
                            mrp = 0.0
                            item_text = item.inner_text().strip()
                            prices = re.findall(r'[₹]\s*([\d,]+)', item_text)
                            if len(prices) >= 2:
                                price = float(prices[0].replace(",", ""))
                                mrp = float(prices[1].replace(",", ""))
                            elif len(prices) == 1:
                                price = float(prices[0].replace(",", ""))
                                mrp = price * 1.5
                            
                            img = ""
                            img_el = item.query_selector("img")
                            if img_el:
                                img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""
                            
                            if title and href and price > 0:
                                p = Product(
                                    source="boat",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand="boAt",
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright boat] error: {e}")
                ctx.close()

            # Dot&Key (D2C Shopify site)
            if "dotandkey" in q.sources:
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = ctx.new_page()
                try:
                    # Dot&Key uses Shopify - use collections/all
                    page.goto("https://www.dotandkey.com/collections/all", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    page.wait_for_timeout(3000)
                    
                    items = page.query_selector_all(".product-card")
                    for item in items[:12]:
                        try:
                            link_el = item.query_selector("a")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = "https://www.dotandkey.com" + href
                            
                            title_el = item.query_selector(".product-card__title, .product-title, h3")
                            title = title_el.inner_text().strip() if title_el else ""
                            
                            # Extract prices from full card text
                            price = 0.0
                            mrp = 0.0
                            item_text = item.inner_text().strip()
                            prices = re.findall(r'[₹]\s*([\d,]+)', item_text)
                            if len(prices) >= 2:
                                price = float(prices[0].replace(",", ""))
                                mrp = float(prices[1].replace(",", ""))
                            elif len(prices) == 1:
                                price = float(prices[0].replace(",", ""))
                                mrp = price * 1.5
                            
                            img = ""
                            img_el = item.query_selector("img")
                            if img_el:
                                img = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""
                                if img.startswith("//"):
                                    img = "https:" + img
                            
                            if title and href and price > 0:
                                p = Product(
                                    source="dotandkey",
                                    title=title,
                                    url=href,
                                    image=img,
                                    price=price,
                                    mrp=mrp,
                                    rating=None,
                                    reviews=None,
                                    category=q.category,
                                    brand="Dot&Key",
                                )
                                if p.discount_pct >= q.min_discount:
                                    results.append(p)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[Playwright dotandkey] error: {e}")
                ctx.close()

            browser.close()
        return results


# ─── Registry ───────────────────────────────────────────────────────────
def build_fetchers() -> List[ProductFetcher]:
    source = os.getenv("DATA_SOURCE", "mock").lower()
    fetchers: list[ProductFetcher] = []

    if source == "mock":
        fetchers.append(MockFetcher("amazon", "https://www.amazon.in"))
        fetchers.append(MockFetcher("flipkart", "https://www.flipkart.com"))
        fetchers.append(MockFetcher("myntra", "https://www.myntra.com"))
        fetchers.append(MockFetcher("ajio", "https://www.ajio.com"))
        fetchers.append(MockFetcher("tatacliq", "https://www.tatacliq.com"))
        fetchers.append(MockFetcher("nykaa", "https://www.nykaafashion.com"))
        fetchers.append(MockFetcher("meesho", "https://www.meesho.com"))
        fetchers.append(MockFetcher("snapdeal", "https://www.snapdeal.com"))
        fetchers.append(MockFetcher("shopclues", "https://www.shopclues.com"))
        fetchers.append(MockFetcher("limeroad", "https://www.limeroad.com"))
        fetchers.append(MockFetcher("shopsy", "https://www.shopsy.in"))
        fetchers.append(MockFetcher("oppo", "https://www.oppo.com/in"))
        fetchers.append(MockFetcher("realme", "https://www.realme.com/in"))
        fetchers.append(MockFetcher("boat", "https://www.boat-lifestyle.com"))
        fetchers.append(MockFetcher("dotandkey", "https://www.dotandkey.com"))
        return fetchers

    if source in ("free", "render"):
        # Render mode = NO Playwright (saves ~300MB RAM, works on 512MB free tier)
        # Free mode = includes Playwright per-site scrapers
        if source == "free":
            # Create one Playwright fetcher per site so ThreadPoolExecutor can parallelize
            playwright_sites = [
                "amazon", "flipkart", "myntra", "ajio", "tatacliq",
                "nykaa", "meesho", "snapdeal", "shopclues", "limeroad",
                "oppo", "realme", "boat", "dotandkey",
            ]
            for site in playwright_sites:
                fetchers.append(PlaywrightScraperFetcher(target_sites=[site]))

        # Requests-based scrapers (lightweight HTTP, no browser needed)
        fetchers.append(AmazonScraperFetcher())
        fetchers.append(FlipkartScraperFetcher())
        fetchers.append(MyntraScraperFetcher())

        # Google Custom Search (cross-site discovery, lightweight HTTP)
        g_key = os.getenv("GOOGLE_API_KEY", "")
        g_cx = os.getenv("GOOGLE_CX", "")
        if g_key and g_cx:
            fetchers.append(GoogleCustomSearchFetcher(g_key, g_cx))

        # Amazon PA-API (accurate Amazon pricing)
        amz_key = os.getenv("AMAZON_ACCESS_KEY", "")
        amz_secret = os.getenv("AMAZON_SECRET_KEY", "")
        amz_tag = os.getenv("AMAZON_PARTNER_TAG", "")
        if amz_key and amz_secret and amz_tag:
            fetchers.append(AmazonPAAPIFetcher(amz_key, amz_secret, amz_tag))

        # Cached deals from GitHub Actions scraper (deals.json)
        fetchers.append(DealsJSONFetcher())

        return fetchers

    # RapidAPI mode (legacy paid option)
    api_key = os.getenv("RAPIDAPI_KEY", "")
    if not api_key:
        raise RuntimeError("DATA_SOURCE=rapidapi but RAPIDAPI_KEY is missing in environment.")

    amazon_host = os.getenv("RAPIDAPI_AMAZON_HOST", "real-time-amazon-data.p.rapidapi.com")
    flipkart_host = os.getenv("RAPIDAPI_FLIPKART_HOST", "real-time-flipkart-api.p.rapidapi.com")

    fetchers.append(RapidAPIAmazonFetcher(api_key, amazon_host))
    fetchers.append(RapidAPIFlipkartFetcher(api_key, flipkart_host))
    fetchers.append(MockFetcher("myntra", "https://www.myntra.com"))
    return fetchers


# ─── Deals JSON fetcher (loads pre-scraped deals from GitHub Actions) ─────
class DealsJSONFetcher(ProductFetcher):
    """Load deals from deals.json — scraped by GitHub Actions every 2 hours.
    Zero RAM usage, zero API calls, instant search."""
    source_name = "cached"

    def __init__(self, json_path: str = "deals.json"):
        self.json_path = json_path

    def search(self, q: SearchQuery) -> List[Product]:
        results: list[Product] = []
        try:
            import json
            from pathlib import Path
            path = Path(self.json_path)
            if not path.exists():
                print("[DealsJSON] deals.json not found")
                return results

            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            for item in data.get("products", []):
                try:
                    # Keyword filter
                    title = item.get("title", "").lower()
                    keywords = q.keywords.lower().split()
                    if not any(kw in title for kw in keywords):
                        continue

                    p = Product(
                        source=item.get("source", "cached"),
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        image=item.get("image"),
                        price=item.get("price", 0.0),
                        mrp=item.get("mrp", 0.0),
                        discount_pct=item.get("discount_pct", 0),
                        savings=item.get("savings", 0.0),
                        rating=item.get("rating"),
                        reviews=item.get("reviews"),
                        category=q.category,
                        brand=item.get("brand"),
                    )
                    # Apply min_discount filter
                    if p.discount_pct >= q.min_discount:
                        results.append(p)
                except Exception:
                    continue

            # Sort by discount
            results.sort(key=lambda x: x.discount_pct, reverse=True)
        except Exception as e:
            print(f"[DealsJSON] error: {e}")
        return results

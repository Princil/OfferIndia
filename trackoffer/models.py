from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Product(BaseModel):
    """Normalized product across all sources."""
    source: str  # amazon | flipkart | myntra
    title: str
    url: str
    image: Optional[str] = None
    price: float = Field(..., description="Current selling price in INR")
    mrp: float = Field(..., description="Original / list price in INR")
    rating: Optional[float] = None
    reviews: Optional[int] = None
    category: Optional[str] = None
    brand: Optional[str] = None

    @property
    def discount_pct(self) -> float:
        if self.mrp <= 0:
            return 0.0
        return round((self.mrp - self.price) / self.mrp * 100, 1)

    @property
    def savings(self) -> float:
        return round(max(self.mrp - self.price, 0.0), 2)


class SearchQuery(BaseModel):
    keywords: str = ""
    min_discount: float = 50.0
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    category: Optional[str] = None
    sources: list[str] = ["amazon", "flipkart", "myntra", "ajio", "tatacliq", "nykaa", "meesho", "snapdeal", "shopclues", "limeroad", "oppo", "realme", "boat", "dotandkey"]
    min_rating: Optional[float] = None

from pydantic import BaseModel, HttpUrl # pyright: ignore[reportMissingImports]
from typing import List, Optional, Literal
from datetime import date

class Provenance(BaseModel):
    source_url: HttpUrl
    crawled_at: str
    snippet: Optional[str] = None

class Company(BaseModel):
    company_id: str
    legal_name: str
    brand_name: Optional[str] = None
    website: Optional[HttpUrl] = None
    hq_city: Optional[str] = None
    hq_state: Optional[str] = None
    hq_country: Optional[str] = None
    founded_year: Optional[int] = None
    categories: List[str] = []
    related_companies: List[str] = []
    total_raised_usd: Optional[float] = None
    last_disclosed_valuation_usd: Optional[float] = None
    last_round_name: Optional[str] = None
    last_round_date: Optional[date] = None
    schema_version: str = "2.0.0"
    as_of: Optional[date] = None
    provenance: List[Provenance] = []

class Event(BaseModel):
    event_id: str
    company_id: str
    occurred_on: date
    event_type: Literal[
        "funding","mna","product_release","integration","partnership",
        "customer_win","leadership_change","regulatory","security_incident",
        "pricing_change","layoff","hiring_spike","office_open","office_close",
        "benchmark","open_source_release","contract_award","other"
    ]
    title: str
    description: Optional[str] = None
    round_name: Optional[str] = None
    investors: List[str] = []
    amount_usd: Optional[float] = None  # funding, contract, pricing deltas
    valuation_usd: Optional[float] = None
    actors: List[str] = []  # investors, partners, customers, execs
    tags: List[str] = []  # e.g., "Series B", "SOC2", "HIPAA"
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class Snapshot(BaseModel):
    company_id: str
    as_of: date
    headcount_total: Optional[int] = None
    headcount_growth_pct: Optional[float] = None
    job_openings_count: Optional[int] = None
    engineering_openings: Optional[int] = None
    sales_openings: Optional[int] = None
    hiring_focus: List[str] = []  # e.g., "sales","ml","security"
    pricing_tiers: List[str] = []
    active_products: List[str] = []
    geo_presence: List[str] = []
    confidence: Optional[float] = None
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class Product(BaseModel):
    product_id: str
    company_id: str
    name: str
    description: Optional[str] = None
    pricing_model: Optional[str] = None # "seat", "usage", "tiered"
    pricing_tiers_public: List[str] = []
    ga_date: Optional[date] = None
    integration_partners: List[str] = []
    github_repo: Optional[str] = None
    license_type: Optional[str] = None
    reference_customers: List[str] = []
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class Leadership(BaseModel):
    person_id: str
    company_id: str
    name: str
    role: str  # CEO, CTO, CPO, etc.
    is_founder: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    previous_affiliation: Optional[str] = None
    education: Optional[str] = None
    linkedin: Optional[HttpUrl] = None
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class Visibility(BaseModel):
    company_id: str
    as_of: date
    news_mentions_30d: Optional[int] = None
    avg_sentiment: Optional[float] = None
    github_stars: Optional[int] = None
    glassdoor_rating: Optional[float] = None
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class NewsArticle(BaseModel):
    article_id: str
    company_id: str
    title: str
    url: Optional[HttpUrl] = None
    author: Optional[str] = None
    date_published: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    categories: List[str] = []
    tags: List[str] = []
    word_count: Optional[int] = None
    reading_time: Optional[int] = None
    schema_version: str = "2.0.0"
    provenance: List[Provenance] = []

class Payload(BaseModel):
    company_record: Company
    events: List[Event] = []
    snapshots: List[Snapshot] = []
    products: List[Product] = []
    leadership: List[Leadership] = []
    visibility: List[Visibility] = []
    news_articles: List[NewsArticle] = []
    notes: Optional[str] = ""
    provenance_policy: Optional[str] = "Use only the sources you scraped. If a field is missing, write 'Not disclosed.' Do not infer valuation."
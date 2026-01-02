# LinkedIn Qualifier v1

> Headless FastAPI backend that qualifies LinkedIn followers against client-specific ICPs extracted from Fathom calls.

---

## 🚀 Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/ZainJaffer/ICPv2.git
cd ICPv2

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate  # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
# Copy .env.example to .env and fill in your keys:
# - SUPABASE_URL, SUPABASE_KEY
# - APIFY_API_TOKEN
# - OPENAI_API_KEY

# 5. Run the server
uvicorn app.main:app --reload --port 8001
```

**API Docs:** http://localhost:8001/docs

---

## 📊 Current Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Project Setup | ✅ Complete |
| 1 | Database Schema | ✅ Complete |
| 2 | HTML Ingestion | ✅ Complete & Tested |
| 3 | Enrichment (Apify scraping) | ✅ Complete & Tested (20×5 concurrency) |
| 4a | LangSmith Setup | ✅ Complete (EU endpoint) |
| 4b | pgvector + Embeddings | ✅ Complete |
| 4c | LLM Classifier | ✅ Complete |
| 4d | ICP Matching + Reranker | 🔄 In Progress |
| 4e | Evals Framework | ❌ Not started |
| 5 | CSV Export | 📝 Code written, not tested |
| 6 | Fathom ICP Sync | ❌ Not started |

---

## Business Context

**What we do:** Create LinkedIn content for clients (founders, executives, etc.)

**The workflow:**
1. Client signs up → we do discovery/interview calls (recorded in Fathom)
2. From those calls, we extract WHO the client wants to reach (their ICP)
3. Client exports their LinkedIn followers (HTML file)
4. We score those followers against the client's ICP
5. Output: CSV of high-fit followers the client should engage with

**Key insight:** Each client has their own ICP. This is per-client targeting criteria extracted from their onboarding and interview calls.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Pydantic |
| Database | Supabase + pgvector (state machine + embeddings) |
| AI/LLM | GPT-5-mini (classifier, query parser) |
| Embeddings | OpenAI text-embedding-3-small |
| Reranker | Jina Reranker (cross-encoder) |
| Observability | LangSmith (tracing + evals) |
| Scraping | Apify LinkedIn Profile Scraper |

---

## Project Structure

```
ICPv2/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── routers/
│   │   ├── clients.py          # Client & ICP management
│   │   └── batches.py          # Batch operations (enrich, qualify, export)
│   └── services/
│       ├── db/
│       │   └── supabase_client.py    # Database client
│       ├── scraping/
│       │   ├── apify_scraper.py      # LinkedIn scraping (profiles, posts)
│       │   ├── html_parser.py        # Extract URLs from HTML
│       │   └── profile_id_utils.py   # LinkedIn ID utilities
│       ├── matching/
│       │   ├── icp_matcher.py        # Current: simple LLM scoring
│       │   ├── embeddings.py         # TODO: Generate embeddings
│       │   ├── classifier.py         # TODO: LLM industry classifier
│       │   ├── query_parser.py       # TODO: ICP → SQL + semantic
│       │   └── reranker.py           # TODO: Jina reranker
│       └── enrichment.py             # Orchestrator for scraping + classification
├── inputs/                     # HTML files to process (gitignored)
├── outputs/                    # Generated CSVs
├── scripts/
│   └── process_html.py         # CLI helper for batch processing
├── requirements.txt
└── README.md
```

---

## Data Model

```
Client (e.g., "Carl Seidman")
├── ICP Definition (extracted from Fathom calls)
│   ├── target_titles: ["CFO", "Finance Director"]
│   ├── target_industries: ["SaaS", "Fintech"]
│   ├── company_sizes: ["startup", "mid-market"]
│   └── embedding: [0.012, -0.034, ...]  # Semantic representation
│
└── Batches (HTML uploads of this client's LinkedIn followers)
    └── Leads (individual profiles)
        ├── status: discovered → enriched → qualified → exported
        ├── profile_data: {...}           # Raw scraped data
        ├── embedding: [0.023, ...]       # Profile embedding
        ├── industry: "SaaS"              # LLM classified
        ├── company_type: "startup"       # LLM classified
        ├── industry_reasoning: "..."     # LLM explanation
        ├── icp_score: 0-100              # Final score
        └── match_reasoning: "CFO at SaaS startup, matches target"
```

---

## Lead Status State Machine

```
discovered → enriched → qualified → exported
     ↓           ↓           ↓
   failed      failed      failed
     ↓           ↓           ↓
  (retry)    (retry)     (retry)
```

| Status | Description |
|--------|-------------|
| `discovered` | URL extracted from HTML, not yet scraped |
| `enriched` | Profile data scraped and cached |
| `qualified` | Scored against client's ICP |
| `exported` | Included in output CSV |
| `failed` | Error occurred, retry_count tracked |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `clients` | Client records (name, created_at) |
| `client_icps` | ICP criteria per client (target_titles, industries, company_sizes, embedding) |
| `batches` | HTML upload batches per client |
| `leads` | Individual profiles (status, profile_data, embedding, classification, icp_score) |
| `profile_cache` | Shared cache of scraped profiles (30-day TTL) |
| `fathom_calls` | Tracks processed Fathom calls (Phase 6) |

**New columns for Phase 4:**
- `leads.embedding` - vector(1536) for semantic search
- `leads.industry`, `leads.company_type` - LLM classification
- `leads.industry_reasoning`, `leads.company_reasoning` - LLM explanations
- `client_icps.embedding` - vector(1536) for ICP representation

---

## Build Phases

### Phase 0: Project Setup ✅
- [x] FastAPI project skeleton
- [x] Supabase connection
- [x] Error handling middleware
- [x] Logging configuration
- [x] Environment variables (.env)

### Phase 1: Database Schema ✅
- [x] Create Supabase tables
- [x] Create indexes
- [x] Test connections

### Phase 2: HTML Ingestion ✅
- [x] URL extraction from HTML (handles URN-style LinkedIn IDs)
- [x] Batch creation
- [x] Lead creation with deduplication
- [x] Endpoint: `POST /clients/{id}/ingest`

### Phase 3: Enrichment Service ✅
- [x] Apify scraper integration
- [x] Cache check logic (30-day TTL)
- [x] URN matching fix (preserve case, match by profileId)
- [x] Status updates
- [x] Endpoint: `POST /batches/{id}/enrich?limit=N`
- [x] **Tested with 5 profiles**
- [x] **Concurrent batching (20 actors × 5 URLs) - TESTED ✅**

### Phase 4a: LangSmith Setup ✅
- [x] Add langchain, langchain-openai, langsmith to requirements
- [x] Configure LANGCHAIN_API_KEY, LANGCHAIN_TRACING_V2
- [x] Configure EU endpoint (LANGCHAIN_ENDPOINT)
- [x] Verify traces appear in LangSmith dashboard

### Phase 4b: pgvector + Embeddings ✅
- [x] Enable pgvector in Supabase
- [x] Add `embedding` column to leads table
- [x] Create embeddings.py service
- [x] Generate embeddings at enrichment time

### Phase 4c: LLM Classifier ✅
- [x] Add classification columns to leads table
- [x] Create classifier.py service
- [x] Integrate classification into enrichment
- [x] Store `industry`, `company_type`, `industry_reasoning`, `company_reasoning`

### Phase 4d: ICP Matching + Reranker 🔄
- [ ] Expand ICP criteria via LLM for richer embeddings
- [ ] Vector similarity search (pgvector)
- [ ] Add Jina reranker integration
- [ ] Update `POST /batches/{id}/qualify` endpoint

**Note:** SQL filtering skipped - batch sizes (10-1000) are small enough for embeddings-only approach.

### Phase 4e: Evals Framework ❌
- [ ] Create test dataset (20-50 known profile matches)
- [ ] Build eval runner in LangSmith
- [ ] Measure: embedding recall, reranker precision, end-to-end accuracy

### Phase 5: Export Service 📝
- [x] CSV generation
- [x] Download endpoint: `GET /batches/{id}/export`
- [ ] **Testing pending**

### Phase 6: Fathom ICP Sync ❌
- [ ] Fathom API client
- [ ] ICP extraction prompt
- [ ] Accumulation logic (expand, don't replace)
- [ ] Endpoint: `POST /clients/{id}/sync-icp`

---

## ICP Matching Architecture

The qualification pipeline uses embeddings + reranker for semantic matching:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. EXPAND ICP (LLM)                                            │
│     "CFO at SaaS startups"                                      │
│     → "CFO, Chief Financial Officer, VP Finance, finance        │
│        executive at SaaS, Software, B2B technology startups"    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. VECTOR SEARCH (pgvector)                                    │
│     Generate ICP embedding, find top 50 similar leads           │
│     cosine_similarity(lead.embedding, icp.embedding)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. RERANKER (Jina)                                             │
│     Cross-encoder rescores top 50 with full profile context     │
│     → Returns final ranked list with scores                     │
└─────────────────────────────────────────────────────────────────┘
```

**Why this approach:**
- Batch sizes (10-1000) are small enough for embeddings-only
- LLM expands ICP for richer semantic matching (CFO ≈ VP Finance)
- Reranker provides highest accuracy for final ranking
- Classification (industry/company_type) stored for display, not filtering
- LangSmith traces every step for debugging and evals

---

## Implementation Rules

1. **Async everywhere** - Use `httpx.AsyncClient` for all external API calls
2. **Stateless processing** - Supabase is the source of truth; server can restart and resume
3. **Cache aggressively** - Don't scrape the same profile twice within 30 days
4. **Fail gracefully** - Track retry_count, mark as failed after 3 attempts

---

## Environment Variables

```env
# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_service_role_key

# Scraping
APIFY_API_TOKEN=your_apify_token

# LLM + Embeddings
OPENAI_API_KEY=your_openai_key

# Observability
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true

# Reranker (Phase 4d)
JINA_API_KEY=your_jina_api_key
```

---

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/clients` | Create new client |
| POST | `/clients/{id}/sync-icp` | Extract ICP from Fathom calls |
| POST | `/clients/{id}/ingest` | Upload HTML, extract URLs |
| POST | `/batches/{id}/enrich` | Scrape profiles for batch |
| POST | `/batches/{id}/qualify` | Score profiles against ICP |
| GET | `/batches/{id}/export` | Download qualified leads CSV |

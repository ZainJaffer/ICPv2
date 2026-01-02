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
| 4 | ICP Qualification (LLM scoring) | 📝 Code written, not tested |
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
| Database | Supabase (state machine + profile cache) |
| AI/LLM | GPT-5-mini with structured JSON outputs |
| File I/O | HTML file ingestion (local), API upload endpoint |
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
│       ├── supabase_client.py  # Database client
│       ├── html_parser.py      # Extract URLs from HTML
│       ├── apify_scraper.py    # LinkedIn scraping (profiles, posts, reactions)
│       ├── enrichment.py       # Batch enrichment logic
│       ├── icp_matcher.py      # LLM-based ICP scoring
│       └── profile_id_utils.py # LinkedIn ID utilities
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
│   └── company_sizes: ["startup", "mid-market"]
│
└── Batches (HTML uploads of this client's LinkedIn followers)
    └── Leads (individual profiles, scored against this client's ICP)
        ├── status: discovered → enriched → qualified → exported
        ├── icp_score: 0-100
        └── match_reasoning: "CFO at SaaS startup, matches target profile"
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
| `client_icps` | ICP criteria per client (target_titles, industries, company_sizes) |
| `batches` | HTML upload batches per client |
| `leads` | Individual profiles to qualify (status, profile_data, icp_score) |
| `profile_cache` | Shared cache of scraped profiles (30-day TTL) |
| `fathom_calls` | Tracks processed Fathom calls (Phase 6) |

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

### Phase 4: Qualification Service 📝
- [x] ICP matching prompt with GPT-5-mini
- [x] Score + reasoning generation
- [x] Status updates
- [x] Endpoint: `POST /batches/{id}/qualify`
- [ ] **Testing pending**

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

## Implementation Rules

1. **Async everywhere** - Use `httpx.AsyncClient` for all external API calls
2. **Stateless processing** - Supabase is the source of truth; server can restart and resume
3. **Cache aggressively** - Don't scrape the same profile twice within 30 days
4. **Fail gracefully** - Track retry_count, mark as failed after 3 attempts

---

## Environment Variables

```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_service_role_key
APIFY_API_TOKEN=your_apify_token
OPENAI_API_KEY=your_openai_key
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

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
| 4b | pgvector + Embeddings | ✅ Complete & Tested |
| 4c | LLM Classifier | ✅ Complete & Tested |
| 4d | ICP Matching + Reranker | ✅ Complete & Tested (5 + 50 leads) |
| 5 | CSV Export | ✅ Complete & Tested |
| 5a | API Usability (ICP upsert + background + run) | ✅ Implemented |
| 4e | Evals Framework | 📅 Future sprint |
| 6 | Fathom ICP Sync | ❌ Not started |
| 7 | KTO Fine-tuning | 📊 Conditional - awaiting feedback data |

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
│       │   ├── apify_scraper.py      # LinkedIn scraping (20×5 concurrency)
│       │   ├── html_parser.py        # Extract URLs from HTML
│       │   └── profile_id_utils.py   # LinkedIn ID utilities
│       ├── matching/
│       │   ├── embeddings.py         # ✅ Profile & ICP embeddings
│       │   ├── classifier.py         # ✅ LLM industry/company classifier
│       │   ├── reranker.py           # ✅ Jina reranker (modular design)
│       │   └── icp_matcher.py        # 🔄 Qualification logic (updating)
│       └── enrichment.py             # Orchestrates scraping + embedding + classification
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
        │
        ├── # Extracted fields (from Apify scrape)
        ├── name: "John Smith"
        ├── headline: "CFO | Finance Leader | Board Member"
        ├── company: "TechStartup Inc"
        ├── location: "San Francisco, CA"
        ├── current_job_titles: ["CFO", "Board Member"]  # ALL current positions
        │
        ├── # Raw data
        ├── profile_data: {...}           # Full Apify response (positions, skills, etc.)
        │
        ├── # Generated at enrichment time
        ├── embedding: [0.023, ...]       # Profile embedding (see below)
        ├── industry: "SaaS"              # LLM classified
        ├── company_type: "startup"       # LLM classified
        ├── industry_reasoning: "..."     # LLM explanation
        ├── company_reasoning: "..."      # LLM explanation
        │
        └── # Added at qualification time
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

### Leads Table Schema

```sql
-- Core fields
id                  uuid PRIMARY KEY
client_id           uuid REFERENCES clients(id)
batch_id            uuid REFERENCES batches(id)
linkedin_url        text UNIQUE
public_identifier   text
status              text  -- discovered, enriched, qualified, exported, failed

-- Extracted from Apify scrape
name                text
headline            text
company             text
location            text
current_job_titles  jsonb -- ALL current titles (where endDate is null)
profile_data        jsonb -- Full Apify response

-- Generated at enrichment time
embedding           vector(1536)  -- Profile embedding for semantic search
industry            text          -- LLM classified
company_type        text          -- LLM classified
industry_reasoning  text          -- LLM explanation
company_reasoning   text          -- LLM explanation

-- Added at qualification time
icp_score           integer       -- 0-100
match_reasoning     text          -- Why this profile matches/doesn't match

-- Metadata
scraped_at          timestamp
error_message       text
retry_count         integer DEFAULT 0
```

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
- [x] Extract `current_job_title` from first current position
- [x] Include ALL current positions in embedding (endDate is null)
- [x] Include position descriptions (full text, no truncation)
- [x] Include 1-2 past positions for career context

### Phase 4c: LLM Classifier ✅
- [x] Add classification columns to leads table
- [x] Create classifier.py service
- [x] Integrate classification into enrichment
- [x] Store `industry`, `company_type`, `industry_reasoning`, `company_reasoning`

### Phase 4d: ICP Matching + Reranker ✅
- [x] Jina reranker integration (`reranker.py` with modular design)
- [x] Expand ICP criteria via LLM for richer semantic matching
- [x] Vector similarity search function (pgvector)
- [x] Update `icp_matcher.py` to use embeddings + reranker
- [x] Update `POST /batches/{id}/qualify` endpoint
- [x] Job titles placed first in profile text for better matching
- [x] Concise ICP expansion (reranker works better with shorter queries)

**Note:** SQL filtering skipped - batch sizes (10-1000) are small enough for embeddings-only approach.
Reranker is modular - can swap Jina for Cohere, ZeroEntropy, etc. for A/B testing via LangSmith.

**Testing Results:**

**Small batch (5 leads - Ben Turtel, tech founders ICP):**
| Lead | Score | Why |
|------|-------|-----|
| Kelly Peng (Founder/CEO, AI) | 69 | Perfect match: CEO+Founder+CTO + AI industry |
| Monica (CEO, Healthcare) | 16 | Title matches, wrong industry |
| John (Global Head, Consulting) | 16 | Title not exact match |
| Chris (Director, Consulting) | 15 | Title matches, wrong industry |
| Mateusz (CEO, HRTech) | 9 | Title matches, wrong industry |

**Large batch (50 leads - Allison Gates, marketing ICP):**
- ✅ All 50 leads enriched via concurrent scraping (20 actors × 5 URLs)
- ✅ All 50 leads qualified with scores 25-85
- ✅ Top match: Gregory Fuentes (85) - GTM/Revenue Intelligence at SaaS
- ✅ CMO matches scoring 60-72 (e.g., Melissa Waters)
- ✅ CSV export working: `allison_gates_qualified.csv`

### Phase 5: Export Service ✅
- [x] CSV generation
- [x] Download endpoint: `GET /batches/{id}/export`
- [x] **Tested** - Exported 50 qualified leads successfully

### Phase 5a: API Usability ✅
Goal: make v1 fully operable via API (no scripts/DB edits) and avoid “PowerShell hangs” on long requests.

- [x] **Upsert ICP via API**:
  - `POST /clients/{id}/icp` (preferred)
  - `PUT /clients/{id}/icp` (alias)
- [x] **Background mode** for long-running operations (returns immediately; poll `GET /batches/{id}`):
  - `POST /batches/{id}/enrich?background=true`
  - `POST /batches/{id}/qualify?background=true`
- [x] **One-shot batch run** (enrich → qualify):
  - `POST /batches/{id}/run?background=true`

### Phase 6: Fathom ICP Sync ❌
- [ ] Fathom API client
- [ ] ICP extraction prompt
- [ ] Accumulation logic (expand, don't replace)
- [ ] Endpoint: `POST /clients/{id}/sync-icp`

---

## Future Phases / Later Sprints

### Phase 4e: Evals Framework
- [ ] Create test dataset (20-50 known profile matches)
- [ ] Build eval runner in LangSmith
- [ ] Measure: embedding recall, reranker precision, end-to-end accuracy
- [ ] Consistency checks (score variance across runs)
- [ ] Ranking quality analysis (top vs bottom differences)
- [ ] Component comparison (embeddings vs reranker)

### Phase 7: KTO Fine-tuning (Conditional)

**Goal:** Fine-tune the Jina reranker using human feedback to improve ICP matching accuracy.

**Approach:** KTO (Kahneman-Tversky Optimization) uses binary feedback (good/bad) to train preference models. The mock_ui's trash icon (🗑) provides explicit negative signal when reviewers reject profiles.

**Data Collection:**
- **Explicit positives:** Leads exported to CSV (strongest signal)
- **Explicit negatives:** Leads marked with trash icon (rare but valuable - these are model mistakes)

**Key Design Decision:** ICP-conditioned training
- Include ICP criteria as context in training queries
- Allows cross-client learning without contradictory signals
- Model learns "what's good for THIS type of ICP" not "what's good globally"

**Prerequisites:**
- [ ] Add `lead_feedback` table to store trash icon clicks
- [ ] Update mock_ui to persist feedback to backend (`POST /feedback`)
- [ ] Track exported leads as implicit positives
- [ ] Accumulate sufficient feedback (~100 positives, ~20+ negatives)

**Implementation (when ready):**
- [ ] Export training data in Jina-compatible format
- [ ] Integrate Jina fine-tuning API
- [ ] A/B test fine-tuned vs base model via LangSmith

**Status:** 📊 Waiting for feedback data. Given that profiles reaching the UI have already passed embedding similarity + reranker filtering, we expect few negatives. Will reassess feasibility after observing actual trash icon usage patterns across multiple batches.

---

## ICP Matching Architecture

The qualification pipeline uses embeddings + reranker for semantic matching:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. BUILD ICP TEXT (No LLM - preserves client intent)           │
│     "Target titles: CFO | Industries: SaaS | Size: startup"     │
│     Embeddings naturally understand CFO ≈ Chief Financial Officer│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. VECTOR SEARCH (pgvector)                                    │
│     Generate ICP embedding, score ALL leads in batch            │
│     cosine_similarity(lead.embedding, icp.embedding)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. RERANKER (Jina)                                             │
│     Cross-encoder rescores ALL leads with full profile context  │
│     Used to filter bottom matches, not for UI sorting           │
└─────────────────────────────────────────────────────────────────┘
```

**Why this approach:**
- **No LLM expansion** - Embeddings naturally handle synonyms (CFO ≈ Chief Financial Officer). LLM expansion risks adding terms the client didn't ask for (e.g., expanding "CFO" to "VP Finance").
- Batch sizes (10-1000) are small enough for embeddings-only scoring
- Reranker filters obvious mismatches; UI shows remaining leads in random order (to avoid biasing human feedback for future KTO training)
- Classification (industry/company_type) stored for display, not filtering
- LangSmith traces every step for debugging and evals

---

## How Profile Embeddings Work

Embeddings are vector representations that capture the semantic meaning of a profile. Two similar profiles (e.g., "CFO at fintech startup" and "VP Finance at SaaS company") will have similar embeddings, even though the words are different.

### What Gets Embedded

When a lead is enriched, we construct a text representation from their LinkedIn data:

```
┌─────────────────────────────────────────────────────────────────┐
│  PROFILE TEXT (fed to OpenAI text-embedding-3-small)            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. NAME          "John Smith"                                  │
│                                                                 │
│  2. HEADLINE      "CFO | Finance Leader | Board Member"         │
│                                                                 │
│  3. COMPANY       "Works at TechStartup Inc"                    │
│                                                                 │
│  4. LOCATION      "Located in San Francisco, CA"                │
│                                                                 │
│  5. SUMMARY       "About: 20+ years scaling finance..."         │
│     (full text, no truncation)                                  │
│                                                                 │
│  6. CURRENT ROLES (all positions where endDate is null)         │
│     "Current roles: Chief Financial Officer at TechStartup.     │
│      Responsible for Series B fundraise... |                    │
│      Board Member at Industry Association. Advising on..."      │
│                                                                 │
│  7. PAST ROLES    (1-2 for career context)                      │
│     "Previous: VP Finance at OldCo. Built finance team... |     │
│      Director at BigCorp"                                       │
│                                                                 │
│  8. SKILLS        "Skills: Financial Modeling, Fundraising..."  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    OpenAI Embedding API
                              ↓
                    [0.012, -0.034, 0.056, ...]
                    (1536-dimensional vector)
```

### Why Current Positions Matter Most

LinkedIn profiles often have multiple positions listed. We prioritize **current positions** (where `endDate` is null) because:

1. **ICP matching is about NOW** - "Find me CFOs" means current CFOs, not former
2. **Multiple current roles are common** - Someone might be:
   - CFO at TechStartup (primary)
   - Board Member at OtherCo
   - Advisor at VCFirm
   
   All of these should be captured because any could match the ICP.

3. **Position descriptions are valuable** - They contain context like:
   - "Led $50M Series B fundraise"
   - "Scaling team from 5 to 50"
   - "Building B2B SaaS platform for finance teams"

### Field Extraction Summary

| Field | Source | Purpose |
|-------|--------|---------|
| `name` | firstName + lastName | Display |
| `headline` | profile.headline | Embedding + display |
| `company` | First current position's company | Display |
| `current_job_titles` | ALL current positions' titles (array) | **Key for ICP matching** |
| `location` | geoLocationName | Embedding |
| `profile_data` | Full Apify response | Embedding (positions, skills, summary) |

### How ICP Embeddings Work

ICP criteria is embedded directly (no LLM expansion) for semantic comparison:

```
ICP: {
  target_titles: ["CFO", "VP Finance"],
  target_industries: ["SaaS", "Fintech"],
  company_sizes: ["startup", "mid-market"]
}
        ↓
"Target titles: CFO, VP Finance | Industries: SaaS, Fintech | Company sizes: startup, mid-market"
        ↓
OpenAI Embedding → [0.034, -0.012, ...]
```

The magic: "CFO" and "Chief Financial Officer" have similar embeddings because they mean the same thing. This enables semantic matching without exact keyword matching - and without needing LLM expansion that might add unwanted terms.

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
| POST | `/clients/{id}/icp` | Upsert ICP criteria for client |
| PUT | `/clients/{id}/icp` | Upsert ICP criteria for client (alias) |
| POST | `/clients/{id}/sync-icp` | Extract ICP from Fathom calls |
| POST | `/clients/{id}/ingest` | Upload HTML, extract URLs |
| POST | `/batches/{id}/enrich` | Scrape profiles for batch |
| POST | `/batches/{id}/qualify` | Score profiles against ICP |
| POST | `/batches/{id}/run` | Run enrich → qualify (supports background) |
| GET | `/batches/{id}/export` | Download qualified leads CSV |

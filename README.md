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

## Current Status

**Production Ready** — Core pipeline complete and tested with 50+ leads.

| Component | Status |
|-----------|--------|
| HTML Ingestion | Complete |
| Profile Enrichment (Apify) | Complete |
| Embeddings + Classification | Complete |
| ICP Matching + Reranker | Complete |
| CSV Export | Complete |
| Background Processing | Complete |
| Fathom ICP Sync | Planned |
| Evals Framework | Planned |
| KTO Fine-tuning | Conditional |

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
│       │   ├── embeddings.py         # Profile & ICP embeddings
│       │   ├── classifier.py         # LLM industry/company classifier
│       │   ├── reranker.py           # Jina reranker (modular design)
│       │   └── icp_matcher.py        # Qualification logic
│       └── enrichment.py             # Orchestrates scraping + embedding + classification
├── inputs/                     # HTML files to process (gitignored)
├── outputs/                    # Generated CSVs
├── mock_ui/                    # Review interface for human feedback
├── scripts/                    # CLI helpers and utilities
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

## Completed Features

### Core Pipeline

**HTML Ingestion** — Upload LinkedIn follower HTML exports. The parser extracts URLs (including URN-style IDs), creates batch records, and deduplicates across uploads.

**Profile Enrichment** — Apify scraper fetches full LinkedIn profile data with 20×5 concurrent batching. Profiles are cached for 30 days to avoid re-scraping. Extracts name, headline, company, location, and all current job titles.

**Embeddings & Classification** — Each profile is embedded using OpenAI `text-embedding-3-small` (1536 dimensions). An LLM classifier (GPT-5-mini) categorizes industry and company type with reasoning.

**ICP Matching** — Profiles are scored against client ICP criteria using:
1. ICP text embedding
2. pgvector cosine similarity search
3. Jina reranker for filtering bottom matches

**CSV Export** — Download qualified leads sorted by ICP score with match reasoning.

### API Features

**Background Processing** — Long-running operations support `?background=true` to return immediately. Poll `GET /batches/{id}` for status.

**ICP Management** — Upsert ICP criteria via `POST /clients/{id}/icp` without database access.

**One-Shot Runs** — `POST /batches/{id}/run` executes enrich → qualify in sequence.

### Observability

**LangSmith Integration** — All LLM calls traced for debugging and future evals. Configured for EU endpoint.

---

## Roadmap

### Phase 6: Fathom ICP Sync
Automatically extract ICP criteria from Fathom call transcripts. Accumulate insights across multiple calls rather than replacing.

### Phase 4e: Evals Framework
Build evaluation suite in LangSmith to measure embedding recall, reranker precision, and end-to-end accuracy. Compare component contributions.

### Phase 7: KTO Fine-tuning (Conditional)

Fine-tune a model using human feedback to improve ICP matching accuracy.

**Approach:** KTO (Kahneman-Tversky Optimization) uses binary feedback (good/bad) from the review UI. The trash icon provides explicit negative signal; CSV exports provide positive signal.

**Key Design Decisions:**
- ICP-conditioned training allows cross-client learning without contradictory signals
- Jina reranker filters bottom matches; UI shows remaining leads in random order to avoid biasing feedback
- Multiple model options: classifier head (~100 examples), cross-encoder (~200-500 examples), or fine-tuned embeddings

**Status:** Waiting for feedback data. Given upstream filtering, we expect few negatives. Will reassess after observing actual usage patterns.

---

## ICP Matching Architecture

The qualification pipeline uses embeddings + reranker for semantic matching:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. BUILD ICP TEXT                                              │
│     "Target titles: CFO | Industries: SaaS | Size: startup"     │
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
- Embeddings naturally handle synonyms (CFO ≈ Chief Financial Officer)
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

ICP criteria is embedded for semantic comparison:

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

Embeddings capture semantic meaning, so "CFO" and "Chief Financial Officer" have similar vectors even though the words differ. This enables matching without exact keywords.

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

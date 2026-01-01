# LinkedIn Qualifier v1

> Headless FastAPI backend that qualifies LinkedIn followers against client-specific ICPs extracted from Fathom calls.

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
| Backend | FastAPI |
| Database | Supabase (state machine + profile cache) |
| AI/LLM | Claude 3.5 / GPT-4o with Instructor + Pydantic |
| File I/O | API upload endpoint (v1), Google Drive (future) |
| Scraping | Existing internal scraper |

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

## Core Services

### A. Fathom ICP Sync

**Purpose:** Extract client ICP from their Fathom call transcripts

**Logic:**
- Connects to Fathom API
- Fetches transcripts for a specific client
- Uses LLM with Instructor to extract structured ICP
- **Expands** criteria over time (accumulates, doesn't replace)

```python
class ClientICP(BaseModel):
    client_id: uuid
    target_titles: list[str]
    target_industries: list[str]
    company_sizes: list[str]
```

### B. HTML Ingestion

**Purpose:** Extract LinkedIn URLs from exported HTML files

**Endpoint:**
```python
@app.post("/clients/{client_id}/ingest")
async def ingest_html(client_id: uuid, file: UploadFile):
    urls = extract_linkedin_urls(await file.read())
    # Create leads in Supabase with status 'discovered'
    return {"leads_created": len(urls)}
```

### C. Enrichment Service

**Purpose:** Scrape full profile data for discovered leads

**Logic:**
1. Query Supabase for leads in `discovered` status
2. Check cache - if profile scraped within 30 days, skip API call
3. Call internal scraper for fresh profiles
4. Store result in Supabase
5. Update status to `enriched`

### D. Qualification Service (The Matcher)

**Purpose:** Score enriched profiles against client's ICP

**Logic:**
1. Load client's ICP definition
2. For each `enriched` lead, compare profile to ICP
3. Generate score (0-100) and reasoning via LLM
4. Update status to `qualified`

```python
class ICPMatch(BaseModel):
    score: int = Field(ge=0, le=100)
    reasoning: str
```

### E. Export Service

**Purpose:** Generate CSV of qualified leads

**Output Format:**
| Name | Profile URL | Title | Company | ICP Score | Match Reasoning |
|------|-------------|-------|---------|-----------|-----------------|

---

## Supabase Schema

```sql
-- Clients
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ICP Definitions (per client, accumulates over time)
CREATE TABLE client_icps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    target_titles TEXT[] DEFAULT '{}',
    target_industries TEXT[] DEFAULT '{}',
    company_sizes TEXT[] DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fathom call log (tracks which calls have been processed)
CREATE TABLE fathom_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    fathom_call_id TEXT UNIQUE NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Batches (each HTML upload)
CREATE TABLE batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    filename TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'processing'
);

-- Leads
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    batch_id UUID REFERENCES batches(id),
    linkedin_url TEXT NOT NULL,
    public_identifier TEXT,
    status TEXT DEFAULT 'discovered',
    retry_count INT DEFAULT 0,
    
    -- Enriched data (cached)
    profile_data JSONB,
    scraped_at TIMESTAMPTZ,
    
    -- Qualification results
    icp_score INT,
    match_reasoning TEXT,
    qualified_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(client_id, linkedin_url)
);

-- Profile cache (shared across clients)
CREATE TABLE profile_cache (
    linkedin_url TEXT PRIMARY KEY,
    public_identifier TEXT,
    profile_data JSONB NOT NULL,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_leads_status ON leads(client_id, status);
CREATE INDEX idx_leads_batch ON leads(batch_id);
CREATE INDEX idx_profile_cache_scraped ON profile_cache(scraped_at);
```

---

## Build Phases

### Phase 0: Project Setup
- [ ] FastAPI project skeleton
- [ ] Supabase connection
- [ ] Error handling middleware
- [ ] Logging configuration
- [ ] Environment variables (.env)

### Phase 1: Database Schema
- [ ] Create Supabase tables
- [ ] Create indexes
- [ ] Test connections

### Phase 2: HTML Ingestion
- [ ] URL extraction from HTML
- [ ] Batch creation
- [ ] Lead creation with deduplication
- [ ] Endpoint: `POST /clients/{id}/ingest`

### Phase 3: Enrichment Service
- [ ] Internal scraper integration
- [ ] Cache check logic (30-day TTL)
- [ ] Status updates
- [ ] Endpoint: `POST /batches/{id}/enrich`

### Phase 4: Qualification Service
- [ ] ICP matching prompt with Instructor
- [ ] Score + reasoning generation (use hardcoded test ICP first)
- [ ] Status updates
- [ ] Endpoint: `POST /batches/{id}/qualify`

### Phase 5: Export Service
- [ ] CSV generation
- [ ] Download endpoint: `GET /batches/{id}/export`

### Phase 6: Fathom ICP Sync (wire up last)
- [ ] Fathom API client
- [ ] ICP extraction prompt with Instructor
- [ ] Accumulation logic (expand, don't replace)
- [ ] Endpoint: `POST /clients/{id}/sync-icp`

---

## Implementation Rules

1. **Async everywhere** - Use `httpx.AsyncClient` for all external API calls
2. **Stateless processing** - Supabase is the source of truth; server can restart and resume
3. **Batching** - Process profiles in small batches to respect rate limits
4. **Structured outputs** - Always use Instructor + Pydantic for LLM calls
5. **Cache aggressively** - Don't scrape the same profile twice within 30 days
6. **Fail gracefully** - Track retry_count, mark as failed after 3 attempts

---

## Environment Variables

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_service_role_key

# Fathom
FATHOM_API_KEY=your_fathom_key

# LLM
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Internal Scraper
SCRAPER_BASE_URL=https://your-scraper.com
SCRAPER_API_KEY=your_scraper_key
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

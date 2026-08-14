CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,           -- remotive, remoteok, wwr, hackernews
    external_id TEXT,               -- ID original de la fuente
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    description TEXT,              -- JD completo
    url TEXT NOT NULL,
    location TEXT,
    remote BOOLEAN DEFAULT 1,
    tags TEXT,                      -- JSON array de tags/keywords
    salary TEXT,
    posted_date TEXT,              -- ISO date

    -- Campos de análisis LLM
    match_score INTEGER DEFAULT 0, -- 0-100
    match_reason TEXT,              -- por qué matchea (resume LLM)
    dealbreaker_hit TEXT,          -- si fue rechazado, cuál dealbreaker

    -- Tracking
    status TEXT DEFAULT 'new',      -- new, viewed, applied, interviewing, rejected, offer
    applied_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT,
    total_fetched INTEGER,
    total_saved INTEGER,
    total_rejected INTEGER,
    errors TEXT
);

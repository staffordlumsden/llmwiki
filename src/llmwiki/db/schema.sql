-- SQLite schema for llmwiki

-- Sources table
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT,
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'pending'
);

-- Source versions table
CREATE TABLE IF NOT EXISTS source_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    page_count INTEGER,
    text_cache_path TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    description TEXT,
    summary_template TEXT,
    retrieval_boost REAL DEFAULT 1.0,
    is_builtin INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Source categories mapping table
CREATE TABLE IF NOT EXISTS source_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    is_primary INTEGER DEFAULT 0,
    confidence REAL,
    rationale TEXT,
    assignment_method TEXT,
    is_manual_override INTEGER DEFAULT 0,
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Pages table
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    page_type TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_version_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (current_version_id) REFERENCES page_versions(id)
);

-- Page versions table
CREATE TABLE IF NOT EXISTS page_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    content_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    generated_by_model_alias TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    run_id INTEGER,
    FOREIGN KEY (page_id) REFERENCES pages(id)
);

-- Chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_version_id INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT,
    char_count INTEGER,
    token_estimate INTEGER,
    FOREIGN KEY (source_version_id) REFERENCES source_versions(id)
);

-- FTS5 virtual table for chunks
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id'
);

-- Embeddings table
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL,
    model_alias TEXT NOT NULL,
    dims INTEGER NOT NULL,
    dtype TEXT NOT NULL,
    vector_blob BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id)
);

-- Runs table
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    profile TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
);

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    target_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Citations table
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_version_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    source_version_id INTEGER,
    chunk_id INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    quote_excerpt TEXT,
    FOREIGN KEY (page_version_id) REFERENCES page_versions(id),
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (source_version_id) REFERENCES source_versions(id),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id)
);

-- Model events table
CREATE TABLE IF NOT EXISTS model_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    event_type TEXT NOT NULL,
    model_alias TEXT,
    model_name TEXT,
    endpoint TEXT,
    success INTEGER NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- Links table (for backlink tracking)
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_page_id INTEGER NOT NULL,
    target_page_id INTEGER NOT NULL,
    link_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_page_id) REFERENCES pages(id),
    FOREIGN KEY (target_page_id) REFERENCES pages(id)
);

-- Query history table
CREATE TABLE IF NOT EXISTS query_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    model_alias TEXT,
    top_k INTEGER,
    lexical_count INTEGER,
    semantic_count INTEGER,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_sources_path ON sources(path);
CREATE INDEX IF NOT EXISTS idx_sources_sha256 ON sources(sha256);
CREATE INDEX IF NOT EXISTS idx_source_versions_source_id ON source_versions(source_id);
CREATE INDEX IF NOT EXISTS idx_source_categories_source_id ON source_categories(source_id);
CREATE INDEX IF NOT EXISTS idx_source_categories_category_id ON source_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);
CREATE INDEX IF NOT EXISTS idx_pages_page_type ON pages(page_type);
CREATE INDEX IF NOT EXISTS idx_page_versions_page_id ON page_versions(page_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source_version_id ON chunks(source_version_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id ON embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_citations_page_version_id ON citations(page_version_id);
CREATE INDEX IF NOT EXISTS idx_links_source_page_id ON links(source_page_id);
CREATE INDEX IF NOT EXISTS idx_links_target_page_id ON links(target_page_id);

-- Trigger to update FTS when chunks are inserted/updated
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text);
END;

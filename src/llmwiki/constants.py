"""Application constants."""

# Default directories
DEFAULT_sources_dir = "./sources"
DEFAULT_wiki_dir = "./wiki"
DEFAULT_state_dir = ".llmwiki"
DEFAULT_cache_dir = ".llmwiki/cache"
DEFAULT_db_path = ".llmwiki/state.db"

# Default category definitions file
DEFAULT_categories_file = "./categories/defaults.yaml"

# Default config file
DEFAULT_config_file = "llmwiki.yaml"

# Default hardware profile
DEFAULT_profile = "desktop"

# Supported profiles
SUPPORTED_PROFILES = ["tiny", "edge", "desktop", "custom"]

# Default page types
PAGE_TYPES = [
    "category",
    "source",
    "concept",
    "entity",
    "comparison",
    "open_question",
    "index",
]

# Default citation format
CITATION_FORMAT = "[CIT:source={source};pages={pages};chunk={chunk}]"

# Default chunking parameters
DEFAULT_CHUNK_TARGET_CHARS = 1800
DEFAULT_CHUNK_MAX_CHARS = 2400
DEFAULT_CHUNK_MIN_CHARS = 500
DEFAULT_CHUNK_OVERLAP_CHARS = 150

# Default retrieval parameters
DEFAULT_TOP_K_LEXICAL = 12
DEFAULT_TOP_K_SEMANTIC = 12
DEFAULT_TOP_K_FINAL = 10
DEFAULT_LEXICAL_WEIGHT = 0.55
DEFAULT_SEMANTIC_WEIGHT = 0.45

# Default model timeouts
DEFAULT_GENERATION_TIMEOUT = 120
DEFAULT_EMBEDDING_TIMEOUT = 120

# SQLite FTS table name
FTS_TABLE_NAME = "chunk_fts"

# Machine-managed markdown markers
BEGIN_LLMWIKI_SUMMARY = "<!-- BEGIN LLMWIKI:SUMMARY -->"
END_LLMWIKI_SUMMARY = "<!-- END LLMWIKI:SUMMARY -->"

"""Configuration management with Pydantic settings."""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GenerationModelConfig(BaseModel):
    """Generation model configuration."""
    alias: str = "writer"
    provider: Literal["ollama"] = "ollama"
    endpoint: str = "http://localhost:11434"
    name: str = "qwen3.5:35b"
    temperature: float = 0.1
    num_ctx: int = 16384
    timeout_seconds: int = 120


class FallbackGenerationModelConfig(BaseModel):
    """Fallback generation model configuration."""
    alias: str = "cloud_writer"
    provider: Literal["ollama"] = "ollama"
    endpoint: str = "http://localhost:11434"
    name: str = "llama3:latest"
    temperature: float = 0.1
    num_ctx: int = 16384
    timeout_seconds: int = 120


class EmbeddingModelConfig(BaseModel):
    """Embedding model configuration."""
    alias: str = "embedder"
    provider: Literal["ollama"] = "ollama"
    endpoint: str = "http://localhost:11434"
    name: str = "qwen3-embedding"
    batch_size: int = 16
    timeout_seconds: int = 120


class RoutingConfig(BaseModel):
    """Model routing configuration."""
    prefer_local: bool = True
    allow_cloud_fallback: bool = True
    fallback_on_oom: bool = True
    fallback_on_timeout: bool = True


class RetrievalConfig(BaseModel):
    """Retrieval configuration."""
    use_embeddings: bool = True
    top_k_lexical: int = 12
    top_k_semantic: int = 12
    top_k_final: int = 10
    lexical_weight: float = 0.55
    semantic_weight: float = 0.45
    include_neighbor_chunks: int = 1


class ChunkingConfig(BaseModel):
    """Chunking configuration."""
    target_chars: int = 1800
    max_chars: int = 2400
    min_chars: int = 500
    overlap_chars: int = 150
    split_on_headings: bool = True
    split_on_page_boundaries: bool = True


class WikiConfig(BaseModel):
    """Wiki generation configuration."""
    source_summary_dir: str = "sources"
    concept_dir: str = "concepts"
    entity_dir: str = "entities"
    comparison_dir: str = "comparisons"
    open_questions_dir: str = "open_questions"
    index_dir: str = "indexes"
    changelog_file: str = "CHANGELOG.md"
    cite_style: Literal["inline_brackets"] = "inline_brackets"
    require_citations: bool = True
    dry_run_default: bool = False


class CategoryConfig(BaseModel):
    """Category management configuration."""
    enabled: bool = True
    definitions_file: str = "./categories/defaults.yaml"
    allow_multi_label: bool = True
    use_llm_classification: bool = True
    use_rule_based_classification: bool = True
    default_category: str = "other"
    min_confidence_for_auto_accept: float = 0.65
    fallback_to_default_on_failure: bool = True
    boost_same_category_in_retrieval: bool = True
    category_dirs: dict = Field(default_factory=lambda: {
        "case_law": "legal/case_law",
        "legislation": "legal/legislation",
        "policy": "policy",
        "journal_article": "scholarship/journal_articles",
        "book_chapter": "scholarship/book_chapters",
        "teaching_material": "teaching",
        "research_report": "reports",
        "presentation_slides": "presentations",
        "other": "other",
    })


class MaintenanceConfig(BaseModel):
    """Maintenance configuration."""
    enable_lint: bool = True
    enable_link_repair: bool = True
    enable_orphan_detection: bool = True
    enable_staleness_checks: bool = True


class DaemonConfig(BaseModel):
    """Daemon/watch mode configuration."""
    enabled: bool = False
    backend: Literal["polling", "watchfiles"] = "polling"
    interval_seconds: int = 30


class PathsConfig(BaseModel):
    """Path configuration."""
    sources_dir: str = "./sources"
    wiki_dir: str = "./wiki"
    state_dir: str = ".llmwiki"
    cache_dir: str = ".llmwiki/cache"
    db_path: str = ".llmwiki/state.db"


class Config(BaseSettings):
    """Main configuration model."""
    model_config = SettingsConfigDict(
        env_prefix="LLMWIKI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: str = "desktop"
    paths: PathsConfig = Field(default_factory=PathsConfig)
    models: dict = Field(default_factory=lambda: {
        "generation": GenerationModelConfig().model_dump(),
        "fallback_generation": FallbackGenerationModelConfig().model_dump(),
        "embeddings": EmbeddingModelConfig().model_dump(),
    })
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    wiki: WikiConfig = Field(default_factory=WikiConfig)
    categories: CategoryConfig = Field(default_factory=CategoryConfig)
    maintenance: MaintenanceConfig = Field(default_factory=MaintenanceConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)

    @classmethod
    def load_from_file(cls, path: Path) -> "Config":
        """Load configuration from YAML file."""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def save_to_file(self, path: Path) -> None:
        """Save configuration to YAML file."""
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)

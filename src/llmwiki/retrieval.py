"""Retrieval pipeline with hybrid FTS + semantic search for llmwiki."""

import numpy as np
import ollama
from typing import List, Dict, Any, Optional
from rich.console import Console

from llmwiki.db.connection import DatabaseConnection
from llmwiki.config import Config

console = Console()


def cosine_similarity(query_embedding: List[float], doc_embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and document embeddings.
    
    Args:
        query_embedding: Query embedding vector
        doc_embeddings: Array of document embedding vectors
        
    Returns:
        Array of similarity scores
    """
    # Normalize query
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    
    # Normalize doc embeddings
    doc_norms = np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
    doc_norms = np.where(doc_norms == 0, 1, doc_norms)  # Avoid division by zero
    doc_normalized = doc_embeddings / doc_norms
    
    # Compute cosine similarity
    similarities = np.dot(doc_normalized, query_norm)
    
    return similarities


def embed_query(query: str, model: str, config: Config) -> Optional[List[float]]:
    """Embed a query using Ollama.
    
    Args:
        query: Query text
        model: Embedding model name
        config: Configuration
        
    Returns:
        Embedding vector or None if failed
    """
    try:
        response = ollama.embeddings(model=model, prompt=query)
        return response["embedding"]
    except Exception as e:
        console.print(f"[yellow]Warning: Embedding generation failed: {e}[/yellow]")
        return None


def retrieve_by_fts(db: DatabaseConnection, query: str, top_k: int = 12) -> List[Dict]:
    """Retrieve chunks using full-text search.
    
    Args:
        db: Database connection
        query: Search query
        top_k: Number of results to return
        
    Returns:
        List of chunk dicts with FTS results
    """
    try:
        # Use FTS5 match
        rows = db.fetchall(
            """SELECT c.id, c.text, c.page_start, c.page_end, c.chunk_index, 
                      sv.source_id
               FROM chunks c
               JOIN chunk_fts cf ON c.id = cf.rowid
               JOIN source_versions sv ON c.source_version_id = sv.id
               WHERE cf MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, top_k)
        )
        
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "chunk_index": row["chunk_index"],
                "source_id": row["source_id"],
                "similarity": 1.0,  # FTS doesn't have similarity score
                "retrieval_method": "fts"
            }
            for row in rows
        ]
    except Exception as e:
        console.print(f"[yellow]FTS query failed: {e}[/yellow]")
        return []


def retrieve_by_embeddings(
    db: DatabaseConnection,
    query: str,
    embed_model: str,
    config: Config,
    top_k: int = 12
) -> List[Dict]:
    """Retrieve chunks using semantic similarity search.
    
    Args:
        db: Database connection
        query: Query text
        embed_model: Embedding model name
        config: Configuration
        top_k: Number of results to return
        
    Returns:
        List of chunk dicts with similarity scores
    """
    # Embed the query
    query_embedding = embed_query(query, embed_model, config)
    
    if query_embedding is None:
        return []
    
    query_vec = np.array(query_embedding)
    
    try:
        # Get all embeddings (in production, would use vector index)
        rows = db.fetchall(
            """SELECT e.chunk_id, e.vector_blob, e.dims,
                      c.text, c.page_start, c.page_end, c.chunk_index,
                      sv.source_id
               FROM embeddings e
               JOIN chunks c ON e.chunk_id = c.id
               JOIN source_versions sv ON c.source_version_id = sv.id
               WHERE e.model_alias = ?
               ORDER BY e.created_at DESC""",
            (embed_model,)
        )
        
        if not rows:
            console.print("[yellow]No embeddings found in database[/yellow]")
            return []
        
        # Build embedding matrix
        import struct
        embeddings_list = []
        chunk_data = []
        
        for row in rows:
            # Unpack vector blob
            dims = row["dims"]
            vector_bytes = row["vector_blob"]
            vector = list(struct.unpack(f'{dims}f', vector_bytes))
            embeddings_list.append(vector)
            
            chunk_data.append({
                "id": row["chunk_id"],
                "text": row["text"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "chunk_index": row["chunk_index"],
                "source_id": row["source_id"]
            })
        
        # Convert to numpy array
        embeddings_matrix = np.array(embeddings_list)
        
        # Compute similarities
        similarities = cosine_similarity(query_vec, embeddings_matrix)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        # Build results
        results = []
        for idx in top_indices:
            if similarities[idx] > 0:  # Filter out negative similarities
                chunk = chunk_data[idx].copy()
                chunk["similarity"] = float(similarities[idx])
                chunk["retrieval_method"] = "semantic"
                results.append(chunk)
        
        return results
        
    except Exception as e:
        console.print(f"[yellow]Embedding retrieval failed: {e}[/yellow]")
        return []


def retrieve_relevant_chunks(
    db: DatabaseConnection,
    embed_model: str,
    query: str,
    config: Config,
    top_k: int = 10,
    use_hybrid: bool = True
) -> List[Dict]:
    """Retrieve relevant chunks using hybrid FTS + semantic search.
    
    Args:
        db: Database connection
        embed_model: Embedding model name
        query: User query
        config: Configuration
        top_k: Final number of chunks to return
        use_hybrid: Whether to use hybrid retrieval
        
    Returns:
        List of chunk dicts sorted by relevance
    """
    retrieval_cfg = config.retrieval
    
    # Get FTS results
    fts_results = retrieve_by_fts(db, query, retrieval_cfg.top_k_lexical)
    
    if not use_hybrid or not retrieval_cfg.use_embeddings:
        # FTS-only mode
        return fts_results[:top_k]
    
    # Get semantic results
    try:
        semantic_results = retrieve_by_embeddings(
            db, query, embed_model, config, retrieval_cfg.top_k_semantic
        )
    except Exception as e:
        console.print(f"[yellow]Semantic retrieval failed, falling back to FTS: {e}[/yellow]")
        return fts_results[:top_k]
    
    if not semantic_results:
        console.print("[yellow]No semantic results found, using FTS only[/yellow]")
        return fts_results[:top_k]
    
    # Merge results using weighted scoring
    # Normalize scores and combine
    all_chunks = {}
    
    # Add FTS results (score = 1.0 for all, could improve with BM25 scores)
    for i, chunk in enumerate(fts_results):
        chunk_id = chunk["id"]
        if chunk_id not in all_chunks:
            all_chunks[chunk_id] = chunk.copy()
            all_chunks[chunk_id]["fts_score"] = 1.0 - (i * 0.05)  # Decay by rank
        else:
            all_chunks[chunk_id]["fts_score"] = max(
                all_chunks[chunk_id].get("fts_score", 0),
                1.0 - (i * 0.05)
            )
    
    # Add semantic results
    for chunk in semantic_results:
        chunk_id = chunk["id"]
        if chunk_id not in all_chunks:
            all_chunks[chunk_id] = chunk.copy()
            all_chunks[chunk_id]["fts_score"] = 0.0
        all_chunks[chunk_id]["semantic_score"] = chunk["similarity"]
    
    # Compute combined scores
    for chunk_id, chunk in all_chunks.items():
        fts_score = chunk.get("fts_score", 0.0)
        semantic_score = chunk.get("semantic_score", 0.0)
        
        # Weighted combination
        combined = (
            retrieval_cfg.lexical_weight * fts_score +
            retrieval_cfg.semantic_weight * semantic_score
        )
        chunk["combined_score"] = combined
    
    # Sort by combined score
    sorted_chunks = sorted(
        all_chunks.values(),
        key=lambda x: x.get("combined_score", 0),
        reverse=True
    )
    
    # Return top-k
    return sorted_chunks[:top_k]


def get_chunk_neighbors(db: DatabaseConnection, chunk_id: int, n: int = 1) -> List[Dict]:
    """Get neighboring chunks (before and after) for context.
    
    Args:
        db: Database connection
        chunk_id: Center chunk ID
        n: Number of neighbors on each side
        
    Returns:
        List of neighbor chunk dicts
    """
    try:
        # Get the center chunk's source_version and chunk_index
        center = db.fetchone(
            """SELECT source_version_id, chunk_index, page_start, page_end
               FROM chunks WHERE id = ?""",
            (chunk_id,)
        )
        
        if not center:
            return []
        
        source_version_id = center["source_version_id"]
        chunk_index = center["chunk_index"]
        
        # Get neighbors
        neighbors = db.fetchall(
            """SELECT id, text, page_start, page_end, chunk_index
               FROM chunks
               WHERE source_version_id = ?
                 AND chunk_index BETWEEN ? AND ?
                 AND id != ?
               ORDER BY chunk_index""",
            (source_version_id, chunk_index - n, chunk_index + n, chunk_id)
        )
        
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "chunk_index": row["chunk_index"],
                "source_id": None,  # Would need join to get
                "similarity": 0.0,
                "retrieval_method": "neighbor"
            }
            for row in neighbors
        ]
    except Exception:
        return []

"""RAG specialist agent — ChromaDB + BM25 hybrid retrieval.

PHASE OFFLINE: index_documents() loads documents from ./data/documents/,
splits them, embeds with HuggingFace all-MiniLM-L6-v2, stores in four
ChromaDB collections, and builds a BM25Okapi index per collection.

PHASE ONLINE: rag_agent_node(state) retrieves from the appropriate collection
using Reciprocal Rank Fusion (RRF) of semantic + BM25 results and stores the
top-3 passages in state["rag_context"].
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Lazy imports — only required at startup (index_documents) ─────────────────

_chroma_client = None           # chromadb.PersistentClient instance
_embedding_fn = None            # HuggingFaceEmbeddings instance
_bm25_indexes: Dict[str, Any] = {}   # collection_name -> BM25Okapi
_corpus_docs: Dict[str, List[Dict[str, str]]] = {}  # collection_name -> [{text, source}]

# ── Collection → domain mapping ───────────────────────────────────────────────

DOMAIN_TO_COLLECTION: Dict[str, str] = {
    "hr":  "hr_policies",
    "crm": "crm_knowledge",
    "erp": "process_procedures",
    "rag": "process_procedures",
    "multi": "process_procedures",
}

# ── Filename keyword → collection routing ─────────────────────────────────────

KEYWORD_TO_COLLECTION: List[Tuple[List[str], str]] = [
    (["conge", "congé", "rh", "hr", "reglement", "règlement", "politique", "leave", "employe", "employé"], "hr_policies"),
    (["client", "crm", "commercial", "compte", "note", "fiche"], "crm_knowledge"),
    (["projet", "project", "spec", "technique", "cr_", "compte-rendu", "compterendu"], "project_docs"),
    (["procedure", "procédure", "faq", "process", "interne", "guide"], "process_procedures"),
]

DEFAULT_COLLECTION = "process_procedures"


def _filename_to_collection(filename: str) -> str:
    """Map a document filename to its target ChromaDB collection."""
    lower = filename.lower()
    for keywords, collection in KEYWORD_TO_COLLECTION:
        if any(kw in lower for kw in keywords):
            return collection
    return DEFAULT_COLLECTION


def index_documents() -> None:
    """Load, split, embed and index all documents from ./data/documents/.

    Called once at application startup.  Handles a missing directory gracefully.
    """
    global _chroma_client, _embedding_fn, _bm25_indexes, _corpus_docs

    # ── Resolve documents directory ───────────────────────────────────────────
    docs_dir = Path("./data/documents")
    if not docs_dir.exists():
        logger.warning(
            "rag_agent: documents directory '%s' not found — RAG will return empty context",
            docs_dir.resolve(),
        )
        return

    # ── Lazy-import heavy dependencies ────────────────────────────────────────
    try:
        import chromadb
        from langchain_community.document_loaders import PyPDFLoader, TextLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from rank_bm25 import BM25Okapi
    except ImportError as exc:
        logger.error(
            "rag_agent: missing dependency — %s — run: pip install chromadb "
            "langchain-community sentence-transformers rank-bm25 pypdf",
            exc,
        )
        return

    from app.core.config import settings

    # ── Initialise ChromaDB persistent client ─────────────────────────────────
    try:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    except Exception as exc:
        logger.error("rag_agent: failed to initialise ChromaDB client — %s", exc)
        return

    # ── Initialise HuggingFace embeddings ─────────────────────────────────────
    try:
        _embedding_fn = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        logger.info("rag_agent: HuggingFace embeddings loaded (all-MiniLM-L6-v2)")
    except Exception as exc:
        logger.error("rag_agent: failed to load HuggingFace embeddings — %s", exc)
        return

    # ── Text splitter ─────────────────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        length_function=len,
        add_start_index=True,
    )

    # ── Ensure the four collections exist ─────────────────────────────────────
    collection_names = ["hr_policies", "project_docs", "crm_knowledge", "process_procedures"]
    collections: Dict[str, Any] = {}
    for name in collection_names:
        try:
            col = _chroma_client.get_or_create_collection(name=name)
            collections[name] = col
            _corpus_docs[name] = []
        except Exception as exc:
            logger.error("rag_agent: failed to create collection '%s' — %s", name, exc)

    # ── Load and index documents ───────────────────────────────────────────────
    supported_extensions = {".pdf", ".md", ".txt"}
    doc_files = [
        f for f in docs_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    if not doc_files:
        logger.warning("rag_agent: no supported documents found in '%s'", docs_dir.resolve())
        _build_bm25_indexes(BM25Okapi)
        return

    logger.info("rag_agent: indexing %d document(s) from '%s'", len(doc_files), docs_dir.resolve())

    indexed_count = 0
    for doc_path in doc_files:
        try:
            # ── Load document ──────────────────────────────────────────────────
            suffix = doc_path.suffix.lower()
            if suffix == ".pdf":
                loader = PyPDFLoader(str(doc_path))
            else:
                loader = TextLoader(str(doc_path), encoding="utf-8")

            raw_docs = loader.load()
            if not raw_docs:
                logger.debug("rag_agent: empty document skipped — %s", doc_path.name)
                continue

            # ── Split into chunks ──────────────────────────────────────────────
            chunks = splitter.split_documents(raw_docs)
            if not chunks:
                continue

            # ── Route to collection ────────────────────────────────────────────
            col_name = _filename_to_collection(doc_path.name)
            if col_name not in collections:
                col_name = DEFAULT_COLLECTION

            collection = collections[col_name]

            # ── Embed and upsert ───────────────────────────────────────────────
            texts = [c.page_content for c in chunks]
            embeddings = _embedding_fn.embed_documents(texts)

            ids = [
                f"{doc_path.stem}__chunk_{i}"
                for i in range(len(chunks))
            ]
            metadatas = [
                {"source": doc_path.name, "chunk_index": i}
                for i in range(len(chunks))
            ]

            # Upsert in batches of 100 to avoid memory spikes
            batch_size = 100
            for start in range(0, len(ids), batch_size):
                batch_slice = slice(start, start + batch_size)
                collection.upsert(
                    ids=ids[batch_slice],
                    embeddings=embeddings[batch_slice],
                    documents=texts[batch_slice],
                    metadatas=metadatas[batch_slice],
                )

            # ── Populate BM25 corpus ───────────────────────────────────────────
            for text, meta in zip(texts, metadatas):
                _corpus_docs[col_name].append({"text": text, "source": meta["source"]})

            indexed_count += 1
            logger.info(
                "rag_agent: indexed '%s' → collection '%s' (%d chunks)",
                doc_path.name, col_name, len(chunks),
            )

        except Exception as exc:
            logger.warning("rag_agent: failed to index '%s' — %s", doc_path.name, exc)

    logger.info("rag_agent: indexing complete — %d documents processed", indexed_count)

    # ── Build BM25 indexes ────────────────────────────────────────────────────
    _build_bm25_indexes(BM25Okapi)


def _build_bm25_indexes(BM25Okapi) -> None:
    """Build a BM25Okapi index per collection from the in-memory corpus."""
    global _bm25_indexes
    for col_name, docs in _corpus_docs.items():
        if not docs:
            _bm25_indexes[col_name] = None
            continue
        tokenized_corpus = [doc["text"].lower().split() for doc in docs]
        try:
            _bm25_indexes[col_name] = BM25Okapi(tokenized_corpus)
            logger.debug(
                "rag_agent: BM25 index built for '%s' (%d docs)", col_name, len(docs)
            )
        except Exception as exc:
            logger.warning("rag_agent: BM25 index build failed for '%s' — %s", col_name, exc)
            _bm25_indexes[col_name] = None


# ── Online node ───────────────────────────────────────────────────────────────

from app.agents.state import AgentState  # noqa: E402  (import after helpers)


def rag_agent_node(state: AgentState) -> AgentState:
    """Hybrid RAG retrieval node (semantic + BM25 with RRF fusion).

    Selects the appropriate ChromaDB collection based on state["detected_domain"],
    runs semantic search and BM25 search, fuses results via Reciprocal Rank Fusion,
    and stores the top-3 passages in state["rag_context"].

    If the index is empty or unavailable, sets rag_context to "" without raising.

    Args:
        state: Current shared AgentState.

    Returns:
        Updated AgentState with rag_context populated.
    """
    # ── Guard: nothing indexed yet ────────────────────────────────────────────
    if _chroma_client is None or _embedding_fn is None:
        logger.debug("rag_agent_node: no index available — returning empty context")
        return {**state, "rag_context": ""}

    # ── Select collection ─────────────────────────────────────────────────────
    domain: str = (state.get("detected_domain") or "rag").lower()
    col_name: str = DOMAIN_TO_COLLECTION.get(domain, DEFAULT_COLLECTION)

    # ── Extract query from last human message ─────────────────────────────────
    from langchain_core.messages import HumanMessage

    query = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            query = str(msg.content).strip()
            break
    if not query:
        return {**state, "rag_context": ""}

    # ── Fetch ChromaDB collection ──────────────────────────────────────────────
    try:
        collection = _chroma_client.get_or_create_collection(name=col_name)
        col_count = collection.count()
    except Exception as exc:
        logger.warning("rag_agent_node: cannot access collection '%s' — %s", col_name, exc)
        return {**state, "rag_context": ""}

    if col_count == 0:
        logger.debug("rag_agent_node: collection '%s' is empty", col_name)
        return {**state, "rag_context": ""}

    # ── Semantic search ───────────────────────────────────────────────────────
    semantic_results: List[Dict[str, Any]] = []
    try:
        query_embedding = _embedding_fn.embed_query(query)
        n_semantic = min(5, col_count)
        chroma_response = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_semantic,
            include=["documents", "metadatas", "distances"],
        )

        docs_list = chroma_response.get("documents", [[]])[0] or []
        metas_list = chroma_response.get("metadatas", [[]])[0] or []

        for doc_text, meta in zip(docs_list, metas_list):
            source = (meta or {}).get("source", col_name)
            semantic_results.append({"text": doc_text, "source": source})

    except Exception as exc:
        logger.warning("rag_agent_node: semantic search failed — %s", exc)
        semantic_results = []

    # ── BM25 search ───────────────────────────────────────────────────────────
    bm25_results: List[Dict[str, Any]] = []
    bm25_index = _bm25_indexes.get(col_name)
    corpus = _corpus_docs.get(col_name, [])

    if bm25_index is not None and corpus:
        try:
            tokenized_query = query.lower().split()
            n_bm25 = min(5, len(corpus))
            top_docs = bm25_index.get_top_n(tokenized_query, corpus, n=n_bm25)
            bm25_results = [
                {"text": d["text"], "source": d["source"]}
                for d in top_docs
            ]
        except Exception as exc:
            logger.warning("rag_agent_node: BM25 search failed — %s", exc)

    # ── RRF fusion ────────────────────────────────────────────────────────────
    # score(doc) = 1/(rank_semantic + 60) + 1/(rank_bm25 + 60)
    # rank is 1-based; documents not present in a list get no contribution.

    rrf_scores: Dict[str, float] = {}
    doc_store: Dict[str, Dict[str, Any]] = {}  # text_key -> {text, source}

    def _doc_key(d: Dict[str, Any]) -> str:
        return d["text"][:120]  # first 120 chars as identity key

    for rank, doc in enumerate(semantic_results, start=1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rank + 60)
        doc_store[key] = doc

    for rank, doc in enumerate(bm25_results, start=1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rank + 60)
        doc_store[key] = doc

    sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)
    top_3_keys = sorted_keys[:3]

    if not top_3_keys:
        return {**state, "rag_context": ""}

    # ── Format context string ─────────────────────────────────────────────────
    fragments: List[str] = []
    for key in top_3_keys:
        doc = doc_store[key]
        score = rrf_scores[key]
        fragments.append(
            f"Source: {doc['source']} (score: {score:.3f})\n{doc['text']}\n---"
        )

    rag_context = "\n".join(fragments)

    logger.info(
        "rag_agent_node: retrieved %d passages from '%s' for domain='%s'",
        len(fragments), col_name, domain,
    )

    return {**state, "rag_context": rag_context}

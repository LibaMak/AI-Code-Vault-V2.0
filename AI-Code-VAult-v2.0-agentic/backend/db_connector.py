# ============================================================================
# DATABASE CONNECTOR - SQLAlchemy ORM & Database Models
# ============================================================================

import os
import hashlib
import json as _json
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, Float, Boolean, ForeignKey, JSON, inspect, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# Database Setup
Base = declarative_base()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./vault_v5.db')

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """User account model for authentication."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)  # Match actual database schema
    password_hash = Column(String)  # Fallback for backward compatibility
    session_token = Column(String, index=True)
    role = Column(String, default='User')
    scan_progress = Column(Integer, default=0)
    scan_status = Column(String, default='Idle')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Hub(Base):
    """Code repository/project hub model."""
    __tablename__ = 'hubs'
    
    id = Column(Integer, primary_key=True)
    hash_key = Column(String, index=True)  # Changed: removed unique=True, using composite constraint instead
    user_id = Column(Integer, ForeignKey('users.id'))
    repo_url = Column(String)
    code_snippet = Column(Text)
    embedding_vector = Column(JSON)  # Store embedding as JSON
    complexity_score = Column(Float, default=0.0)
    indexed_at = Column(DateTime, default=datetime.now)
    status = Column(String, default='active')
    
    # Composite unique constraint: hash_key is unique per user
    __table_args__ = (
        UniqueConstraint('user_id', 'hash_key', name='unique_user_hash'),
    )

class ChatMessage(Base):
    """Chat conversation history model."""
    __tablename__ = 'chat_messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)

class SearchHistory(Base):
    """Query/search history for analytics."""
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    query = Column(String)
    results_count = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.now)

class FileMetadata(Base):
    """Uploaded file metadata."""
    __tablename__ = 'file_metadata'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    filename = Column(String)
    file_type = Column(String)
    size = Column(Integer)
    upload_date = Column(DateTime, default=datetime.now)

class Satellite(Base):
    """Code metrics and complexity analysis."""
    __tablename__ = 'satellites'
    
    id = Column(Integer, primary_key=True)
    hub_hash = Column(String, ForeignKey('hubs.hash_key'))
    metrics = Column(JSON)  # Store metrics as JSON

class KeyPool(Base):
    """Global API credentials management."""
    __tablename__ = 'key_pool'
    
    id = Column(Integer, primary_key=True)
    provider = Column(String)  # 'GROQ', 'OPENROUTER', etc.
    key_value = Column(String)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class ScanJob(Base):
    """Background scan job tracking model."""
    __tablename__ = 'scan_jobs'

    id = Column(Integer, primary_key=True)
    job_uuid = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    repo_url = Column(String)
    status = Column(String, default='Pending')
    progress = Column(Integer, default=0)
    temp_dir = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ============================================================================
# DATA VAULT 2.0 — HUB TABLES
# ============================================================================

class HubCode(Base):
    """Data Vault 2.0 Hub for code entities."""
    __tablename__ = 'hub_code'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    natural_key = Column(String, nullable=False)


class HubRepository(Base):
    """Data Vault 2.0 Hub for repositories."""
    __tablename__ = 'hub_repository'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)


class HubUser(Base):
    """Data Vault 2.0 Hub for users."""
    __tablename__ = 'hub_user'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    email = Column(String, nullable=False)


class HubDocument(Base):
    """Data Vault 2.0 Hub for documents."""
    __tablename__ = 'hub_document'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    filename = Column(String, nullable=False)


# ============================================================================
# DATA VAULT 2.0 — LINK TABLES
# ============================================================================

class LinkCodeRepository(Base):
    """Data Vault 2.0 Link between code and repository."""
    __tablename__ = 'link_code_repository'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    hub_code_hash = Column(String, ForeignKey('hub_code.hash_key'), nullable=False)
    hub_repo_hash = Column(String, ForeignKey('hub_repository.hash_key'), nullable=False)


class LinkUserRepository(Base):
    """Data Vault 2.0 Link between user and repository."""
    __tablename__ = 'link_user_repository'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    hub_user_hash = Column(String, ForeignKey('hub_user.hash_key'), nullable=False)
    hub_repo_hash = Column(String, ForeignKey('hub_repository.hash_key'), nullable=False)


class LinkUserDocument(Base):
    """Data Vault 2.0 Link between user and document."""
    __tablename__ = 'link_user_document'

    hash_key = Column(String, primary_key=True)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    record_source = Column(String, nullable=False)
    hub_user_hash = Column(String, ForeignKey('hub_user.hash_key'), nullable=False)
    hub_doc_hash = Column(String, ForeignKey('hub_document.hash_key'), nullable=False)


# ============================================================================
# DATA VAULT 2.0 — SATELLITE TABLES (insert-only, temporal history)
# ============================================================================

class SatCodeContent(Base):
    """Satellite: versioned code content for a code hub."""
    __tablename__ = 'sat_code_content'

    id = Column(Integer, primary_key=True)
    hub_code_hash = Column(String, ForeignKey('hub_code.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    code_snippet = Column(Text)
    language = Column(String)
    file_path = Column(String)

    __table_args__ = (
        Index('idx_sat_current', 'hub_code_hash', 'load_end_date'),
    )


class SatCodeMetrics(Base):
    """Satellite: versioned code metrics for a code hub."""
    __tablename__ = 'sat_code_metrics'

    id = Column(Integer, primary_key=True)
    hub_code_hash = Column(String, ForeignKey('hub_code.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    lines_of_code = Column(Integer, default=0)
    complexity = Column(String)
    parameter_count = Column(Integer, default=0)


class SatCodeEmbedding(Base):
    """Satellite: versioned embedding vectors for a code hub."""
    __tablename__ = 'sat_code_embedding'

    id = Column(Integer, primary_key=True)
    hub_code_hash = Column(String, ForeignKey('hub_code.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    embedding_vector = Column(JSON)
    model_name = Column(String)

    __table_args__ = (
        Index('idx_sat_code_embedding_hub', 'hub_code_hash'),
    )


class SatDocumentContent(Base):
    """Satellite: versioned document chunk content for a document hub."""
    __tablename__ = 'sat_document_content'

    id = Column(Integer, primary_key=True)
    hub_doc_hash = Column(String, ForeignKey('hub_document.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    raw_text = Column(Text)
    chunk_index = Column(Integer, default=0)
    chunk_size = Column(Integer, default=0)


class SatDocumentEmbedding(Base):
    """Satellite: versioned embedding vectors for a document chunk hub."""
    __tablename__ = 'sat_document_embedding'

    id = Column(Integer, primary_key=True)
    hub_doc_hash = Column(String, ForeignKey('hub_document.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    embedding_vector = Column(JSON, nullable=True)
    model_name = Column(String)

    __table_args__ = (
        Index('idx_sat_doc_embedding_hub', 'hub_doc_hash'),
    )


class SatUserProfile(Base):
    """Satellite: versioned user profile for a user hub."""
    __tablename__ = 'sat_user_profile'

    id = Column(Integer, primary_key=True)
    hub_user_hash = Column(String, ForeignKey('hub_user.hash_key'), nullable=False)
    load_date = Column(DateTime, default=datetime.now, nullable=False)
    load_end_date = Column(DateTime, nullable=True)
    hash_diff = Column(String, nullable=False)
    role = Column(String)
    preferences = Column(JSON)

    @property
    def theme_preference(self):
        if not self.preferences:
            return "System"
        return self.preferences.get("theme_preference", self.preferences.get("theme", "System"))

    @theme_preference.setter
    def theme_preference(self, val):
        if not self.preferences:
            self.preferences = {}
        # Support both keys for compatibility
        self.preferences["theme_preference"] = val
        self.preferences["theme"] = val

    @property
    def full_name(self):
        if not self.preferences:
            return None
        return self.preferences.get("full_name")

    @full_name.setter
    def full_name(self, val):
        if not self.preferences:
            self.preferences = {}
        self.preferences["full_name"] = val

    @property
    def avatar_url(self):
        if not self.preferences:
            return None
        return self.preferences.get("avatar_url")

    @avatar_url.setter
    def avatar_url(self, val):
        if not self.preferences:
            self.preferences = {}
        self.preferences["avatar_url"] = val


# ============================================================================
# EVALUATION CHECKLIST TABLES
# ============================================================================

class Document(Base):
    """Evaluation checklist: document tracking table."""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    filename = Column(String, nullable=False)
    file_type = Column(String)
    size = Column(Integer, default=0)
    upload_date = Column(DateTime, default=datetime.now)
    chunk_count = Column(Integer, default=0)
    status = Column(String, default='pending')
    column_names = Column(JSON, nullable=True)  # Store CSV column metadata


class Search(Base):
    """Evaluation checklist: search tracking table."""
    __tablename__ = 'searches'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    query = Column(String, nullable=False)
    results = Column(JSON)
    scores = Column(JSON)
    response_time_ms = Column(Integer, default=0)
    results_count = Column(Integer, default=0)
    top_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_search_user_time', 'user_id', 'timestamp'),
    )


class Feedback(Base):
    """Evaluation checklist: user feedback table."""
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    search_id = Column(Integer, ForeignKey('searches.id'), nullable=True)
    chat_message_id = Column(Integer, ForeignKey('chat_messages.id'), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)


# ============================================================================
# COMPOSITE INDEXES
# ============================================================================

# idx_hubs_user_repo: composite index on existing hubs table (user_id, repo_url)
Index('idx_hubs_user_repo', Hub.user_id, Hub.repo_url)

# idx_sat_current is defined in SatCodeContent.__table_args__
# idx_search_user_time is defined in Search.__table_args__


# ============================================================================
# DATA VAULT 2.0 — HASH FUNCTIONS
# ============================================================================

def compute_hash_key(*args):
    """Compute an MD5 hash key from concatenated positional arguments.

    This implements the Data Vault 2.0 business-key hashing pattern.
    All arguments are cast to strings and joined with '||' before hashing.
    """
    raw = '||'.join(str(a) for a in args)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def compute_hash_diff(**kwargs):
    """Compute an MD5 hash diff from sorted keyword arguments.

    This implements the Data Vault 2.0 change-detection pattern.
    Keyword arguments are sorted by key, serialized to a stable JSON
    string, and hashed.  Used to detect whether a satellite row has
    actually changed before inserting a new version.
    """
    ordered = {k: kwargs[k] for k in sorted(kwargs.keys())}
    raw = _json.dumps(ordered, default=str, ensure_ascii=False)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def get_user_scoped_query(session, model, user_id):
    """Enforces row-level security (RLS) by scoping queries to the specified user_id.
    
    Ensures that no database queries for documents, chat history, or search history
    leak data between users.
    """
    query = session.query(model)
    if hasattr(model, 'user_id'):
        return query.filter(model.user_id == user_id)
    return query


# ============================================================================
# DATA VAULT 2.0 — LOAD FUNCTION (insert-only pattern)
# ============================================================================

def load_data_vault(session, hub_model, satellite_model, hub_data, sat_data,
                    hub_hash_key, record_source='vault_app',
                    hub_fk_column='hub_code_hash'):
    """Load data into a Data Vault 2.0 hub + satellite pair.

    Implements the insert-only pattern:
      1. Check if the hub already exists; insert only if missing.
      2. Compute hash_diff for the satellite payload; compare with the
         current (open) satellite row.
      3. If hash_diff differs: close the old satellite (set load_end_date)
         and insert a new satellite row.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active DB session.
    hub_model : type
        SQLAlchemy hub model class (e.g. HubCode).
    satellite_model : type
        SQLAlchemy satellite model class (e.g. SatCodeContent).
    hub_data : dict
        Column values for the hub row (must include 'hash_key').
    sat_data : dict
        Column values for the satellite row (excluding hash_diff,
        load_date, load_end_date, and the hub FK which are managed
        automatically).
    hub_hash_key : str
        Pre-computed hash key for the hub.
    record_source : str
        Origin system identifier stored in the hub.
    hub_fk_column : str
        Name of the FK column in the satellite that references the hub.
    """
    now = datetime.now()

    # --- Hub: insert only if missing ---
    existing_hub = session.query(hub_model).filter(
        hub_model.hash_key == hub_hash_key
    ).first()
    if not existing_hub:
        hub_row = hub_model(
            hash_key=hub_hash_key,
            load_date=now,
            record_source=record_source,
            **hub_data,
        )
        session.add(hub_row)
        session.flush()

    # --- Satellite: compare hash_diff, close-and-insert if changed ---
    new_hash_diff = compute_hash_diff(**sat_data)

    current_sat = (
        session.query(satellite_model)
        .filter(
            getattr(satellite_model, hub_fk_column) == hub_hash_key,
            satellite_model.load_end_date.is_(None),
        )
        .first()
    )

    if current_sat and current_sat.hash_diff == new_hash_diff:
        # No change — skip insert
        return current_sat

    if current_sat:
        # Close the old satellite row
        current_sat.load_end_date = now
        session.flush()

    # Insert new satellite version
    sat_row = satellite_model(
        **{hub_fk_column: hub_hash_key},
        load_date=now,
        load_end_date=None,
        hash_diff=new_hash_diff,
        **sat_data,
    )
    session.add(sat_row)
    session.flush()
    return sat_row


# ============================================================================
# DATA VAULT 2.0 — POINT-IN-TIME QUERY
# ============================================================================

def query_point_in_time(session, satellite_model, hub_hash, as_of_datetime,
                        hub_fk_column='hub_code_hash'):
    """Return the satellite row that was active at a given point in time.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active DB session.
    satellite_model : type
        SQLAlchemy satellite model class.
    hub_hash : str
        Hash key of the parent hub.
    as_of_datetime : datetime
        The point in time to query.
    hub_fk_column : str
        Name of the FK column in the satellite that references the hub.

    Returns
    -------
    object or None
        The satellite row active at the given time, or None.
    """
    return (
        session.query(satellite_model)
        .filter(
            getattr(satellite_model, hub_fk_column) == hub_hash,
            satellite_model.load_date <= as_of_datetime,
            sa.or_(
                satellite_model.load_end_date.is_(None),
                satellite_model.load_end_date > as_of_datetime,
            ),
        )
        .first()
    )


# ============================================================================
# DATA VAULT 2.0 — HYBRID SEARCH
# ============================================================================

def run_hybrid_search(session, query, user_id, top_k=5):
    """Hybrid Search using SQL LIKE keyword search and Cosine Similarity Reranking.
    
    1. SQL LIKE keyword search first to filter candidates.
    2. If LIKE returns zero results, return empty list immediately.
    3. Cosine similarity reranking on the candidates.
    4. Hybrid score = 0.7 * semantic + 0.3 * keyword.
    5. Return results with confidence scores (0.0 to 1.0) and source attribution.
    """
    from embeddings import get_embeddings
    import numpy as np
    import re
    
    scored_results = []
    
    # Split query into words to do a flexible search / scoring
    words = [w.strip().lower() for w in query.split() if len(w.strip()) > 1]
    if not words:
        words = [query.lower()]
        
    # Get user email for DV2.0 document mapping
    user_row = session.query(User).filter(User.id == user_id).first()
    user_email = user_row.email if user_row else None
    user_hash = compute_hash_key(user_email) if user_email else None
    
    # Retrieve all unique files/paths for this user from database
    code_paths = [r[0] for r in session.query(Hub.hash_key).filter(Hub.user_id == user_id, sa.or_(Hub.status != 'deleted', Hub.status.is_(None))).distinct().all() if r[0]]
    doc_filenames = []
    if user_email and user_hash:
        doc_filenames = [r[0] for r in session.query(HubDocument.filename).select_from(LinkUserDocument).join(
            HubDocument, LinkUserDocument.hub_doc_hash == HubDocument.hash_key
        ).where(
            LinkUserDocument.hub_user_hash == user_hash
        ).distinct().all() if r[0]]
        
    all_files = list(set(code_paths + doc_filenames))
    
    query_lower = query.lower()
    normalized_query = query_lower.replace(" ", "").replace("|", "/")
    
    # Sort files by length descending to match full paths/filenames before basenames
    all_files_sorted = sorted(all_files, key=len, reverse=True)
    
    matched_files = []
    
    # Check direct path/filename mention in the query
    # E.g. "backend/agent.py" or "ai-legal-aid-pakistan | prompts.py"
    for f in all_files_sorted:
        normalized_f = f.lower().replace("\\", "/").replace(" ", "")
        clean_f = normalized_f.split("::chunk_")[0]
        if clean_f in normalized_query:
            matched_files.append(f)
            
    # Build map of basename -> list of full paths/filenames
    basename_map = {}
    for f in all_files:
        f_norm = f.replace("\\", "/").split("::chunk_")[0]
        base = f_norm.split("/")[-1]
        if base:
            basename_map.setdefault(base.lower(), []).append(f)
            
    disambiguation_result = None
    
    if not matched_files:
        # Check if a filename is mentioned alone (meaning no path prefix is in the query)
        for base_lower, full_paths in basename_map.items():
            pattern = r'\b' + re.escape(base_lower) + r'\b'
            if re.search(pattern, query_lower):
                # Disambiguate only if different files are matched (ignoring chunk indexes)
                unique_base_files = list({fp.split("::chunk_")[0] for fp in full_paths})
                if len(unique_base_files) > 1:
                    # Multiple distinct files match the filename alone!
                    paths_str = " or ".join(f"'{p}'" for p in unique_base_files)
                    disambig_msg = f"Multiple files found matching '{base_lower}' ({paths_str}). Please specify the full path to get the right answer."
                    disambiguation_result = [{
                        "name": "disambiguation_required",
                        "snippet": disambig_msg,
                        "score": 1.0,
                        "type": "document"
                    }]
                    break
                else:
                    matched_files = full_paths
                    break
                    
    # If no filename matched, check if a directory/path is mentioned in the query
    if not matched_files and not disambiguation_result:
        matched_dirs = []
        for f in all_files:
            f_norm = f.replace("\\", "/").lower()
            parts = f_norm.split("/")
            if len(parts) > 1:
                # Check directory prefixes (e.g. "backend", "ai-legal-aid-pakistan")
                for i in range(1, len(parts)):
                    dir_path = "/".join(parts[:i])
                    pattern = r'\b' + re.escape(dir_path) + r'\b'
                    if re.search(pattern, query_lower) and dir_path not in matched_dirs:
                        matched_dirs.append(dir_path)
        if matched_dirs:
            for f in all_files:
                f_norm = f.replace("\\", "/").lower()
                for d in matched_dirs:
                    if f_norm.startswith(d + "/"):
                        matched_files.append(f)
                        
    if disambiguation_result:
        return disambiguation_result
        
    # Query candidate chunks based on matched_files filter or keyword search
    if matched_files:
        # If specific paths/files are targeted, directly retrieve all their chunks
        code_candidates = session.query(Hub).filter(Hub.user_id == user_id, sa.or_(Hub.status != 'deleted', Hub.status.is_(None)), Hub.hash_key.in_(matched_files)).all()
        
        doc_candidates = []
        if user_email and user_hash:
            doc_stmt = sa.select(
                HubDocument.filename,
                SatDocumentContent.raw_text,
                SatDocumentEmbedding.embedding_vector,
                SatDocumentContent.chunk_index
            ).select_from(LinkUserDocument).join(
                HubDocument, LinkUserDocument.hub_doc_hash == HubDocument.hash_key
            ).join(
                SatDocumentContent, HubDocument.hash_key == SatDocumentContent.hub_doc_hash
            ).outerjoin(
                SatDocumentEmbedding,
                sa.and_(
                    SatDocumentContent.hub_doc_hash == SatDocumentEmbedding.hub_doc_hash,
                    SatDocumentContent.hash_diff == SatDocumentEmbedding.hash_diff,
                    SatDocumentEmbedding.load_end_date.is_(None)
                )
            ).where(
                LinkUserDocument.hub_user_hash == user_hash,
                SatDocumentContent.load_end_date.is_(None),
                HubDocument.filename.in_(matched_files)
            )
            doc_candidates = session.execute(doc_stmt).all()
    else:
        # Default behavior: SQL LIKE keyword search first to filter candidates
        like_conds = []
        for w in words:
            like_conds.append(Hub.code_snippet.like(f"%{w}%"))
            like_conds.append(Hub.hash_key.like(f"%{w}%"))
            
        code_stmt = sa.select(Hub).where(Hub.user_id == user_id, sa.or_(Hub.status != 'deleted', Hub.status.is_(None)))
        if like_conds:
            code_stmt = code_stmt.where(sa.or_(*like_conds))
            
        code_candidates = session.execute(code_stmt).scalars().all()
        
        doc_candidates = []
        if user_email and user_hash:
            doc_stmt = sa.select(
                HubDocument.filename,
                SatDocumentContent.raw_text,
                SatDocumentEmbedding.embedding_vector,
                SatDocumentContent.chunk_index
            ).select_from(LinkUserDocument).join(
                HubDocument, LinkUserDocument.hub_doc_hash == HubDocument.hash_key
            ).join(
                SatDocumentContent, HubDocument.hash_key == SatDocumentContent.hub_doc_hash
            ).outerjoin(
                SatDocumentEmbedding,
                sa.and_(
                    SatDocumentContent.hub_doc_hash == SatDocumentEmbedding.hub_doc_hash,
                    SatDocumentContent.hash_diff == SatDocumentEmbedding.hash_diff,
                    SatDocumentEmbedding.load_end_date.is_(None)
                )
            ).where(
                LinkUserDocument.hub_user_hash == user_hash,
                SatDocumentContent.load_end_date.is_(None)
            )
            
            doc_like_conds = []
            for w in words:
                doc_like_conds.append(SatDocumentContent.raw_text.like(f"%{w}%"))
                doc_like_conds.append(HubDocument.filename.like(f"%{w}%"))
                
            if doc_like_conds:
                doc_stmt = doc_stmt.where(sa.or_(*doc_like_conds))
                
            doc_candidates = session.execute(doc_stmt).all()
            
        # If LIKE returns zero results across BOTH code and documents, fall back to retrieving all to enable semantic search
        if not code_candidates and not doc_candidates:
            code_stmt = sa.select(Hub).where(Hub.user_id == user_id, sa.or_(Hub.status != 'deleted', Hub.status.is_(None)))
            code_candidates = session.execute(code_stmt).scalars().all()
            if user_email and user_hash:
                doc_stmt = sa.select(
                    HubDocument.filename,
                    SatDocumentContent.raw_text,
                    SatDocumentEmbedding.embedding_vector,
                    SatDocumentContent.chunk_index
                ).select_from(LinkUserDocument).join(
                    HubDocument, LinkUserDocument.hub_doc_hash == HubDocument.hash_key
                ).join(
                    SatDocumentContent, HubDocument.hash_key == SatDocumentContent.hub_doc_hash
                ).outerjoin(
                    SatDocumentEmbedding,
                    sa.and_(
                        SatDocumentContent.hub_doc_hash == SatDocumentEmbedding.hub_doc_hash,
                        SatDocumentContent.hash_diff == SatDocumentEmbedding.hash_diff,
                        SatDocumentEmbedding.load_end_date.is_(None)
                    )
                ).where(
                    LinkUserDocument.hub_user_hash == user_hash,
                    SatDocumentContent.load_end_date.is_(None)
                )
                doc_candidates = session.execute(doc_stmt).all()

    # Generate query embedding only if candidates exist
    try:
        query_vector = np.array(get_embeddings([query])[0])
    except Exception as e:
        print(f"Error generating embedding for search: {e}")
        query_vector = None
        
    # Process code candidates
    for c in code_candidates:
        emb_data = c.embedding_vector
        if isinstance(emb_data, str):
            try:
                emb_data = _json.loads(emb_data)
            except Exception:
                emb_data = None
        emb = np.array(emb_data) if emb_data and len(emb_data) > 0 else None
        
        sem_score = 0.0
        if emb is not None and query_vector is not None:
            try:
                dot = np.dot(emb, query_vector)
                norm_prod = np.linalg.norm(emb) * np.linalg.norm(query_vector)
                if norm_prod > 0:
                    sim = dot / norm_prod
                    sem_score = max(0.0, float(sim))
            except Exception:
                pass
                
        text_lower = (c.code_snippet or "").lower()
        name_lower = (c.hash_key or "").lower()
        match_count = sum(1 for w in words if w in text_lower or w in name_lower)
        keyword_score = match_count / len(words) if words else 0.0
        
        hybrid_score = 0.7 * sem_score + 0.3 * keyword_score
        
        repo_name = c.repo_url.split('/')[-1] if c.repo_url else "code"
        source_name = f"{repo_name} | {c.hash_key}"
        
        scored_results.append({
            "name": source_name,
            "snippet": c.code_snippet,
            "score": min(1.0, max(0.0, round(float(hybrid_score), 3))),
            "type": "code"
        })
        
    # Process document candidates
    for r in doc_candidates:
        emb_data = r.embedding_vector
        if isinstance(emb_data, str):
            try:
                emb_data = _json.loads(emb_data)
            except Exception:
                emb_data = None
        emb = np.array(emb_data) if emb_data and len(emb_data) > 0 else None
        
        sem_score = 0.0
        if emb is not None and query_vector is not None:
            try:
                dot = np.dot(emb, query_vector)
                norm_prod = np.linalg.norm(emb) * np.linalg.norm(query_vector)
                if norm_prod > 0:
                    sim = dot / norm_prod
                    sem_score = max(0.0, float(sim))
            except Exception:
                pass
                
        text_lower = (r.raw_text or "").lower()
        name_lower = (r.filename or "").lower()
        match_count = sum(1 for w in words if w in text_lower or w in name_lower)
        keyword_score = match_count / len(words) if words else 0.0
        
        hybrid_score = 0.7 * sem_score + 0.3 * keyword_score
        
        part_name = f"{r.filename} | chunk {r.chunk_index + 1}" if r.chunk_index is not None else r.filename
        
        scored_results.append({
            "name": part_name,
            "snippet": r.raw_text,
            "score": min(1.0, max(0.0, round(float(hybrid_score), 3))),
            "type": "document"
        })
        
    # Sort by score descending
    scored_results.sort(key=lambda x: x['score'], reverse=True)
    return scored_results[:top_k]


# ============================================================================
# DATA VAULT 2.0 — SQL VIEWS
# ============================================================================

def create_views(engine=None):
    """Create analytical SQL views.

    Creates (or replaces) four views used by the evaluation checklist:
      - user_activity_summary
      - document_search_summary
      - complex_code_units
      - search_analytics
    """
    engine = engine or get_engine()
    views = [
        # 1. user_activity_summary
        """
        CREATE VIEW IF NOT EXISTS user_activity_summary AS
        SELECT
            u.id            AS user_id,
            u.email         AS email,
            u.role          AS role,
            (SELECT COUNT(*) FROM searches s WHERE s.user_id = u.id)   AS total_searches,
            (SELECT COUNT(*) FROM documents d WHERE d.user_id = u.id)  AS total_documents,
            (SELECT COUNT(*) FROM feedback f WHERE f.user_id = u.id)   AS total_feedback,
            (SELECT AVG(f.rating) FROM feedback f WHERE f.user_id = u.id) AS avg_rating
        FROM users u
        """,
        # 2. document_search_summary
        """
        CREATE VIEW IF NOT EXISTS document_search_summary AS
        SELECT
            d.id            AS document_id,
            d.filename      AS filename,
            d.file_type     AS file_type,
            d.user_id       AS user_id,
            d.chunk_count   AS chunk_count,
            d.status        AS status,
            (SELECT COUNT(*) FROM searches s WHERE s.user_id = d.user_id) AS user_search_count,
            (SELECT AVG(s.response_time_ms) FROM searches s WHERE s.user_id = d.user_id) AS avg_response_time_ms
        FROM documents d
        """,
        # 3. complex_code_units
        """
        CREATE VIEW IF NOT EXISTS complex_code_units AS
        SELECT
            hc.hash_key       AS code_hash_key,
            hc.natural_key    AS natural_key,
            sc.code_snippet   AS code_snippet,
            sm.lines_of_code  AS lines_of_code,
            sm.complexity     AS complexity,
            sm.parameter_count AS parameter_count
        FROM hub_code hc
        LEFT JOIN sat_code_content sc
            ON sc.hub_code_hash = hc.hash_key AND sc.load_end_date IS NULL
        LEFT JOIN sat_code_metrics sm
            ON sm.hub_code_hash = hc.hash_key AND sm.load_end_date IS NULL
        WHERE sm.complexity IN ('High', 'Medium')
        """,
        # 4. search_analytics
        """
        CREATE VIEW IF NOT EXISTS search_analytics AS
        SELECT
            user_id,
            COUNT(*)                    AS search_count,
            AVG(response_time_ms)       AS avg_response_time_ms,
            MIN(timestamp)              AS first_search,
            MAX(timestamp)              AS last_search
        FROM searches
        GROUP BY user_id
        """,
    ]

    with engine.begin() as conn:
        for view_sql in views:
            try:
                conn.execute(sa.text(view_sql))
            except Exception as e:
                print(f"[DB Views] Warning creating view: {e}")


# ============================================================================
# DATABASE INITIALIZATION & MIGRATION
# ============================================================================

def get_engine():
    """Create and return database engine."""
    if DATABASE_URL.startswith('sqlite'):
        engine = create_engine(
            DATABASE_URL,
            connect_args={'check_same_thread': False},
            poolclass=StaticPool
        )
    else:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return engine

def init_db():
    """Initialize database and create all tables with constraint migration."""
    engine = get_engine()
    
    # Handle constraint migration for hubs table
    if DATABASE_URL.startswith('sqlite'):
        inspector = inspect(engine)
        if 'hubs' in inspector.get_table_names():
            # Check if old constraint exists
            constraints = inspector.get_unique_constraints('hubs')
            has_old_constraint = any(
                constraint['column_names'] == ('hash_key',) 
                for constraint in constraints
            )
            
            if has_old_constraint:
                print("[DB Migration] Detected old UNIQUE constraint on hubs.hash_key")
                print("[DB Migration] Recreating hubs table with composite constraint...")
                
                # Drop the old table and recreate with new constraints
                with engine.begin() as conn:
                    conn.execute(sa.text('DROP TABLE hubs'))
                    print("[DB Migration] Old hubs table dropped")
                
                # Create all tables (including new hubs table with composite constraint)
                Base.metadata.create_all(bind=engine)
                print("[DB Migration] Hubs table recreated with composite (user_id, hash_key) constraint")
    
    # Create all tables (idempotent for tables that don't need migration)
    Base.metadata.create_all(bind=engine)

    # Create Data Vault 2.0 analytical views
    try:
        create_views(engine)
    except Exception as e:
        print(f"[DB Init] Warning: Could not create views: {e}")

    # Run migrations to update columns on existing databases
    run_migrations(engine)

    return engine

def get_session():
    """Get a database session."""
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()

def run_migrations(engine=None):
    """Run database migrations.

    Accepts an optional engine for compatibility with streamlit_app.py.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name == 'sqlite':
        inspector = inspect(engine)
        user_columns = {column['name'] for column in inspector.get_columns('users')}
        if 'session_token' not in user_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE users ADD COLUMN session_token VARCHAR'))

        # Migrate documents (add column_names)
        doc_columns = {column['name'] for column in inspector.get_columns('documents')}
        if 'column_names' not in doc_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE documents ADD COLUMN column_names TEXT'))

        # Migrate searches (add response_time_ms, results_count, top_score)
        search_columns = {column['name'] for column in inspector.get_columns('searches')}
        if 'response_time_ms' not in search_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE searches ADD COLUMN response_time_ms INTEGER DEFAULT 0'))
        if 'results_count' not in search_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE searches ADD COLUMN results_count INTEGER DEFAULT 0'))
        if 'top_score' not in search_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE searches ADD COLUMN top_score FLOAT DEFAULT 0.0'))

        # Migrate hubs (add status)
        hub_columns = {column['name'] for column in inspector.get_columns('hubs')}
        if 'status' not in hub_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE hubs ADD COLUMN status VARCHAR DEFAULT "active"'))

        # Migrate feedback (add chat_message_id)
        feedback_columns = {column['name'] for column in inspector.get_columns('feedback')}
        if 'chat_message_id' not in feedback_columns:
            with engine.begin() as connection:
                connection.execute(sa.text('ALTER TABLE feedback ADD COLUMN chat_message_id INTEGER'))

def get_schema_diagnostics(engine):
    """Get database schema diagnostics."""
    try:
        # Check if database file exists
        if 'sqlite' in DATABASE_URL:
            db_file = DATABASE_URL.replace('sqlite:///', '')
            file_exists = os.path.exists(db_file)
        else:
            file_exists = True
        
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        return {
            'file_exists': file_exists,
            'file_path': DATABASE_URL,
            'tables_created': True,
            'tables': tables
        }
    except Exception as e:
        return {
            'file_exists': False,
            'file_path': DATABASE_URL,
            'error': str(e)
        }

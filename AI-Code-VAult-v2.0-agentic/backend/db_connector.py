# ============================================================================
# DATABASE CONNECTOR - SQLAlchemy ORM & Database Models
# ============================================================================

import os
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, Float, Boolean, ForeignKey, JSON, inspect, UniqueConstraint
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

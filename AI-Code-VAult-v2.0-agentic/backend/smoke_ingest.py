import os
import tempfile
import uuid
from datetime import datetime

# Ensure backend modules import correctly
from db_connector import init_db, get_engine, get_session, User, ScanJob, Hub
from agent import run_ingest_agent

# Initialize DB
engine = init_db()

# Create test user
session = get_session()
user = session.query(User).filter(User.email == 'smoke@test.local').first()
if not user:
    user = User(email='smoke@test.local', hashed_password='x', role='User')
    session.add(user)
    session.commit()
    session.refresh(user)

user_id = user.id

# Create ScanJob
job_uuid = str(uuid.uuid4())
job = ScanJob(job_uuid=job_uuid, user_id=user_id, repo_url='https://github.com/octocat/Hello-World', status='Queued', progress=0)
session.add(job)
session.commit()

print(f"Created user {user_id} and ScanJob {job_uuid}")

# Run agent ingest (limit chunks for speed)
summary = run_ingest_agent('https://github.com/octocat/Hello-World', user_id, job_uuid=job_uuid, max_chunks=10)
print('Agent summary:', summary)

# Check DB for created hubs
session = get_session()
hubs = session.query(Hub).filter(Hub.user_id == user_id).all()
print(f"Hubs created: {len(hubs)}")
for h in hubs:
    print('-', h.hash_key, 'embedding_len=', len(h.embedding_vector) if h.embedding_vector else 0)

# Check for leftover temp clone dirs
temp_root = tempfile.gettempdir()
leftovers = [d for d in os.listdir(temp_root) if d.startswith('vault_repo_')]
print('Leftover temp dirs in', temp_root, ':', leftovers)

print('Smoke ingest finished at', datetime.utcnow().isoformat() + 'Z')

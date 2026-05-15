# 🧪 INGESTION FIXES - TESTING & VALIDATION

## Current Status
✅ **Application Restarted**
- Streamlit server: Running at http://localhost:8501
- Database: Reset (vault_v5.db recreated with new schema)
- Code: All 7 fixes applied and deployed

---

## Test Plan

### Phase 1: Basic Repository Ingestion ⭐ PRIMARY TEST
**Goal:** Verify core bug fixes work correctly

1. **Setup**
   - Login credentials: `admin@vault.ai` / `admin123`
   - Target repo: `https://github.com/fastapi/fastapi` (small public repo)

2. **Execute Ingestion**
   ```
   Step 1: Go to "Scan Repository" tab
   Step 2: Enter repository URL
   Step 3: Click "Initialize Vault Ingestion"
   Step 4: Watch progress bar (should reach ~100%)
   Step 5: Check System Telemetry Logs for debug output
   ```

3. **Verify Fixes:**
   
   **Fix #1 - repo_url Propagation**
   - ✅ Check: Progress bar shows "Scanning chunks..." 
   - ✅ Verify: System logs show "Extracting chunks from [repo_url]"
   - ❌ Fail: Progress bar shows error about empty repo_url
   
   **Fix #2 - Duplicate Detection**
   - ✅ Check: Ingestion completes without "UNIQUE constraint failed" error
   - ✅ Verify: Message shows "Complete — N code hubs indexed"
   - ❌ Fail: Error message contains "UNIQUE constraint failed: hubs.hash_key"
   
   **Fix #3 - Per-User Constraints**
   - ✅ Check: First user can ingest successfully
   - ✅ Verify: No constraint errors even if many users have same code
   - ❌ Fail: Error "UNIQUE constraint failed" when second user ingests same repo
   
   **Fix #4 - Logging System**
   - ✅ Check: System Telemetry Logs expand and show output
   - ✅ Verify: Logs show timestamps like "[2026-05-14 16:24:37]"
   - ❌ Fail: Logs are empty or don't update during ingestion

---

### Phase 2: Multi-User Isolation Test
**Goal:** Verify per-user unique constraints work

1. **Create Second User Account**
   ```
   Click: Logout Access
   Click: Create New Account
   Email: dev@vault.ai
   Password: dev123
   ```

2. **Re-ingest Same Repository**
   ```
   Step 1: Ingest https://github.com/fastapi/fastapi
   Step 2: Should complete successfully (not fail with duplicate key)
   Step 3: Check that second user has own isolated copy
   ```

3. **Verify Isolation**
   - ✅ User 1 (liba) has ~523 hubs from FastAPI
   - ✅ User 2 (dev) has separate ~523 hubs from same repo
   - ✅ No constraint violations during second ingestion
   - ❌ Fail: Second user gets "UNIQUE constraint failed" error

---

### Phase 3: File Upload Ingestion Test
**Goal:** Verify file upload with repo_url tracking works

1. **Create Test File**
   ```python
   # test_sample.py
   def hello_world():
       """Simple test function."""
       print("Hello, World!")
       return 42
   
   class DataProcessor:
       def __init__(self, data):
           self.data = data
       
       def process(self):
           return [x * 2 for x in self.data]
   ```

2. **Upload via UI**
   ```
   Click: File System Source tab
   Upload: test_sample.py
   Watch: Progress bar
   Check: System Telemetry logs
   ```

3. **Verify Upload Fix**
   - ✅ Check: File ingested successfully without errors
   - ✅ Verify: Logs show "Extracting text from file: test_sample.py"
   - ✅ Verify: repo_url shows as "file_upload/test_sample.py"
   - ✅ Verify: Chunks created with proper metadata
   - ❌ Fail: Error about missing repo_url in upload

---

### Phase 4: Duplicate Handling Test
**Goal:** Verify duplicate detection and re-indexing

1. **Re-ingest Same Repository**
   ```
   Step 1: Same user, same repo URL
   Step 2: Click "Initialize Vault Ingestion" again
   Step 3: Wait for completion
   ```

2. **Verify Duplicate Handling**
   - ✅ Check: No duplicate key error (Fix #2 working)
   - ✅ Verify: Hubs updated instead of creating duplicates
   - ✅ Verify: Same number of hubs (not doubled)
   - ❌ Fail: Database error about duplicates

---

### Phase 5: Error Recovery Test
**Goal:** Verify logging and error handling

1. **Try Invalid Repository**
   ```
   Enter: https://github.com/this-repo-does-not-exist/fake-repo-name-12345
   Click: Initialize Vault Ingestion
   Wait: See error handling
   ```

2. **Check Error Logging**
   - ✅ Check: System Telemetry shows error message
   - ✅ Verify: Error is logged with timestamp
   - ✅ Verify: App doesn't crash, UI recovers
   - ❌ Fail: App crashes or hangs

---

## Expected Outcomes

### Fix Validation Checklist

| Fix # | Description | How to Verify | Status |
|-------|-------------|---------------|--------|
| 1 | repo_url in chunks | Logs show repo URLs correctly | 🔄 PENDING |
| 2 | Duplicate detection | No UNIQUE constraint errors | 🔄 PENDING |
| 3 | Per-user constraints | Multiple users can ingest same code | 🔄 PENDING |
| 4 | File logging | System Telemetry shows timestamps | 🔄 PENDING |
| 5 | File upload repo_url | Uploads tracked as file_upload/* | 🔄 PENDING |
| 6 | Duplicate handling | Re-ingestion updates instead of fails | 🔄 PENDING |
| 7 | UniqueConstraint import | App loads without import errors | 🔄 PENDING |

---

## Success Criteria

### ✅ All Tests Pass When:
1. First repository ingestion completes without errors
2. Progress bar reaches 100% and shows "Complete — N hubs indexed"
3. System Telemetry logs display with timestamps
4. Second user can ingest same repository
5. File uploads work with file_upload/filename tracking
6. Re-ingesting same repo updates instead of creating errors
7. Invalid repos show graceful error messages

### ❌ Tests Fail If:
1. "UNIQUE constraint failed" error appears
2. Progress bar gets stuck or shows red error
3. System Telemetry logs are empty
4. Second user gets duplicate key error
5. File uploads fail silently
6. Re-ingestion creates constraint violations
7. App crashes or becomes unresponsive

---

## Rollback Plan

If tests fail, rollback available:

```bash
# If critical error, kill Streamlit
Get-Process streamlit | Stop-Process -Force

# Restore previous db_connector.py if needed
# (Git backup available if version control is active)

# Reset database and restart
Remove-Item vault_v5.db
streamlit run streamlit_app.py
```

---

## Debug Information Location

**Log File:** `/tmp/vault_v6_debug.log`
**Database:** `vault_v5.db` (SQLite)
**Terminal Output:** PowerShell terminal with Streamlit process

**Check Logs Via UI:**
- Click "🛠️ System Telemetry Logs (V6.1)" expand button
- Shows last 50 lines of `/tmp/vault_v6_debug.log`
- Timestamps show ISO format (YYYY-MM-DD HH:MM:SS)

---

## Next Steps After Validation

### If All Tests Pass ✅:
1. Document success in INGESTION_FIXES.md
2. Create performance benchmarks
3. Archive initial test results
4. Plan Phase 2 optimizations:
   - Batch processing large repos
   - Parallel chunk extraction
   - Incremental indexing for updates

### If Tests Partially Pass 🟡:
1. Identify specific failed fix
2. Review code changes for that fix
3. Check debug logs for root cause
4. Make targeted fixes
5. Re-test specific scenario

### If Tests Fail ❌:
1. Check error message in System Telemetry
2. Review terminal output for stack trace
3. Verify database connection works
4. Check .env file has GROQ_API_KEY
5. Rollback if needed

---

## Performance Benchmarks to Track

After successful ingestion, measure:

```
- Chunks indexed per second
- Average chunk size (should be ~1500 chars)
- Embedding generation time
- Database write time per chunk
- Total ingestion time for repository
- Memory usage during processing
```

Document in `/tmp/vault_v6_debug.log` for analysis.

---

## Quick Start Commands

```powershell
# If needed, restart fresh:
Remove-Item "vault_v5.db" -ErrorAction SilentlyContinue
streamlit run streamlit_app.py

# Monitor logs in real-time:
Get-Content -Path "/tmp/vault_v6_debug.log" -Wait -Tail 20

# Check database exists:
Test-Path "vault_v5.db"

# Verify Streamlit running:
Get-Process streamlit
```


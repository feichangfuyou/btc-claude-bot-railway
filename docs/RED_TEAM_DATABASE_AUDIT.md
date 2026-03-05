# Red Team Audit: Database → API Key Extraction

**Scope:** Attack paths to extract exchange API keys from the database layer.

---

## Data Flow Summary

| Storage        | Contains API Keys? | Access Control                    |
|----------------|--------------------|-----------------------------------|
| **Supabase** `user_exchanges` | Yes (`api_key_enc`, `api_secret_enc`) | RLS (unknown policies in repo)     |
| **SQLite** `bot.db`           | No                 | File system only                  |
| **Backups** `backups/*.db`    | No                 | SQLite copies only                |

---

## Attack Vectors

### 1. Direct Supabase REST API (Anon Key)

**Exposure:** `VITE_SUPABASE_ANON_KEY` is bundled in the frontend. Anyone can extract it from the built JS.

**Query pattern:**
```http
POST https://<project>.supabase.co/rest/v1/user_exchanges
  ?select=api_key_enc,api_secret_enc,user_id,exchange
  &user_id=eq.<TARGET_USER_UUID>
Headers:
  apikey: <ANON_KEY>
  Authorization: Bearer <JWT or empty>
```

**Mitigation:** Supabase RLS. If `user_exchanges` has:
- `auth.uid() = user_id` for SELECT → users only see own rows ✅
- No RLS or permissive policy → **all keys readable** ❌

**Finding:** No RLS migrations in repo. **Assumption:** RLS must be configured in Supabase Dashboard. If not, anon key + direct REST = full table read.

**Recommendation:** Add RLS migration to repo and document:
```sql
ALTER TABLE user_exchanges ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users read own exchanges"
  ON user_exchanges FOR SELECT
  USING (auth.uid() = user_id);
CREATE POLICY "Users insert own exchanges"
  ON user_exchanges FOR INSERT
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own exchanges"
  ON user_exchanges FOR UPDATE
  USING (auth.uid() = user_id);
```

---

### 2. Frontend Over-Fetch

**Exposure:** Settings.jsx line 138, 223:
```javascript
supabase.from("user_exchanges").select("*").eq("user_id", user.id)
```

`select("*")` returns **all columns** including `api_key_enc` and `api_secret_enc`. The UI only displays `exchange`, `connection_type`, `is_active` — but the full row (with keys) is stored in React state.

**Risks:**
- **React DevTools:** Attacker with physical access can inspect `exchanges` state and see keys.
- **XSS:** Any stored XSS could `JSON.stringify(exchanges)` and exfiltrate.
- **Memory dump:** Keys reside in browser memory.

**Recommendation:** Select only needed columns:
```javascript
supabase.from("user_exchanges")
  .select("exchange, connection_type, is_active, created_at")
  .eq("user_id", user.id)
```

---

### 3. Backend Service Key

**Exposure:** `get_supabase()` uses `SUPABASE_SERVICE_KEY` — bypasses RLS. Backend can read any row.

**Callers of key-bearing functions:**
- `get_user_exchange_keys(user_id, exchange)` — **never called** in codebase.
- `save_user_exchange` — called only with `user.id` from JWT.
- `load_user_config` — selects only `exchange`, not keys.

**Finding:** No backend endpoint returns raw API keys. `get_user_exchange_keys` exists but is unused (likely for future per-user execution).

**Risks if service key leaks:**
- `.env` in repo, logs, or backups
- Compromised host
- Overly permissive IAM

**Recommendation:** Ensure `SUPABASE_SERVICE_KEY` is never logged or committed. Rotate if exposed.

---

### 4. SQLite (bot.db)

**Finding:** SQLite stores trades, bot_state, decision_audit_log, etc. **No user_exchanges or API keys.** Keys live only in Supabase.

**Attack:** File read of `bot.db` or `backups/*.db` yields no exchange keys.

---

### 5. IDOR / Parameter Tampering

**Checked:** All auth routes use `user.id` from `get_current_user()` (JWT). No `user_id` in path or query. No IDOR path found.

---

### 6. Logging

**Checked:** `api/exchange_validate.py` — no logging of request body. Keys not logged during validate or connect.

---

## Summary: Viable Paths to API Keys

| Vector                    | Severity | Condition                          |
|---------------------------|----------|------------------------------------|
| Supabase RLS missing      | **Critical** | `user_exchanges` without RLS      |
| Frontend select("*")      | **Medium**   | XSS or DevTools / memory access   |
| Service key compromise   | **Critical** | Key in env leak / backup / host   |
| SQLite / backups         | **N/A**      | Keys not stored there             |

---

## Recommended Hardening

1. **RLS:** Add and enforce RLS on `user_exchanges`; store migration in repo. → **Done:** `supabase/migrations/20260305000000_rls_user_exchanges.sql`
2. **Frontend:** Change to `select("exchange, connection_type, is_active")` — never fetch key columns in the client. → **Done:** Settings.jsx
3. **Encryption:** Already implemented; ensure `EXCHANGE_KEYS_ENCRYPTION_KEY` is set in production.
4. **Audit:** Confirm RLS policies in Supabase Dashboard; document in runbook. → **Done:** RUNBOOK.md

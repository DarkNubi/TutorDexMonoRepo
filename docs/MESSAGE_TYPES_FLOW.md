# TutorDex Message Types: Comprehensive Flow Documentation

> **Investigation Date:** 2026-01-18  
> **Purpose:** Document how TutorDex handles different Telegram message types (edits, forwards, replies)

---

## Executive Summary

TutorDex comprehensively tracks **message edits**, **forwarded messages**, and **reply messages** in the `telegram_messages_raw` table. Each message type has distinct tracking and processing behavior:

| Message Type | Tracked in DB? | Database Update? | Processed by Extraction? | Notes |
|--------------|---------------|------------------|-------------------------|--------|
| **Edits** | ✅ Yes | ✅ Yes (upsert) | ✅ Yes (re-queued) | Full re-extraction triggered |
| **Forwards** | ✅ Yes | ✅ Yes | ❌ No (filtered) | Skipped during extraction |
| **Replies** | ✅ Yes | ✅ Yes | ✅ Yes | Processed normally |

---

## 1. Message Edits

### Overview
Message edits are **fully tracked and trigger re-extraction**. When a Telegram message is edited, TutorDex:
1. Captures the edit event via Telethon
2. Updates the database row with the new content and `edit_date`
3. Force-enqueues a new extraction job to reprocess the edited content
4. Updates the downstream `assignments` table with new parsed data

### Implementation

#### Collection (Event Handler)
**File:** `TutorDexAggregator/collection/tail.py` (lines 159-197)

```python
@client.on(events.MessageEdited(chats=entities))
async def _on_edit(event) -> None:
    """Handle message edits by re-ingesting and re-extracting."""
    msg = event.message
    channel_link = _channel_link_for_event(event)
    channel_id = _channel_id_for_event(event)
    
    # Build raw row with updated content
    row = build_raw_row(
        channel_link=channel_link,
        channel_id=channel_id,
        msg=msg
    )
    
    # Upsert to database (updates existing row)
    _, ok_rows = store.upsert_messages_batch(rows=[row])
    
    # Force re-extraction with force=True
    enqueue_extraction_jobs(
        store,
        cfg=ctx.cfg,
        channel_link=channel_link,
        message_ids=[str(getattr(msg, "id", ""))],
        force=True  # ← Key: bypasses "already processed" check
    )
```

**Key Behavior:**
- `force=True` ensures extraction queue creates a new job even if the message was previously processed
- The entire message is re-extracted with the LLM to capture content changes
- Previous extraction results are replaced in the `assignments` table

#### Database Persistence
**File:** `TutorDexAggregator/supabase_raw_persist.py` (lines 507-531)

```python
def build_raw_row(channel_link: str, channel_id: str | None, msg) -> dict:
    """Build raw row from Telethon message object."""
    return {
        "channel_link": channel_link,
        "channel_id": channel_id,
        "message_id": str(getattr(msg, "id", "")),
        "message_date": _parse_timestamp(getattr(msg, "date", None)),
        "edit_date": _parse_timestamp(getattr(msg, "edit_date", None)),  # ← Edit timestamp
        "raw_text": getattr(msg, "text", "") or "",
        "is_forward": bool(getattr(msg, "fwd_from", None) is not None),
        "is_reply": bool(getattr(msg, "reply_to_msg_id", None) is not None),
        "message_json": {
            # Full message captured including:
            "edit_date": getattr(msg, "edit_date", None),
            # ... other fields
        }
    }
```

#### Database Schema
**File:** `TutorDexAggregator/supabase sqls/supabase_schema_full.sql` (lines 1507-1580)

```sql
create table if not exists public.telegram_messages_raw (
  id bigserial primary key,
  channel_link text not null,
  message_id text not null,
  message_date timestamptz not null,
  
  -- Edit tracking
  edit_date timestamptz,  -- ← Timestamp of last edit
  
  -- Complete message snapshot
  message_json jsonb not null,  -- Contains full msg including edit_date
  
  -- Audit timestamps
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  
  -- Unique constraint ensures upserts work correctly
  constraint telegram_messages_raw_channel_message_uq 
    unique (channel_link, message_id)
);
```

#### Recovery Utility (Offline Re-Enqueueing)
**File:** `TutorDexAggregator/utilities/enqueue_edited_raws.py`

For cases where the collector was offline during edits, this utility:
1. Scans `telegram_messages_raw` for rows with non-null `edit_date`
2. Enqueues extraction jobs with `force=true`
3. Maintains checkpoint state based on `last_edit_date`

```bash
# Usage: Reprocess messages edited after a specific date
python utilities/enqueue_edited_raws.py --since "2026-01-01"
```

### Flow Diagram: Message Edit

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Telegram Agency Channel                                   │
│    User edits assignment post                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. TutorDex Collector (tail.py)                             │
│    @client.on(events.MessageEdited)                          │
│    - Captures edit event via Telethon                        │
│    - Builds updated raw_row with new content + edit_date    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Supabase: telegram_messages_raw (UPSERT)                 │
│    - Updates existing row (channel_link, message_id)        │
│    - Sets edit_date timestamp                                │
│    - Updates raw_text, message_json with new content        │
│    - Updates last_seen_at                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Enqueue Extraction Job (force=True)                      │
│    - Calls enqueue_telegram_extractions RPC                  │
│    - Creates new job in telegram_extractions table          │
│    - force=True bypasses "already processed" check          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Extraction Worker (extract_worker.py)                    │
│    - Claims job from queue                                   │
│    - Loads updated raw_text from telegram_messages_raw      │
│    - Re-runs LLM extraction with new content                │
│    - Applies deterministic signals                           │
│    - Validates output                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Supabase: assignments (UPDATE/UPSERT)                    │
│    - Updates existing assignment row                         │
│    - Replaces parsed fields with new extraction results     │
│    - Preserves assignment id but updates content            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Website/Backend                                           │
│    - Users see updated assignment content                    │
│    - No duplicate assignment created                         │
└─────────────────────────────────────────────────────────────┘
```

### Important Notes

1. **Idempotency:** The `(channel_link, message_id)` unique constraint ensures edits update the same row, not create duplicates
2. **Audit Trail:** Both `edit_date` and `message_json` preserve the edit history
3. **No Downtime Loss:** If the collector is offline during edits, use `enqueue_edited_raws.py` to catch up
4. **Full Re-Extraction:** The entire message is re-parsed with the LLM; partial updates are not supported
5. **Downstream Propagation:** The `assignments` table is updated via the normal persistence flow

---

## 2. Forwarded Messages

### Overview
Forwarded messages are **tracked but NOT processed**. TutorDex explicitly skips forwarded messages during extraction because:
- They typically represent reposts from other channels (not original agency posts)
- They may lack original context needed for accurate extraction
- They create duplicate assignment entries

### Implementation

#### Detection & Storage
**File:** `TutorDexAggregator/supabase_raw_persist.py` (lines 523)

```python
def build_raw_row(channel_link: str, channel_id: str | None, msg) -> dict:
    return {
        # Forward detection
        "is_forward": bool(getattr(msg, "fwd_from", None) is not None),
        
        # Forward metadata (preserved for audit)
        "message_json": {
            "fwd_from": getattr(msg, "fwd_from", None),  # Original source info
            "forwards": getattr(msg, "forwards", None),   # Forward count
            # ...
        }
    }
```

**Telethon `fwd_from` Object Structure:**
```python
# Example fwd_from structure:
{
    "from_id": <original sender/channel>,
    "from_name": "Agency Name",
    "date": <original post date>,
    "channel_post": <original message id>,
    # ...
}
```

#### Database Schema
```sql
create table if not exists public.telegram_messages_raw (
  -- ...
  is_forward boolean not null default false,  -- ← Forward flag
  forwards int,  -- Number of times this message was forwarded
  message_json jsonb not null,  -- Contains fwd_from details
  -- ...
);
```

#### Filtering (Skip During Extraction)
**File:** `TutorDexAggregator/workers/message_processor.py` (lines 116-118)

```python
def filter_message(raw: dict) -> MessageFilterResult:
    """Pre-LLM filtering to skip non-assignment messages."""
    
    # Check if forwarded
    if bool(raw.get("is_forward")):
        return MessageFilterResult(
            should_skip=True,
            reason="forward"
        )
    
    # ... other filters
```

**Result:** Forwarded messages are saved to `telegram_messages_raw` but never queued for extraction.

### Flow Diagram: Forwarded Message

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Telegram Agency Channel                                   │
│    Agency forwards a message from another channel            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. TutorDex Collector (tail.py)                             │
│    - Receives message via Telethon                           │
│    - Detects msg.fwd_from is not None                       │
│    - Builds raw_row with is_forward=true                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Supabase: telegram_messages_raw (INSERT)                 │
│    ✅ Message IS stored with:                                │
│       - is_forward = true                                    │
│       - fwd_from metadata in message_json                   │
│       - forwards count                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Enqueue Extraction? (Check)                              │
│    - Collector enqueues jobs as normal                       │
│    - Extraction job IS created in telegram_extractions      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Extraction Worker (message_processor.py)                 │
│    - Claims job from queue                                   │
│    - Loads raw from telegram_messages_raw                   │
│    - Calls filter_message()                                  │
│    - Detects is_forward=true                                 │
│    ❌ SKIPS PROCESSING                                        │
│    - Updates job status to "skipped" with reason="forward"  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Result: NO Assignment Created                            │
│    ❌ Not extracted by LLM                                    │
│    ❌ Not persisted to assignments table                      │
│    ❌ Not broadcasted                                         │
│    ❌ Not sent as DM                                          │
│    ✅ Audit trail preserved in telegram_messages_raw         │
└─────────────────────────────────────────────────────────────┘
```

### Important Notes

1. **Storage vs Processing:** Forwards ARE stored (for audit) but NOT processed
2. **Rationale:** Prevents duplicate assignments when agencies repost from other channels
3. **Audit Trail:** `message_json.fwd_from` preserves original source information
4. **No Extraction:** LLM is never called for forwarded messages (cost savings)
5. **No False Negatives:** If an agency manually copies (not forwards) content, it will be processed normally

---

## 3. Reply Messages

### Overview
Reply messages are **tracked AND processed normally**. When a message is a reply to another message, TutorDex:
1. Stores the `reply_to_msg_id` in the database
2. Processes the message through normal extraction
3. Does NOT fetch or include the parent message content in extraction

### Implementation

#### Detection & Storage
**File:** `TutorDexAggregator/supabase_raw_persist.py` (lines 524)

```python
def build_raw_row(channel_link: str, channel_id: str | None, msg) -> dict:
    return {
        # Reply detection
        "is_reply": bool(getattr(msg, "reply_to_msg_id", None) is not None),
        
        # Reply metadata
        "message_json": {
            "reply_to_msg_id": getattr(msg, "reply_to_msg_id", None),
            # ...
        }
    }
```

#### Database Schema
```sql
create table if not exists public.telegram_messages_raw (
  -- ...
  is_reply boolean not null default false,  -- ← Reply flag
  reply_count int,  -- Number of replies this message has
  message_json jsonb not null,  -- Contains reply_to_msg_id
  -- ...
);
```

#### Processing (No Special Filter)
**File:** `TutorDexAggregator/workers/message_processor.py`

```python
def filter_message(raw: dict) -> MessageFilterResult:
    """Pre-LLM filtering to skip non-assignment messages."""
    
    # Forward check
    if bool(raw.get("is_forward")):
        return MessageFilterResult(should_skip=True, reason="forward")
    
    # Empty message check
    if not raw.get("raw_text", "").strip():
        return MessageFilterResult(should_skip=True, reason="empty")
    
    # NO EXPLICIT REPLY CHECK
    # → Reply messages are processed normally
    
    # ... other filters
```

**Result:** Reply messages go through normal extraction pipeline.

### Flow Diagram: Reply Message

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Telegram Agency Channel                                   │
│    Agency posts a message that replies to another message    │
│    (e.g., "ASSIGNMENT CLOSED" replying to original post)    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. TutorDex Collector (tail.py)                             │
│    - Receives message via Telethon                           │
│    - Detects msg.reply_to_msg_id is not None                │
│    - Builds raw_row with is_reply=true                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Supabase: telegram_messages_raw (INSERT)                 │
│    ✅ Message IS stored with:                                │
│       - is_reply = true                                      │
│       - reply_to_msg_id in message_json                     │
│       - reply_count (replies this message has received)     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Enqueue Extraction Job                                    │
│    - Normal enqueue_telegram_extractions RPC                 │
│    - Job created in telegram_extractions table              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Extraction Worker (extract_worker.py)                    │
│    - Claims job from queue                                   │
│    - Loads raw_text from telegram_messages_raw              │
│    - NO REPLY FILTERING                                      │
│    ✅ PROCESSES NORMALLY                                      │
│    - Runs LLM extraction                                     │
│    - Applies deterministic signals                           │
│    - Validates output                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Supabase: assignments (INSERT/UPDATE)                    │
│    ✅ Assignment IS created/updated                           │
│    - Parsed fields populated from extraction                │
│    - reply_to_msg_id metadata available in raw table        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Broadcast/DM (Optional)                                   │
│    ✅ Eligible for broadcast to aggregator channel           │
│    ✅ Eligible for DM to matched tutors                       │
└─────────────────────────────────────────────────────────────┘
```

### Important Notes

1. **No Special Treatment:** Reply messages are processed exactly like non-reply messages
2. **Parent Context Not Fetched:** The extraction only sees the reply message text, not the original message being replied to
3. **Use Case Examples:**
   - Agency posts "ASSIGNMENT CLOSED" as a reply → Extracted normally (may be caught by non-assignment detector)
   - Agency posts additional details as a reply → Extracted as standalone message
4. **Metadata Preserved:** `reply_to_msg_id` is available in `telegram_messages_raw.message_json` for future analysis
5. **Potential Enhancement:** Could fetch parent message and combine contexts for better extraction (not currently implemented)

---

## 4. Database Schema Summary

### telegram_messages_raw Table (Complete)

```sql
create table if not exists public.telegram_messages_raw (
  -- Primary key
  id bigserial primary key,
  
  -- Channel identification
  channel_link text not null,
  channel_id text,
  message_id text not null,
  
  -- Timestamps
  message_date timestamptz not null,       -- Original post time
  edit_date timestamptz,                   -- Last edit time (null if never edited)
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  deleted_at timestamptz,                  -- Deletion time (for deleted messages)
  
  -- Message type flags
  is_forward boolean not null default false,  -- ← Forward detection
  is_reply boolean not null default false,    -- ← Reply detection
  
  -- Content
  raw_text text,                           -- Plain text content
  entities_json jsonb,                     -- Formatting entities
  media_json jsonb,                        -- Media attachments
  
  -- Metadata
  sender_id text,
  views int,                               -- View count
  forwards int,                            -- Forward count
  reply_count int,                         -- Number of replies
  
  -- Complete message snapshot
  message_json jsonb not null,             -- Full Telethon message object
                                           -- Contains: fwd_from, reply_to_msg_id, edit_date, etc.
  
  -- Unique constraint for upserts
  constraint telegram_messages_raw_channel_message_uq 
    unique (channel_link, message_id)
);

-- Indexes for common queries
create index if not exists telegram_messages_raw_edit_date_idx 
  on public.telegram_messages_raw (edit_date) 
  where edit_date is not null;

create index if not exists telegram_messages_raw_is_forward_idx 
  on public.telegram_messages_raw (is_forward) 
  where is_forward = true;

create index if not exists telegram_messages_raw_is_reply_idx 
  on public.telegram_messages_raw (is_reply) 
  where is_reply = true;
```

### message_json Structure (JSONB)

The `message_json` column contains the complete Telethon message object, including:

```json
{
  "id": 12345,
  "date": "2026-01-18T10:00:00Z",
  "message": "Assignment text...",
  
  // Edit tracking
  "edit_date": "2026-01-18T11:30:00Z",  // Present if edited
  
  // Forward tracking
  "fwd_from": {                          // Present if forwarded
    "from_id": {...},
    "from_name": "Original Agency",
    "date": "2026-01-17T15:00:00Z",
    "channel_post": 54321
  },
  "forwards": 15,                        // Forward count
  
  // Reply tracking
  "reply_to_msg_id": 12340,              // Present if reply
  "reply_to": {...},                     // Full reply metadata
  
  // Other fields
  "views": 250,
  "entities": [...],
  "media": {...},
  // ...
}
```

---

## 5. Operational Queries

### Query Edited Messages
```sql
-- Find all edited messages in the last 7 days
SELECT 
  channel_link,
  message_id,
  message_date,
  edit_date,
  raw_text
FROM public.telegram_messages_raw
WHERE edit_date IS NOT NULL
  AND edit_date > now() - interval '7 days'
ORDER BY edit_date DESC;
```

### Query Forwarded Messages
```sql
-- Find all forwarded messages
SELECT 
  channel_link,
  message_id,
  is_forward,
  message_json->'fwd_from'->>'from_name' as original_source,
  forwards as forward_count
FROM public.telegram_messages_raw
WHERE is_forward = true
ORDER BY message_date DESC;
```

### Query Reply Messages
```sql
-- Find all reply messages with parent reference
SELECT 
  channel_link,
  message_id,
  is_reply,
  (message_json->>'reply_to_msg_id')::bigint as parent_message_id,
  raw_text
FROM public.telegram_messages_raw
WHERE is_reply = true
ORDER BY message_date DESC;
```

### Query Messages Needing Re-Extraction (Edited but Not Reprocessed)
```sql
-- Find edited messages without recent extraction
SELECT 
  raw.channel_link,
  raw.message_id,
  raw.edit_date,
  MAX(ext.updated_at) as last_extraction
FROM public.telegram_messages_raw raw
LEFT JOIN public.telegram_extractions ext 
  ON ext.raw_id = raw.id
WHERE raw.edit_date IS NOT NULL
  AND (ext.updated_at IS NULL OR raw.edit_date > ext.updated_at)
GROUP BY raw.channel_link, raw.message_id, raw.edit_date
ORDER BY raw.edit_date DESC;
```

---

## 6. Known Limitations & Future Enhancements

### Current Limitations

1. **Reply Context Not Included:**
   - Reply messages are extracted without parent message context
   - May lead to incomplete information if the reply assumes parent context
   - Example: Reply says "This is for Secondary 3" but doesn't include subject (which was in parent)

2. **Forward Detection Not Configurable:**
   - All forwards are skipped without exception
   - May miss legitimate agency posts that happen to be forwards

3. **Edit Re-Extraction Always Full:**
   - Even minor edits (typo fixes) trigger full LLM re-extraction
   - No partial update capability

4. **No Edit History:**
   - Only the latest version is stored (edit_date updated)
   - Previous versions are lost (no versioning)

### Potential Enhancements

#### Enhancement 1: Smart Reply Context Inclusion
```python
# Proposed implementation
async def fetch_reply_context(client, msg):
    """Fetch parent message if this is a reply."""
    if msg.reply_to_msg_id:
        try:
            parent = await client.get_messages(
                msg.chat_id, 
                ids=msg.reply_to_msg_id
            )
            return f"[Parent message]: {parent.text}\n\n[Reply]: {msg.text}"
        except Exception:
            return msg.text  # Fallback to reply only
    return msg.text
```

**Benefits:**
- Better extraction quality for reply messages
- Captures full conversation context

**Risks:**
- Additional Telegram API calls
- May fetch deleted parent messages (error handling needed)

#### Enhancement 2: Selective Forward Processing
```python
# Proposed configuration
ALLOW_FORWARDS_FROM = [
    "t.me/trusted_agency_1",
    "t.me/trusted_agency_2"
]

def should_process_forward(raw: dict) -> bool:
    """Allow forwards from trusted sources."""
    if not raw.get("is_forward"):
        return True
    
    fwd_from = raw.get("message_json", {}).get("fwd_from", {})
    from_name = fwd_from.get("from_name", "")
    
    return from_name in ALLOW_FORWARDS_FROM
```

**Benefits:**
- Capture legitimate cross-posts from trusted agencies
- Configurable via environment variable

**Risks:**
- Potential for duplicate assignments if same message appears in multiple channels

#### Enhancement 3: Edit History Versioning
```sql
-- Proposed schema
create table if not exists public.telegram_messages_raw_history (
  id bigserial primary key,
  raw_id bigint references public.telegram_messages_raw(id),
  version int not null,
  raw_text_snapshot text,
  message_json_snapshot jsonb,
  edit_date timestamptz not null,
  created_at timestamptz not null default now(),
  constraint unique_version unique (raw_id, version)
);
```

**Benefits:**
- Audit trail for content changes
- Can analyze how agencies update posts over time
- Rollback capability if needed

**Risks:**
- Storage overhead for frequently edited messages
- Complexity in managing versions

#### Enhancement 4: Smart Edit Detection (Reduce Re-Extraction)
```python
def is_significant_edit(old_text: str, new_text: str) -> bool:
    """Determine if edit requires re-extraction."""
    import difflib
    
    # Calculate similarity ratio
    ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()
    
    # Only re-extract if >10% change
    return ratio < 0.90
```

**Benefits:**
- Reduce LLM API costs for minor edits
- Faster processing for typo corrections

**Risks:**
- May miss important changes (e.g., rate changes with similar text)
- Complexity in defining "significant"

---

## 7. Testing & Validation

### Test Cases

#### Test Case 1: Message Edit Flow
```
GIVEN a message exists in telegram_messages_raw
WHEN the agency edits the message in Telegram
THEN:
  1. telegram_messages_raw row is updated (not duplicated)
  2. edit_date is set to edit timestamp
  3. New extraction job is created with force=true
  4. Worker re-processes the message
  5. assignments table is updated with new content
  6. Only one assignment row exists (no duplicate)
```

#### Test Case 2: Forwarded Message Filtering
```
GIVEN an agency forwards a message from another channel
WHEN the collector receives the forwarded message
THEN:
  1. telegram_messages_raw row is created with is_forward=true
  2. fwd_from metadata is preserved in message_json
  3. Extraction job is created but skipped by worker
  4. NO assignment row is created
  5. Job status is "skipped" with reason="forward"
```

#### Test Case 3: Reply Message Processing
```
GIVEN an agency posts a reply to an existing message
WHEN the collector receives the reply message
THEN:
  1. telegram_messages_raw row is created with is_reply=true
  2. reply_to_msg_id is stored in message_json
  3. Extraction job is created and processed normally
  4. Assignment row is created from reply text only
  5. Parent message context is NOT included (current behavior)
```

### Validation Queries

```sql
-- Validate all three flags are being set correctly
SELECT 
  COUNT(*) as total_messages,
  SUM(CASE WHEN is_forward THEN 1 ELSE 0 END) as forwards,
  SUM(CASE WHEN is_reply THEN 1 ELSE 0 END) as replies,
  SUM(CASE WHEN edit_date IS NOT NULL THEN 1 ELSE 0 END) as edited
FROM public.telegram_messages_raw;

-- Validate forwards are not creating assignments
SELECT 
  COUNT(DISTINCT raw.id) as forward_messages,
  COUNT(DISTINCT ext.id) as extraction_jobs,
  COUNT(DISTINCT asg.id) as assignments_created
FROM public.telegram_messages_raw raw
LEFT JOIN public.telegram_extractions ext ON ext.raw_id = raw.id
LEFT JOIN public.assignments asg ON asg.message_id = raw.message_id
WHERE raw.is_forward = true;
-- Expected: forward_messages > 0, extraction_jobs >= 0, assignments_created = 0
```

---

## 8. Conclusion

TutorDex provides comprehensive tracking of all three message types with distinct processing behaviors optimized for the assignment aggregation use case:

| Aspect | Edits | Forwards | Replies |
|--------|-------|----------|---------|
| **Tracked in DB** | ✅ Full | ✅ Full | ✅ Full |
| **Extracted** | ✅ Yes (re-extracted) | ❌ No (filtered) | ✅ Yes |
| **Updates Assignments** | ✅ Yes (upserts) | ❌ No | ✅ Yes (new) |
| **Audit Trail** | ✅ edit_date + json | ✅ fwd_from + json | ✅ reply_to_msg_id + json |
| **Cost Optimization** | Re-extraction cost | Saved (no LLM) | Normal cost |

**Key Takeaways:**
1. All message types are comprehensively tracked for audit purposes
2. Processing behavior is intentionally different based on message type
3. Forward filtering prevents duplicate assignments across channels
4. Edit handling ensures assignments stay current with agency updates
5. Reply processing could be enhanced with parent context in the future

**Recommendations:**
1. ✅ Current implementation is solid for production use
2. 💡 Consider reply context enhancement for better extraction quality
3. 💡 Monitor forward filtering for false negatives (legitimate cross-posts being skipped)
4. 💡 Consider edit history versioning if audit requirements increase
5. 💡 Add metrics/alerting for edit frequency by channel (detect suspicious behavior)

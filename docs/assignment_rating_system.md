# Assignment Rating and Adaptive Threshold System

## Overview

The Assignment Rating System provides intelligent, personalized assignment distribution to tutors based on:
- **Quality scoring**: Combines matching accuracy, distance convenience, and pay rate attractiveness
- **Adaptive thresholds**: Each tutor receives assignments tailored to their desired volume
- **Historical learning**: System learns from past assignments to improve recommendations over time

This replaces the previous fixed threshold system (`MATCH_MIN_SCORE=3`) with a dynamic, tutor-specific approach.

## Key Benefits

1. **Reduces spam**: Tutors no longer receive every marginally-matching assignment
2. **Prioritizes quality**: Nearby, high-paying assignments are prioritized
3. **Respects preferences**: Each tutor can set their desired assignment volume
4. **Adapts automatically**: System adjusts thresholds based on market supply
5. **Maintains flow**: Never blocks all assignments - just filters low-value ones

## How It Works

### 1. Assignment Rating Calculation

For each tutor-assignment pair, calculate a rating:

```
Rating = Base_Score + Distance_Score + Rate_Score
```

**Base Score** (0-8 points):
- Subject match: +3 points
- Level match: +2 points
- Assignment type match: +1 point
- Learning mode match: +1 point
- Tutor type match: +1 point

**Distance Score**:
- < 1km: +5.0 (very valuable)
- 1-3km: +3.0 (valuable)
- 3-5km: +1.0 (slight bonus)
- 5-10km: 0.0 (neutral)
- > 10km: -2.0 (penalty)
- Online/no location: 0.0 (neutral)

**Rate Score**:
- Assignment pays >20% above tutor's historical average: +0 to +3.0 bonus
- Assignment pays around tutor's average (±20-30%): 0.0 (neutral)
- Assignment pays >30% below tutor's average: -0 to -2.0 penalty

**Example Ratings:**
- Perfect nearby match with high pay: ~13-16 points
- Good match, moderate distance: ~7-9 points
- Weak match, far away, low pay: ~1-3 points

### 2. Adaptive Threshold Calculation

Each tutor has a personalized threshold calculated from their history:

```sql
SELECT calculate_tutor_rating_threshold(
  user_id := 123,
  desired_per_day := 10,  -- Tutor's preference
  lookback_days := 7      -- Past week of data
)
```

**Algorithm:**
1. Look at past 7 days of assignment ratings sent to this tutor
2. Calculate how many assignments would give ~10 per day (tutor's preference)
3. Set threshold at the rating that achieves this target

**Examples:**
- **New tutor**: Threshold = 0.0 (permissive, send everything to build history)
- **High-volume market**: Threshold = 8.5 (only send good matches)
- **Low-volume market**: Threshold = 3.0 (more permissive to hit daily target)
- **Tutor wants 20/day**: Lower threshold than someone wanting 5/day

### 3. Assignment Distribution Flow

```
New Assignment
    ↓
Match against all tutors (subject/level/etc)
    ↓
Calculate rating for each match
    ↓
For each tutor:
  - Get tutor's desired_assignments_per_day (default: 10)
  - Calculate adaptive threshold from past 7 days
  - If rating >= threshold: Send DM
  - If rating < threshold: Skip (not valuable enough)
    ↓
Record rating for sent assignments (builds history for future thresholds)
```

## Database Schema

### `user_preferences` Table

New column:
```sql
desired_assignments_per_day INTEGER DEFAULT 10
```

Controls how many assignments per day the tutor wants to receive. Higher values = lower threshold (more permissive), lower values = higher threshold (more selective).

### `tutor_assignment_ratings` Table

Tracks every assignment sent to each tutor:

```sql
CREATE TABLE tutor_assignment_ratings (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  assignment_id BIGINT NOT NULL REFERENCES assignments(id),
  rating_score DOUBLE PRECISION NOT NULL,  -- Overall rating
  distance_km DOUBLE PRECISION,            -- Distance to assignment
  rate_min INTEGER,                        -- Assignment pay range
  rate_max INTEGER,
  match_score INTEGER NOT NULL,            -- Base matching score
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, assignment_id)
);
```

Used to:
- Calculate adaptive thresholds (past 7 days)
- Calculate tutor's average rate (past 30 days)
- Analytics and monitoring

### Database Functions

**`calculate_tutor_rating_threshold(user_id, desired_per_day, lookback_days)`**
- Returns the rating threshold for a tutor
- Based on historical ratings from past N days
- Aims to deliver approximately `desired_per_day` assignments

**`get_tutor_avg_rate(user_id, lookback_days)`**
- Returns tutor's average assignment rate from past N days
- Used to calculate rate bonuses/penalties
- Returns 0.0 if no history

## Configuration

### Environment Variables

**Core Settings:**
- `DM_USE_ADAPTIVE_THRESHOLD` (default: `true`)
  - Enable/disable adaptive filtering
  - Set to `false` to use old fixed-threshold behavior

- `DM_RATING_LOOKBACK_DAYS` (default: `7`)
  - Days of history for threshold calculation
  - Shorter = more reactive to recent changes
  - Longer = more stable thresholds

- `DM_RATING_AVG_RATE_LOOKBACK_DAYS` (default: `30`)
  - Days of history for calculating tutor's average rate
  - Used for rate bonus/penalty calculation

**Rating Algorithm Tuning:**
- `RATING_DISTANCE_VERY_CLOSE_KM` (default: `1.0`)
- `RATING_DISTANCE_CLOSE_KM` (default: `3.0`)
- `RATING_DISTANCE_MODERATE_KM` (default: `5.0`)
- `RATING_DISTANCE_FAR_KM` (default: `10.0`)

- `RATING_DISTANCE_VERY_CLOSE_BONUS` (default: `5.0`)
- `RATING_DISTANCE_CLOSE_BONUS` (default: `3.0`)
- `RATING_DISTANCE_MODERATE_BONUS` (default: `1.0`)
- `RATING_DISTANCE_FAR_PENALTY` (default: `-2.0`)

- `RATING_RATE_BONUS_THRESHOLD_PCT` (default: `20.0`)
- `RATING_RATE_BONUS_MAX` (default: `3.0`)
- `RATING_RATE_PENALTY_THRESHOLD_PCT` (default: `30.0`)
- `RATING_RATE_PENALTY_MAX` (default: `-2.0`)

**Legacy Settings (still supported):**
- `MATCH_MIN_SCORE` (default: `3`)
  - Minimum base matching score
  - Acts as a floor before rating calculation
  - Not affected by adaptive threshold

- `DM_MAX_RECIPIENTS` (default: `50`)
  - Hard cap on DMs per assignment
  - Applied after adaptive filtering

## Migration Guide

### 1. Apply Database Migration

```bash
psql $DATABASE_URL < TutorDexAggregator/supabase\ sqls/2026-01-09_assignment_ratings.sql
```

This creates:
- `tutor_assignment_ratings` table
- `calculate_tutor_rating_threshold()` function
- `get_tutor_avg_rate()` function
- Adds `desired_assignments_per_day` to `user_preferences`

### 2. Deploy Code Changes

The system is backward compatible:
- If migration not applied, falls back to old behavior
- Existing tutors default to 10 assignments/day
- Rating calculation gracefully handles missing data

### 3. Verify Deployment

Check logs for:
```
dm_adaptive_filter initial_matches=50 filtered_out=25 remaining=25
```

This indicates the adaptive threshold is working.

### 4. Monitor Performance

**Key metrics:**
- `initial_matched`: Tutors matching before filtering
- `matched`: Tutors after adaptive threshold
- `sent`: Actually sent DMs
- `filtered_out`: How many tutors were filtered

**What to watch:**
- If `filtered_out` is consistently 0: Thresholds may be too low
- If `filtered_out` equals `initial_matched`: Thresholds may be too high
- Typical: 20-40% filtered out in mature markets

## Tuning Recommendations

### If tutors complain about too many assignments:

1. Check their `desired_assignments_per_day` setting (should be lower)
2. Verify rating history is building up (check `tutor_assignment_ratings` table)
3. Consider raising distance penalties for their area

### If tutors complain about too few assignments:

1. Check their `desired_assignments_per_day` setting (should be higher)
2. Verify enough assignments exist in their subject/level
3. Check if threshold is too high (new tutors should have threshold=0)
4. Consider the market - low supply means fewer high-quality matches

### If system is too reactive:

- Increase `DM_RATING_LOOKBACK_DAYS` (e.g., 14 instead of 7)
- This smooths out day-to-day variations

### If system is too sluggish:

- Decrease `DM_RATING_LOOKBACK_DAYS` (e.g., 3-5 instead of 7)
- This makes thresholds more responsive to recent changes

## API Changes

### `GET /me/tutor`

Response now includes:
```json
{
  "desired_assignments_per_day": 10
}
```

### `PUT /me/tutor`

Accepts new field:
```json
{
  "desired_assignments_per_day": 15
}
```

### `POST /match/payload`

Response now includes for each match:
```json
{
  "rating": 8.5,
  "rate_min": 50,
  "rate_max": 70
}
```

## Troubleshooting

### No assignments being sent after migration

**Symptoms:** All matches filtered out, `remaining=0`

**Causes:**
- Database migration not applied
- Supabase connection issues
- Rating calculation failing

**Fix:**
```bash
# Check if migration applied
psql $DATABASE_URL -c "SELECT * FROM tutor_assignment_ratings LIMIT 1;"

# Temporarily disable adaptive threshold
export DM_USE_ADAPTIVE_THRESHOLD=false

# Check logs for errors
docker compose logs backend | grep -i "threshold\|rating"
```

### Threshold seems stuck at 0

**Symptoms:** All tutors have threshold=0.0, nothing filtered

**Causes:**
- No rating history yet (new deployment)
- Database function not working

**Fix:**
- Wait for history to build (24-48 hours)
- Check function: `SELECT calculate_tutor_rating_threshold(1, 10, 7);`
- Verify ratings are being recorded: `SELECT count(*) FROM tutor_assignment_ratings;`

### Ratings seem incorrect

**Symptoms:** Very high or very low ratings for seemingly normal assignments

**Causes:**
- Distance calculation issue
- Rate comparison baseline wrong
- Misconfigured bonus/penalty values

**Fix:**
```python
# Test rating calculation
from TutorDexBackend.assignment_rating import get_rating_components

components = get_rating_components(
    base_score=5,
    distance_km=2.0,
    assignment_rate_min=60,
    tutor_avg_rate=50.0,
)
print(components)
```

## Testing

Run the test suite:
```bash
python -m unittest tests.test_assignment_rating -v
```

All tests should pass. The tests cover:
- Distance scoring tiers
- Rate bonus/penalty calculation
- Combined rating calculation
- Component breakdown

## Future Enhancements

1. **Frontend UI**: Add slider in user profile for `desired_assignments_per_day`
2. **Time-based preferences**: Allow tutors to set different volumes for weekdays vs weekends
3. **Subject-specific preferences**: Different thresholds for different subjects
4. **ML-based rating**: Train model on tutor acceptance/rejection patterns
5. **A/B testing**: Compare adaptive vs fixed thresholds
6. **Dashboard**: Show tutors their rating distribution and threshold over time

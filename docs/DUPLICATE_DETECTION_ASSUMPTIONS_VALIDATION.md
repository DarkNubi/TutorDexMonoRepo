# Duplicate Detection - Assumptions Validation

## Overview

This document lists all assumptions made in the duplicate detection design and provides SQL queries to validate them against the production database. Run these queries and provide the results to ensure the implementation is production-ready and accurate.

---

## Assumptions Made

### 1. Assignment Code Assumptions

**Assumption 1.1**: Assignment codes exist for most assignments  
**Assumption 1.2**: Assignment codes can be the same across different agencies (shared assignments)  
**Assumption 1.3**: Assignment codes can be different for the same assignment across agencies (agency-specific codes)  
**Assumption 1.4**: Some agencies use predictable code formats (e.g., "D2388", "TUT-123")  

**SQL Queries to Validate**:

```sql
-- Query 1.1: How many assignments have assignment codes vs don't?
SELECT 
    COUNT(*) FILTER (WHERE assignment_code IS NOT NULL AND assignment_code != '') as with_code,
    COUNT(*) FILTER (WHERE assignment_code IS NULL OR assignment_code = '') as without_code,
    ROUND(100.0 * COUNT(*) FILTER (WHERE assignment_code IS NOT NULL AND assignment_code != '') / COUNT(*), 2) as pct_with_code
FROM public.assignments
WHERE status = 'open';

-- Query 1.2: Check if same assignment codes appear across multiple agencies
SELECT 
    assignment_code,
    COUNT(DISTINCT agency_id) as num_agencies,
    COUNT(*) as num_assignments,
    array_agg(DISTINCT agency_name ORDER BY agency_name) as agencies
FROM public.assignments
WHERE assignment_code IS NOT NULL 
    AND assignment_code != ''
    AND status = 'open'
GROUP BY assignment_code
HAVING COUNT(DISTINCT agency_id) > 1
ORDER BY num_agencies DESC, num_assignments DESC
LIMIT 20;

-- Query 1.3: Check common assignment code patterns by agency
SELECT 
    agency_name,
    COUNT(*) as total_assignments,
    COUNT(DISTINCT assignment_code) as unique_codes,
    array_agg(DISTINCT substring(assignment_code from '^[A-Za-z]+') ORDER BY substring(assignment_code from '^[A-Za-z]+')) as code_prefixes
FROM public.assignments
WHERE assignment_code IS NOT NULL 
    AND assignment_code != ''
    AND status = 'open'
GROUP BY agency_name
ORDER BY total_assignments DESC
LIMIT 10;

-- Query 1.4: Sample assignment codes by agency to identify patterns
SELECT 
    agency_name,
    array_agg(assignment_code ORDER BY created_at DESC) as sample_codes
FROM (
    SELECT DISTINCT ON (agency_name, assignment_code)
        agency_name,
        assignment_code,
        created_at
    FROM public.assignments
    WHERE assignment_code IS NOT NULL 
        AND assignment_code != ''
        AND status = 'open'
    ORDER BY agency_name, assignment_code, created_at DESC
) sub
GROUP BY agency_name
LIMIT 10;
```

---

### 2. Postal Code Assumptions

**Assumption 2.1**: Most assignments have postal codes (either exact or estimated)  
**Assumption 2.2**: Postal codes are 6-digit Singapore format  
**Assumption 2.3**: First 2 digits represent the district  
**Assumption 2.4**: Postal codes can have OCR/parsing errors (±1-2 digits)  
**Assumption 2.5**: Same postal code across agencies indicates same location  

**SQL Queries to Validate**:

```sql
-- Query 2.1: How many assignments have postal codes?
SELECT 
    COUNT(*) FILTER (WHERE (postal_code IS NOT NULL AND array_length(postal_code, 1) > 0) 
                        OR (postal_code_estimated IS NOT NULL AND array_length(postal_code_estimated, 1) > 0)) as with_postal,
    COUNT(*) FILTER (WHERE (postal_code IS NULL OR array_length(postal_code, 1) = 0) 
                        AND (postal_code_estimated IS NULL OR array_length(postal_code_estimated, 1) = 0)) as without_postal,
    ROUND(100.0 * COUNT(*) FILTER (WHERE (postal_code IS NOT NULL AND array_length(postal_code, 1) > 0) 
                        OR (postal_code_estimated IS NOT NULL AND array_length(postal_code_estimated, 1) > 0)) / COUNT(*), 2) as pct_with_postal
FROM public.assignments
WHERE status = 'open';

-- Query 2.2: Check postal code formats and lengths
SELECT 
    CASE 
        WHEN length(postal) = 6 AND postal ~ '^\d{6}$' THEN 'valid_6_digit'
        WHEN length(postal) < 6 AND postal ~ '^\d+$' THEN 'too_short'
        WHEN length(postal) > 6 AND postal ~ '^\d+$' THEN 'too_long'
        ELSE 'invalid_format'
    END as format_type,
    COUNT(*) as count,
    array_agg(postal ORDER BY random()) FILTER (WHERE random() < 0.01) as samples
FROM (
    SELECT unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal
    FROM public.assignments
    WHERE status = 'open'
) sub
GROUP BY format_type
ORDER BY count DESC;

-- Query 2.3: Check district distribution (first 2 digits)
SELECT 
    substring(postal from 1 for 2) as district,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM (
    SELECT unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal
    FROM public.assignments
    WHERE status = 'open'
) sub
WHERE postal ~ '^\d{6}$'
GROUP BY district
ORDER BY count DESC
LIMIT 20;

-- Query 2.4: Check if same postal codes appear across multiple agencies
SELECT 
    postal,
    COUNT(DISTINCT agency_id) as num_agencies,
    COUNT(*) as num_assignments,
    array_agg(DISTINCT agency_name ORDER BY agency_name) as agencies
FROM (
    SELECT 
        unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal,
        agency_id,
        agency_name
    FROM public.assignments
    WHERE status = 'open'
) sub
WHERE postal ~ '^\d{6}$'
GROUP BY postal
HAVING COUNT(DISTINCT agency_id) > 1
ORDER BY num_agencies DESC, num_assignments DESC
LIMIT 20;
```

---

### 2.5 Address Assumptions (ADDITIONAL VALIDATION RECOMMENDED)

**Assumption 2.5.1**: Address field may provide additional location confidence  
**Assumption 2.5.2**: Addresses might have format variations (e.g., "Blk 123" vs "Block 123")  
**Assumption 2.5.3**: Address matching would require fuzzy string comparison  
**Assumption 2.5.4**: Postal code is more reliable than address for duplicate detection  

**SQL Queries to Validate**:

```sql
-- Query 2.5.1: Address coverage
SELECT 
    COUNT(*) FILTER (WHERE address IS NOT NULL AND array_length(address, 1) > 0) as with_address,
    COUNT(*) FILTER (WHERE address IS NULL OR array_length(address, 1) = 0) as without_address,
    ROUND(100.0 * COUNT(*) FILTER (WHERE address IS NOT NULL AND array_length(address, 1) > 0) / COUNT(*), 2) as pct_with_address
FROM public.assignments
WHERE status = 'open';

-- Query 2.5.2: Sample addresses to understand format
SELECT 
    unnest(address) as address_sample,
    unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal,
    COUNT(*) as count
FROM public.assignments
WHERE status = 'open'
    AND address IS NOT NULL
    AND array_length(address, 1) > 0
GROUP BY address_sample, postal
ORDER BY count DESC
LIMIT 30;

-- Query 2.5.3: Check address consistency for same postal code
SELECT 
    postal,
    COUNT(DISTINCT address_text) as num_address_variants,
    array_agg(DISTINCT address_text ORDER BY address_text) as address_variants
FROM (
    SELECT 
        unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal,
        unnest(address) as address_text
    FROM public.assignments
    WHERE status = 'open'
        AND address IS NOT NULL
        AND array_length(address, 1) > 0
) sub
WHERE postal ~ '^\d{6}$'
GROUP BY postal
HAVING COUNT(DISTINCT address_text) > 1
ORDER BY num_address_variants DESC
LIMIT 20;

-- Query 2.5.4: Compare assignments with same address but different postal codes
SELECT 
    address_text,
    COUNT(DISTINCT postal) as num_postal_codes,
    array_agg(DISTINCT postal ORDER BY postal) as postal_codes,
    COUNT(*) as num_assignments
FROM (
    SELECT 
        unnest(address) as address_text,
        unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal
    FROM public.assignments
    WHERE status = 'open'
        AND address IS NOT NULL
        AND array_length(address, 1) > 0
) sub
GROUP BY address_text
HAVING COUNT(DISTINCT postal) > 1
ORDER BY num_postal_codes DESC, num_assignments DESC
LIMIT 20;
```

---

### 3. Subject and Level Assumptions

**Assumption 3.1**: Most assignments have subjects extracted  
**Assumption 3.2**: Subjects are stored in `subjects_canonical` or fall back to `signals_subjects`  
**Assumption 3.3**: Levels are stored in `signals_levels` and `signals_specific_student_levels`  
**Assumption 3.4**: Similar subject/level combinations across agencies indicate duplicates  

**SQL Queries to Validate**:

```sql
-- Query 3.1: Subject extraction coverage
SELECT 
    COUNT(*) FILTER (WHERE (subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0) 
                        OR (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0)) as with_subjects,
    COUNT(*) FILTER (WHERE (subjects_canonical IS NULL OR array_length(subjects_canonical, 1) = 0) 
                        AND (signals_subjects IS NULL OR array_length(signals_subjects, 1) = 0)) as without_subjects,
    ROUND(100.0 * COUNT(*) FILTER (WHERE (subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0) 
                        OR (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0)) / COUNT(*), 2) as pct_with_subjects
FROM public.assignments
WHERE status = 'open';

-- Query 3.2: Compare subjects_canonical vs signals_subjects usage
SELECT 
    COUNT(*) FILTER (WHERE subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0) as has_canonical,
    COUNT(*) FILTER (WHERE signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0) as has_signals,
    COUNT(*) FILTER (WHERE (subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0)
                        AND (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0)) as has_both,
    COUNT(*) FILTER (WHERE (subjects_canonical IS NULL OR array_length(subjects_canonical, 1) = 0)
                        AND (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0)) as signals_only
FROM public.assignments
WHERE status = 'open';

-- Query 3.3: Level extraction coverage
SELECT 
    COUNT(*) FILTER (WHERE (signals_levels IS NOT NULL AND array_length(signals_levels, 1) > 0) 
                        OR (signals_specific_student_levels IS NOT NULL AND array_length(signals_specific_student_levels, 1) > 0)) as with_levels,
    COUNT(*) FILTER (WHERE (signals_levels IS NULL OR array_length(signals_levels, 1) = 0) 
                        AND (signals_specific_student_levels IS NULL OR array_length(signals_specific_student_levels, 1) = 0)) as without_levels,
    ROUND(100.0 * COUNT(*) FILTER (WHERE (signals_levels IS NOT NULL AND array_length(signals_levels, 1) > 0) 
                        OR (signals_specific_student_levels IS NOT NULL AND array_length(signals_specific_student_levels, 1) > 0)) / COUNT(*), 2) as pct_with_levels
FROM public.assignments
WHERE status = 'open';

-- Query 3.4: Most common subject+level combinations
SELECT 
    COALESCE(subjects_canonical, signals_subjects, ARRAY[]::text[]) as subjects,
    COALESCE(signals_levels, ARRAY[]::text[]) as levels,
    COUNT(*) as count
FROM public.assignments
WHERE status = 'open'
    AND ((subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0)
        OR (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0))
GROUP BY subjects, levels
ORDER BY count DESC
LIMIT 20;
```

---

### 4. Rate Assumptions

**Assumption 4.1**: Rate information is optional (many assignments don't have rates)  
**Assumption 4.2**: Rates are stored as `rate_min` and `rate_max` integers  
**Assumption 4.3**: Rate ranges can overlap between duplicates but may vary slightly  
**Assumption 4.4**: Missing rates should not prevent duplicate detection  

**SQL Queries to Validate**:

```sql
-- Query 4.1: Rate coverage
SELECT 
    COUNT(*) FILTER (WHERE rate_min IS NOT NULL OR rate_max IS NOT NULL OR rate_raw_text IS NOT NULL) as with_rate,
    COUNT(*) FILTER (WHERE rate_min IS NULL AND rate_max IS NULL AND rate_raw_text IS NULL) as without_rate,
    ROUND(100.0 * COUNT(*) FILTER (WHERE rate_min IS NOT NULL OR rate_max IS NOT NULL OR rate_raw_text IS NOT NULL) / COUNT(*), 2) as pct_with_rate
FROM public.assignments
WHERE status = 'open';

-- Query 4.2: Rate range distribution
SELECT 
    rate_min,
    rate_max,
    COUNT(*) as count
FROM public.assignments
WHERE status = 'open'
    AND rate_min IS NOT NULL
    AND rate_max IS NOT NULL
GROUP BY rate_min, rate_max
ORDER BY count DESC
LIMIT 20;

-- Query 4.3: Check if assignments with same postal have similar rates
SELECT 
    postal,
    COUNT(DISTINCT agency_name) as num_agencies,
    array_agg(DISTINCT agency_name ORDER BY agency_name) as agencies,
    MIN(rate_min) as min_rate_min,
    MAX(rate_max) as max_rate_max,
    array_agg(DISTINCT rate_min ORDER BY rate_min) FILTER (WHERE rate_min IS NOT NULL) as rate_mins,
    array_agg(DISTINCT rate_max ORDER BY rate_max) FILTER (WHERE rate_max IS NOT NULL) as rate_maxs
FROM (
    SELECT 
        unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal,
        agency_name,
        rate_min,
        rate_max
    FROM public.assignments
    WHERE status = 'open'
) sub
WHERE postal ~ '^\d{6}$'
GROUP BY postal
HAVING COUNT(DISTINCT agency_name) > 1
ORDER BY num_agencies DESC
LIMIT 10;
```

---

### 5. Temporal Proximity Assumptions

**Assumption 5.1**: Duplicates are typically posted within 24-48 hours of each other  
**Assumption 5.2**: `published_at` timestamp is reliable and populated  
**Assumption 5.3**: Time window of 7 days is sufficient to catch most duplicates  

**SQL Queries to Validate**:

```sql
-- Query 5.1: Check published_at coverage
SELECT 
    COUNT(*) FILTER (WHERE published_at IS NOT NULL) as with_published_at,
    COUNT(*) FILTER (WHERE published_at IS NULL) as without_published_at,
    ROUND(100.0 * COUNT(*) FILTER (WHERE published_at IS NOT NULL) / COUNT(*), 2) as pct_with_published_at
FROM public.assignments
WHERE status = 'open';

-- Query 5.2: Check age distribution of open assignments
SELECT 
    CASE 
        WHEN age_days < 1 THEN '< 1 day'
        WHEN age_days < 2 THEN '1-2 days'
        WHEN age_days < 3 THEN '2-3 days'
        WHEN age_days < 7 THEN '3-7 days'
        WHEN age_days < 14 THEN '7-14 days'
        ELSE '14+ days'
    END as age_bucket,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM (
    SELECT 
        EXTRACT(EPOCH FROM (NOW() - published_at)) / 86400 as age_days
    FROM public.assignments
    WHERE status = 'open'
        AND published_at IS NOT NULL
) sub
GROUP BY age_bucket
ORDER BY 
    CASE age_bucket
        WHEN '< 1 day' THEN 1
        WHEN '1-2 days' THEN 2
        WHEN '2-3 days' THEN 3
        WHEN '3-7 days' THEN 4
        WHEN '7-14 days' THEN 5
        ELSE 6
    END;

-- Query 5.3: Check if assignments with same postal are posted close together
WITH potential_duplicates AS (
    SELECT 
        a1.id as id1,
        a2.id as id2,
        a1.agency_name as agency1,
        a2.agency_name as agency2,
        unnest(COALESCE(a1.postal_code, a1.postal_code_estimated, ARRAY[]::text[])) as postal,
        a1.published_at as time1,
        a2.published_at as time2,
        ABS(EXTRACT(EPOCH FROM (a1.published_at - a2.published_at))) / 3600 as hours_apart
    FROM public.assignments a1
    JOIN public.assignments a2 ON 
        a1.id < a2.id
        AND a1.agency_id != a2.agency_id
        AND a1.status = 'open'
        AND a2.status = 'open'
        AND unnest(COALESCE(a1.postal_code, a1.postal_code_estimated, ARRAY[]::text[])) = 
            unnest(COALESCE(a2.postal_code, a2.postal_code_estimated, ARRAY[]::text[]))
    WHERE a1.published_at IS NOT NULL
        AND a2.published_at IS NOT NULL
    LIMIT 100
)
SELECT 
    CASE 
        WHEN hours_apart < 1 THEN '< 1 hour'
        WHEN hours_apart < 6 THEN '1-6 hours'
        WHEN hours_apart < 24 THEN '6-24 hours'
        WHEN hours_apart < 48 THEN '24-48 hours'
        WHEN hours_apart < 168 THEN '2-7 days'
        ELSE '7+ days'
    END as time_gap,
    COUNT(*) as count
FROM potential_duplicates
GROUP BY time_gap
ORDER BY 
    CASE time_gap
        WHEN '< 1 hour' THEN 1
        WHEN '1-6 hours' THEN 2
        WHEN '6-24 hours' THEN 3
        WHEN '24-48 hours' THEN 4
        WHEN '2-7 days' THEN 5
        ELSE 6
    END;
```

---

### 6. Agency and External ID Assumptions

**Assumption 6.1**: Different agencies have different `agency_id` values  
**Assumption 6.2**: Same agency doesn't duplicate its own assignments  
**Assumption 6.3**: `external_id` is unique within an agency but may overlap across agencies  
**Assumption 6.4**: Agency names are consistent and don't change  

**SQL Queries to Validate**:

```sql
-- Query 6.1: Count agencies and assignments per agency
SELECT 
    agency_name,
    agency_id,
    COUNT(*) as num_assignments
FROM public.assignments
WHERE status = 'open'
GROUP BY agency_name, agency_id
ORDER BY num_assignments DESC;

-- Query 6.2: Check for duplicate external_id within same agency
SELECT 
    agency_name,
    external_id,
    COUNT(*) as count
FROM public.assignments
WHERE status = 'open'
    AND external_id IS NOT NULL
GROUP BY agency_name, external_id
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 20;

-- Query 6.3: Check if external_id is shared across agencies
SELECT 
    external_id,
    COUNT(DISTINCT agency_id) as num_agencies,
    COUNT(*) as num_assignments,
    array_agg(DISTINCT agency_name ORDER BY agency_name) as agencies
FROM public.assignments
WHERE status = 'open'
    AND external_id IS NOT NULL
GROUP BY external_id
HAVING COUNT(DISTINCT agency_id) > 1
ORDER BY num_agencies DESC, num_assignments DESC
LIMIT 20;

-- Query 6.4: Check for agency name variations
SELECT 
    agency_name,
    COUNT(DISTINCT agency_id) as num_ids,
    array_agg(DISTINCT agency_id ORDER BY agency_id) as agency_ids
FROM public.assignments
GROUP BY agency_name
HAVING COUNT(DISTINCT agency_id) > 1
ORDER BY num_ids DESC;
```

---

### 7. Time Availability Assumptions

**Assumption 7.1**: Time availability is optional and may be missing  
**Assumption 7.2**: Time availability is stored as JSONB in `time_availability_explicit` or `time_availability_estimated`  
**Assumption 7.3**: Time availability overlap is a weak signal (low weight)  

**SQL Queries to Validate**:

```sql
-- Query 7.1: Time availability coverage
SELECT 
    COUNT(*) FILTER (WHERE time_availability_explicit IS NOT NULL OR time_availability_estimated IS NOT NULL OR time_availability_note IS NOT NULL) as with_time,
    COUNT(*) FILTER (WHERE time_availability_explicit IS NULL AND time_availability_estimated IS NULL AND time_availability_note IS NULL) as without_time,
    ROUND(100.0 * COUNT(*) FILTER (WHERE time_availability_explicit IS NOT NULL OR time_availability_estimated IS NOT NULL OR time_availability_note IS NOT NULL) / COUNT(*), 2) as pct_with_time
FROM public.assignments
WHERE status = 'open';

-- Query 7.2: Sample time availability structures
SELECT 
    time_availability_explicit,
    time_availability_estimated,
    time_availability_note
FROM public.assignments
WHERE status = 'open'
    AND (time_availability_explicit IS NOT NULL OR time_availability_estimated IS NOT NULL)
LIMIT 10;
```

---

### 8. Overall Data Quality Assumptions

**Assumption 8.1**: Most assignments have enough data for duplicate detection (postal + subjects/levels)  
**Assumption 8.2**: Parse quality score correlates with data completeness  
**Assumption 8.3**: Open assignments are the primary target for duplicate detection  

**SQL Queries to Validate**:

```sql
-- Query 8.1: Check data completeness for duplicate detection signals
SELECT 
    COUNT(*) FILTER (WHERE 
        ((postal_code IS NOT NULL AND array_length(postal_code, 1) > 0) OR (postal_code_estimated IS NOT NULL AND array_length(postal_code_estimated, 1) > 0))
        AND ((subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0) OR (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0))
    ) as complete_for_detection,
    COUNT(*) as total,
    ROUND(100.0 * COUNT(*) FILTER (WHERE 
        ((postal_code IS NOT NULL AND array_length(postal_code, 1) > 0) OR (postal_code_estimated IS NOT NULL AND array_length(postal_code_estimated, 1) > 0))
        AND ((subjects_canonical IS NOT NULL AND array_length(subjects_canonical, 1) > 0) OR (signals_subjects IS NOT NULL AND array_length(signals_subjects, 1) > 0))
    ) / COUNT(*), 2) as pct_complete
FROM public.assignments
WHERE status = 'open';

-- Query 8.2: Parse quality score distribution
SELECT 
    CASE 
        WHEN parse_quality_score >= 12 THEN 'high (12+)'
        WHEN parse_quality_score >= 8 THEN 'medium (8-11)'
        WHEN parse_quality_score >= 4 THEN 'low (4-7)'
        ELSE 'very low (0-3)'
    END as quality_tier,
    COUNT(*) as count,
    ROUND(AVG(parse_quality_score), 2) as avg_score,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM public.assignments
WHERE status = 'open'
GROUP BY quality_tier
ORDER BY avg_score DESC;

-- Query 8.3: Assignment status distribution
SELECT 
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM public.assignments
GROUP BY status
ORDER BY count DESC;
```

---

### 9. Potential False Positive Scenarios

**Assumption 9.1**: Two assignments in same location with same subject are likely duplicates  
**Assumption 9.2**: Small differences in rates shouldn't prevent duplicate detection  
**Assumption 9.3**: Different assignment codes don't necessarily mean different assignments  

**SQL Queries to Check Edge Cases**:

```sql
-- Query 9.1: Find potential false positives (same postal + subject but different details)
WITH postal_subject_groups AS (
    SELECT 
        unnest(COALESCE(postal_code, postal_code_estimated, ARRAY[]::text[])) as postal,
        COALESCE(subjects_canonical, signals_subjects, ARRAY[]::text[]) as subjects,
        COUNT(*) as count,
        array_agg(DISTINCT agency_name ORDER BY agency_name) as agencies,
        array_agg(DISTINCT assignment_code ORDER BY assignment_code) FILTER (WHERE assignment_code IS NOT NULL) as codes
    FROM public.assignments
    WHERE status = 'open'
    GROUP BY postal, subjects
    HAVING COUNT(*) > 1 AND COUNT(DISTINCT agency_id) > 1
)
SELECT 
    postal,
    subjects,
    count,
    agencies,
    codes
FROM postal_subject_groups
ORDER BY count DESC
LIMIT 20;

-- Query 9.2: Check assignments that look similar but have different codes
SELECT 
    a1.id as id1,
    a2.id as id2,
    a1.agency_name as agency1,
    a2.agency_name as agency2,
    a1.assignment_code as code1,
    a2.assignment_code as code2,
    unnest(COALESCE(a1.postal_code, a1.postal_code_estimated, ARRAY[]::text[])) as postal,
    a1.subjects_canonical as subjects1,
    a2.subjects_canonical as subjects2,
    a1.rate_min as rate1_min,
    a1.rate_max as rate1_max,
    a2.rate_min as rate2_min,
    a2.rate_max as rate2_max
FROM public.assignments a1
JOIN public.assignments a2 ON 
    a1.id < a2.id
    AND a1.agency_id != a2.agency_id
    AND a1.status = 'open'
    AND a2.status = 'open'
    AND unnest(COALESCE(a1.postal_code, a1.postal_code_estimated, ARRAY[]::text[])) = 
        unnest(COALESCE(a2.postal_code, a2.postal_code_estimated, ARRAY[]::text[]))
    AND a1.subjects_canonical = a2.subjects_canonical
    AND a1.assignment_code IS NOT NULL
    AND a2.assignment_code IS NOT NULL
    AND a1.assignment_code != a2.assignment_code
WHERE a1.subjects_canonical IS NOT NULL
    AND array_length(a1.subjects_canonical, 1) > 0
LIMIT 10;
```

---

## Summary of Key Assumptions to Validate

### Critical Assumptions (Must Validate)
1. **Assignment codes**: Are they reliable? Shared across agencies?
2. **Postal codes**: Coverage? Format consistency? District accuracy?
3. **Subjects**: Extraction success rate? Canonical vs signals usage?
4. **Agency IDs**: Uniqueness and consistency?
5. **Data completeness**: What % of assignments have enough signals for detection?

### Important Assumptions (Should Validate)
6. **Temporal patterns**: How quickly do duplicates appear?
7. **Rate ranges**: How consistent are rates for duplicates?
8. **Parse quality**: Does it correlate with detection suitability?

### Nice to Validate
9. **Time availability**: Coverage and structure
10. **False positive scenarios**: What edge cases exist?

### Additional Validation (RECOMMENDED)
11. **Address field**: Coverage? Format consistency? Would it improve detection accuracy?
    - Run queries 2.5.1 through 2.5.4 to assess if address should be added as supplementary signal
    - Consider as 5-10 point signal if coverage >70% and formats are relatively consistent

---

## How to Use This Document

1. **Run each SQL query** against your production Supabase database
2. **Copy the results** into a response (tables, counts, samples)
3. **Review the results** to identify:
   - Which assumptions are valid
   - Which assumptions need adjustment
   - What edge cases exist
   - What weight adjustments are needed
4. **Update the detection algorithm** based on findings

For example, if Query 1.1 shows only 30% of assignments have codes, we should reduce the weight of assignment_code matching from 40 to 20-25 points.

---

## Expected Actions Based on Results

### If assignment code coverage is low (<50%):
- Reduce `weight_assignment_code` from 40 to 20-25
- Make postal code + subjects the primary signals
- Don't rely on codes for initial detection

### If postal codes are unreliable:
- Increase fuzzy matching tolerance
- Add validation for 6-digit format
- Use postal_code_estimated as primary source

### If subjects_canonical is not widely populated:
- Always fall back to signals_subjects
- Add null handling in similarity calculation
- Consider waiting for taxonomy migration

### If temporal patterns show duplicates appear over 7+ days:
- Increase time window from 7 to 14 days
- Reduce temporal proximity weight
- Add separate detection pass for older assignments

---

## Next Steps

Once you provide the query results, I will:
1. Adjust signal weights based on data quality
2. Refine the detection algorithm for edge cases
3. Update threshold values if needed
4. Add specific handling for agency partnership patterns
5. Create a tuned, production-ready implementation

Please run these queries and share the results!

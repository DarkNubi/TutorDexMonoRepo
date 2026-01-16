# Duplicate Detection Admin Guide

## Overview

This guide provides SQL queries and procedures for manually managing duplicate assignment groups and monitoring system performance.

## Manual Group Management

### View All Duplicate Groups

```sql
-- View all duplicate groups with summary info
SELECT 
    id,
    primary_assignment_id,
    member_count,
    avg_confidence_score,
    status,
    created_at,
    updated_at
FROM assignment_duplicate_groups
ORDER BY created_at DESC
LIMIT 50;
```

### View Assignments in a Specific Group

```sql
-- Replace <GROUP_ID> with actual group ID
SELECT 
    a.id,
    a.agency_name,
    a.assignment_code,
    a.is_primary_in_group,
    a.duplicate_confidence_score,
    a.published_at,
    a.postal_code,
    a.subjects_canonical,
    a.signals_levels
FROM assignments a
WHERE a.duplicate_group_id = <GROUP_ID>
ORDER BY a.is_primary_in_group DESC, a.published_at ASC;
```

### Manually Add Assignment to Group

```sql
-- Add an assignment to an existing duplicate group
UPDATE assignments
SET 
    duplicate_group_id = <GROUP_ID>,
    is_primary_in_group = FALSE,
    duplicate_confidence_score = 85.0
WHERE id = <ASSIGNMENT_ID>;

-- Update group member count
UPDATE assignment_duplicate_groups
SET 
    member_count = member_count + 1,
    updated_at = NOW()
WHERE id = <GROUP_ID>;
```

### Remove Assignment from Group

```sql
-- Remove assignment from group
UPDATE assignments
SET 
    duplicate_group_id = NULL,
    is_primary_in_group = TRUE,
    duplicate_confidence_score = NULL
WHERE id = <ASSIGNMENT_ID>;

-- Update group member count
UPDATE assignment_duplicate_groups
SET 
    member_count = member_count - 1,
    updated_at = NOW()
WHERE id = <GROUP_ID>;
```

### Change Primary Assignment

```sql
-- First, make current primary non-primary
UPDATE assignments
SET is_primary_in_group = FALSE
WHERE duplicate_group_id = <GROUP_ID>
AND is_primary_in_group = TRUE;

-- Then, promote new assignment to primary
UPDATE assignments
SET is_primary_in_group = TRUE
WHERE id = <NEW_PRIMARY_ASSIGNMENT_ID>;

-- Update group primary reference
UPDATE assignment_duplicate_groups
SET 
    primary_assignment_id = <NEW_PRIMARY_ASSIGNMENT_ID>,
    updated_at = NOW()
WHERE id = <GROUP_ID>;
```

### Delete Empty Groups

```sql
-- Find and delete groups with no members
DELETE FROM assignment_duplicate_groups
WHERE member_count = 0
OR id NOT IN (
    SELECT DISTINCT duplicate_group_id 
    FROM assignments 
    WHERE duplicate_group_id IS NOT NULL
);
```

### Dissolve a Duplicate Group

```sql
-- Remove all assignments from group
UPDATE assignments
SET 
    duplicate_group_id = NULL,
    is_primary_in_group = TRUE,
    duplicate_confidence_score = NULL
WHERE duplicate_group_id = <GROUP_ID>;

-- Delete the group
DELETE FROM assignment_duplicate_groups
WHERE id = <GROUP_ID>;
```

## Analytics Queries

### Duplicate Statistics

```sql
-- Overall duplicate statistics
SELECT 
    COUNT(DISTINCT duplicate_group_id) as total_groups,
    COUNT(*) FILTER (WHERE duplicate_group_id IS NOT NULL) as total_duplicates,
    COUNT(*) FILTER (WHERE is_primary_in_group = TRUE) as total_primary,
    ROUND(AVG(duplicate_confidence_score), 2) as avg_confidence,
    ROUND(MIN(duplicate_confidence_score), 2) as min_confidence,
    ROUND(MAX(duplicate_confidence_score), 2) as max_confidence
FROM assignments
WHERE status = 'open';
```

### Group Size Distribution

```sql
-- Distribution of duplicate group sizes
SELECT 
    member_count,
    COUNT(*) as group_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM assignment_duplicate_groups
WHERE status = 'active'
GROUP BY member_count
ORDER BY member_count;
```

### Top Agency Pairs

```sql
-- Which agencies share the most assignments
SELECT 
    a1.agency_name as agency_1,
    a2.agency_name as agency_2,
    COUNT(*) as shared_assignments
FROM assignments a1
JOIN assignments a2 
    ON a1.duplicate_group_id = a2.duplicate_group_id
WHERE a1.agency_name < a2.agency_name
AND a1.status = 'open'
AND a2.status = 'open'
GROUP BY a1.agency_name, a2.agency_name
ORDER BY shared_assignments DESC
LIMIT 20;
```

### Confidence Score Distribution

```sql
-- Distribution of confidence scores
SELECT 
    CASE 
        WHEN duplicate_confidence_score >= 90 THEN 'High (90-100)'
        WHEN duplicate_confidence_score >= 70 THEN 'Medium (70-89)'
        WHEN duplicate_confidence_score >= 55 THEN 'Low (55-69)'
        ELSE 'Very Low (<55)'
    END as confidence_range,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM assignments
WHERE duplicate_group_id IS NOT NULL
AND status = 'open'
GROUP BY confidence_range
ORDER BY MIN(duplicate_confidence_score) DESC;
```

### Assignments Without Duplicates

```sql
-- Assignments that have no duplicates
SELECT 
    COUNT(*) FILTER (WHERE duplicate_group_id IS NULL) as unique_assignments,
    COUNT(*) FILTER (WHERE duplicate_group_id IS NOT NULL) as duplicate_assignments,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duplicate_group_id IS NULL) / COUNT(*), 2) as unique_percentage
FROM assignments
WHERE status = 'open';
```

### Recent Duplicate Groups

```sql
-- Recently created duplicate groups
SELECT 
    g.id,
    g.member_count,
    g.avg_confidence_score,
    g.created_at,
    STRING_AGG(a.agency_name, ', ' ORDER BY a.is_primary_in_group DESC) as agencies
FROM assignment_duplicate_groups g
JOIN assignments a ON a.duplicate_group_id = g.id
WHERE g.status = 'active'
GROUP BY g.id, g.member_count, g.avg_confidence_score, g.created_at
ORDER BY g.created_at DESC
LIMIT 20;
```

### Duplicate Detection Performance

```sql
-- Average time between assignment creation and duplicate detection
SELECT 
    AVG(EXTRACT(EPOCH FROM (g.created_at - a.created_at))) as avg_detection_seconds,
    MIN(EXTRACT(EPOCH FROM (g.created_at - a.created_at))) as min_detection_seconds,
    MAX(EXTRACT(EPOCH FROM (g.created_at - a.created_at))) as max_detection_seconds
FROM assignments a
JOIN assignment_duplicate_groups g ON g.primary_assignment_id = a.id
WHERE g.created_at > NOW() - INTERVAL '7 days';
```

## Validation Queries

### Find Inconsistent Groups

```sql
-- Groups where member_count doesn't match actual members
SELECT 
    g.id,
    g.member_count as reported_count,
    COUNT(a.id) as actual_count
FROM assignment_duplicate_groups g
LEFT JOIN assignments a ON a.duplicate_group_id = g.id
GROUP BY g.id, g.member_count
HAVING g.member_count != COUNT(a.id);
```

### Find Groups Without Primary

```sql
-- Groups that have no primary assignment
SELECT 
    g.id,
    g.member_count,
    COUNT(a.id) FILTER (WHERE a.is_primary_in_group = TRUE) as primary_count
FROM assignment_duplicate_groups g
JOIN assignments a ON a.duplicate_group_id = g.id
GROUP BY g.id, g.member_count
HAVING COUNT(a.id) FILTER (WHERE a.is_primary_in_group = TRUE) = 0;
```

### Find Groups with Multiple Primaries

```sql
-- Groups that have more than one primary assignment (error condition)
SELECT 
    g.id,
    g.member_count,
    COUNT(a.id) FILTER (WHERE a.is_primary_in_group = TRUE) as primary_count
FROM assignment_duplicate_groups g
JOIN assignments a ON a.duplicate_group_id = g.id
GROUP BY g.id, g.member_count
HAVING COUNT(a.id) FILTER (WHERE a.is_primary_in_group = TRUE) > 1;
```

## Configuration Management

### View Current Configuration

```sql
SELECT 
    config_key,
    config_value,
    updated_at
FROM duplicate_detection_config
ORDER BY config_key;
```

### Update Detection Thresholds

```sql
UPDATE duplicate_detection_config
SET 
    config_value = '{"high_confidence": 90, "medium_confidence": 70, "low_confidence": 55}'::jsonb,
    updated_at = NOW()
WHERE config_key = 'thresholds';
```

### Update Signal Weights

```sql
UPDATE duplicate_detection_config
SET 
    config_value = '{"postal": 50, "subjects": 35, "levels": 25, "rate": 15, "temporal": 10, "assignment_code": 10, "time": 5}'::jsonb,
    updated_at = NOW()
WHERE config_key = 'weights';
```

### Update Time Window

```sql
UPDATE duplicate_detection_config
SET 
    config_value = '"14"'::jsonb,
    updated_at = NOW()
WHERE config_key = 'time_window_days';
```

## Troubleshooting

### Rerun Detection for Specific Assignment

```python
# In Python shell or script
from duplicate_detector import detect_duplicates_for_assignment
from supabase_env import get_supabase_client

client = get_supabase_client()
assignment_id = 12345

# Rerun detection
detect_duplicates_for_assignment(client, assignment_id)
```

### Manually Recompute Group Statistics

```sql
-- Recompute member count for a group
UPDATE assignment_duplicate_groups
SET 
    member_count = (
        SELECT COUNT(*) 
        FROM assignments 
        WHERE duplicate_group_id = assignment_duplicate_groups.id
    ),
    avg_confidence_score = (
        SELECT AVG(duplicate_confidence_score)
        FROM assignments
        WHERE duplicate_group_id = assignment_duplicate_groups.id
    ),
    updated_at = NOW()
WHERE id = <GROUP_ID>;
```

### Clean Up Orphaned Assignments

```sql
-- Find assignments pointing to non-existent groups
SELECT a.id, a.duplicate_group_id
FROM assignments a
LEFT JOIN assignment_duplicate_groups g ON g.id = a.duplicate_group_id
WHERE a.duplicate_group_id IS NOT NULL
AND g.id IS NULL;

-- Clean them up
UPDATE assignments a
SET 
    duplicate_group_id = NULL,
    is_primary_in_group = TRUE,
    duplicate_confidence_score = NULL
WHERE a.duplicate_group_id NOT IN (
    SELECT id FROM assignment_duplicate_groups
);
```

## Monitoring Checklist

Daily:
- [ ] Check duplicate detection rate (should be 20-40%)
- [ ] Review recent groups for false positives
- [ ] Check for groups without primaries
- [ ] Monitor detection performance (p95 < 500ms)

Weekly:
- [ ] Review top agency pairs
- [ ] Check confidence score distribution
- [ ] Validate group member counts
- [ ] Review any detection failures

Monthly:
- [ ] Analyze detection accuracy trends
- [ ] Review and adjust thresholds if needed
- [ ] Clean up orphaned records
- [ ] Update documentation with learnings

## Contact

For issues or questions about duplicate detection:
- Check logs: `docker-compose logs -f aggregator | grep duplicate`
- Review Grafana dashboard: http://localhost:3300/d/duplicate-detection
- Check Prometheus metrics: http://localhost:8000/metrics | grep duplicate

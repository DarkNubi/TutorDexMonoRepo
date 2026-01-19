"""
Business Metrics Updater for TutorDex.

Provides functions to update high-level business metrics for monitoring.
These metrics complement operational metrics with business KPIs.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def update_assignments_per_hour(supabase_client, metric_gauge) -> int:
    """
    Update the assignments_per_hour metric.

    Counts assignments created in the last hour.

    Args:
        supabase_client: Supabase client for querying
        metric_gauge: Prometheus Gauge to update

    Returns:
        Number of assignments in last hour
    """
    try:
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        response = supabase_client.rpc(
            "count_assignments_since",
            {"since_timestamp": one_hour_ago}
        )

        count = response if isinstance(response, int) else 0
        metric_gauge.set(count)

        logger.debug(f"assignments_per_hour={count}")
        return count

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_assignments_per_hour",
            extra={"module": __name__}
        )
        return 0


def update_tutors_with_active_dms(redis_client, metric_gauge) -> int:
    """
    Update the tutors_with_active_dms metric.

    Counts tutor profiles stored in Redis (active DM subscriptions).

    Args:
        redis_client: Redis client
        metric_gauge: Prometheus Gauge to update

    Returns:
        Number of tutors with profiles
    """
    try:
        # Count keys matching pattern tutordex:tutor:*
        pattern = "tutordex:tutor:*"
        keys = redis_client.keys(pattern)
        count = len(keys) if keys else 0

        metric_gauge.set(count)

        logger.debug(f"tutors_with_active_dms={count}")
        return count

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_active_dms",
            extra={"module": __name__}
        )
        return 0


def record_time_to_first_match(created_at: datetime, matched_at: datetime, metric_histogram):
    """
    Record time from assignment creation to first match.

    Args:
        created_at: When assignment was created
        matched_at: When first match occurred (DM sent)
        metric_histogram: Prometheus Histogram to observe
    """
    try:
        if created_at and matched_at:
            delta = (matched_at - created_at).total_seconds()
            if delta >= 0:  # Sanity check
                metric_histogram.observe(delta)
                logger.debug(f"time_to_first_match={delta:.0f}s")

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_time_to_match",
            extra={"module": __name__}
        )


def update_assignments_by_status(supabase_client, metric_gauge):
    """
    Update the assignments_by_status metric for all statuses.

    Args:
        supabase_client: Supabase client for querying
        metric_gauge: Prometheus Gauge with 'status' label
    """
    try:
        statuses = ["open", "closed", "hidden", "expired", "deleted", "pending"]

        for status in statuses:
            response = supabase_client.rpc(
                "count_assignments_by_status",
                {"status_filter": status}
            )

            count = response if isinstance(response, int) else 0
            metric_gauge.labels(status=status).set(count)
            logger.debug(f"assignments_{status}={count}")

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_assignments_by_status",
            extra={"module": __name__}
        )


def update_tutor_engagement_metrics(supabase_client, redis_client, metrics):
    """
    Update tutor engagement metrics.

    Args:
        supabase_client: Supabase client
        redis_client: Redis client
        metrics: Dict with gauge metrics (tutors_with_profiles, tutors_with_telegram_linked)
    """
    try:
        # Tutors with profiles in Redis
        if redis_client and "tutors_with_profiles" in metrics:
            pattern = "tutordex:tutor:*"
            keys = redis_client.keys(pattern)
            count = len(keys) if keys else 0
            metrics["tutors_with_profiles"].set(count)

        # Tutors with Telegram linked (from Supabase)
        if supabase_client and "tutors_with_telegram_linked" in metrics:
            response = supabase_client.rpc("count_tutors_with_telegram")
            count = response if isinstance(response, int) else 0
            metrics["tutors_with_telegram_linked"].set(count)

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_tutor_engagement",
            extra={"module": __name__}
        )


def update_assignment_quality_metrics(supabase_client, metrics):
    """
    Update assignment quality metrics.

    Args:
        supabase_client: Supabase client
        metrics: Dict with gauge metrics (assignments_with_parsed_rate, assignments_with_location)
    """
    try:
        # Percentage with parsed rate
        if "assignments_with_parsed_rate" in metrics:
            response = supabase_client.rpc("get_assignment_quality_stats")
            if response and "rate_parsed_pct" in response:
                metrics["assignments_with_parsed_rate"].set(response["rate_parsed_pct"])

        # Percentage with location
        if "assignments_with_location" in metrics:
            response = supabase_client.rpc("get_assignment_quality_stats")
            if response and "location_pct" in response:
                metrics["assignments_with_location"].set(response["location_pct"])

    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(
            e,
            context="business_metrics_quality",
            extra={"module": __name__}
        )


def update_all_business_metrics(supabase_client, redis_client, metrics_dict):
    """
    Update all business metrics in one call.

    Call this periodically (e.g., every 60 seconds) from a background thread.

    Args:
        supabase_client: Supabase client
        redis_client: Redis client
        metrics_dict: Dict mapping metric names to Prometheus objects
    """
    logger.info("Updating business metrics...")

    # Update each category
    if "assignments_created_per_hour" in metrics_dict:
        update_assignments_per_hour(supabase_client, metrics_dict["assignments_created_per_hour"])

    if "tutors_with_active_dms" in metrics_dict:
        update_tutors_with_active_dms(redis_client, metrics_dict["tutors_with_active_dms"])

    if "assignments_by_status" in metrics_dict:
        update_assignments_by_status(supabase_client, metrics_dict["assignments_by_status"])

    # Tutor engagement
    tutor_metrics = {
        k: v for k, v in metrics_dict.items()
        if k in ["tutors_with_profiles", "tutors_with_telegram_linked"]
    }
    if tutor_metrics:
        update_tutor_engagement_metrics(supabase_client, redis_client, tutor_metrics)

    # Assignment quality
    quality_metrics = {
        k: v for k, v in metrics_dict.items()
        if k in ["assignments_with_parsed_rate", "assignments_with_location"]
    }
    if quality_metrics:
        update_assignment_quality_metrics(supabase_client, quality_metrics)

    logger.info("Business metrics updated successfully")

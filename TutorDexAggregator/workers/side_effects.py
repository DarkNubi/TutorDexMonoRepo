"""
Side effects coordination for the extraction worker.

Handles broadcast and DM delivery coordination.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("side_effects")


def should_broadcast(
    enable_broadcast: bool,
    broadcast_module: Any
) -> bool:
    """
    Check if broadcasting is enabled and available.
    
    Args:
        enable_broadcast: Whether broadcasting is enabled in config
        broadcast_module: Broadcast assignments module (or None if not available)
        
    Returns:
        True if broadcasting should be attempted
    """
    return enable_broadcast and broadcast_module is not None


def should_send_dms(
    enable_dms: bool,
    send_dms_func: Any
) -> bool:
    """
    Check if DM sending is enabled and available.
    
    Args:
        enable_dms: Whether DM sending is enabled in config
        send_dms_func: Send DMs function (or None if not available)
        
    Returns:
        True if DM sending should be attempted
    """
    return enable_dms and send_dms_func is not None


def broadcast_assignment(
    payload: Dict[str, Any],
    broadcast_module: Any,
    cid: str
) -> Optional[Dict[str, Any]]:
    """
    Broadcast assignment to aggregator channel.
    
    Best-effort: failures are logged but don't fail the extraction.
    
    Args:
        payload: Assignment payload to broadcast
        broadcast_module: Broadcast assignments module
        cid: Correlation ID for logging
        
    Returns:
        Broadcast result dict or None if failed
    """
    if not broadcast_module:
        return None

    try:
        result = broadcast_module.broadcast_single_assignment(payload)
        logger.info(f"Broadcast successful for {cid}")
        return result
    except Exception as e:
        logger.warning(f"Broadcast failed for {cid}: {e}")
        return None


def send_assignment_dms(
    payload: Dict[str, Any],
    send_dms_func: Any,
    cid: str
) -> Optional[Dict[str, Any]]:
    """
    Send DMs to matched tutors.
    
    Best-effort: failures are logged but don't fail the extraction.
    
    Args:
        payload: Assignment payload for matching
        send_dms_func: Function to send DMs
        cid: Correlation ID for logging
        
    Returns:
        DM sending result dict or None if failed
    """
    if not send_dms_func:
        return None

    try:
        result = send_dms_func(payload)
        logger.info(f"DMs sent for {cid}")
        return result
    except Exception as e:
        logger.warning(f"DM sending failed for {cid}: {e}")
        return None


def execute_side_effects(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    modules: Dict[str, Any],
    cid: str
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Execute all side effects (broadcast, DMs) for an assignment.
    
    Side effects are best-effort - failures are logged but don't fail extraction.
    
    Args:
        payload: Assignment payload
        config: Configuration dict with enable flags
        modules: Dict with broadcast_module and send_dms_func
        cid: Correlation ID for logging
        
    Returns:
        Dict with results: {"broadcast": result, "dms": result}
    """
    results: Dict[str, Optional[Dict[str, Any]]] = {
        "broadcast": None,
        "dms": None
    }

    # Broadcast
    if should_broadcast(config.get("enable_broadcast", False), modules.get("broadcast_module")):
        results["broadcast"] = broadcast_assignment(
            payload,
            modules.get("broadcast_module"),
            cid
        )

    # DMs
    if should_send_dms(config.get("enable_dms", False), modules.get("send_dms_func")):
        results["dms"] = send_assignment_dms(
            payload,
            modules.get("send_dms_func"),
            cid
        )

    return results

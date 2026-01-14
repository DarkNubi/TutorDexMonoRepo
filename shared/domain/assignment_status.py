"""
Assignment Status State Machine.

Enforces valid status transitions for assignments to prevent invalid state changes.
Provides clear documentation of assignment lifecycle.
"""
from enum import Enum
from typing import Set, Optional
import logging

logger = logging.getLogger(__name__)


class AssignmentStatus(str, Enum):
    """
    Valid assignment statuses.
    
    Lifecycle:
    PENDING → OPEN → (CLOSED | EXPIRED | HIDDEN) → DELETED
    """
    PENDING = "pending"      # Just ingested, validation pending
    OPEN = "open"            # Active, visible to tutors
    CLOSED = "closed"        # Filled or manually closed
    HIDDEN = "hidden"        # Hidden by admin/flag
    EXPIRED = "expired"      # Past expiry date
    DELETED = "deleted"      # Soft-deleted (terminal state)


class StatusTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""
    
    def __init__(self, from_status: AssignmentStatus, to_status: AssignmentStatus, message: Optional[str] = None):
        self.from_status = from_status
        self.to_status = to_status
        default_message = f"Invalid status transition: {from_status.value} → {to_status.value}"
        super().__init__(message or default_message)


class AssignmentStateMachine:
    """
    Enforces valid status transitions for assignments.
    
    Valid transitions:
    - PENDING → OPEN, DELETED
    - OPEN → CLOSED, HIDDEN, EXPIRED, DELETED
    - CLOSED → OPEN (reopen), DELETED
    - HIDDEN → OPEN (unhide), DELETED
    - EXPIRED → CLOSED, DELETED
    - DELETED → (terminal, no transitions)
    """
    
    # Define valid transitions as a directed graph
    VALID_TRANSITIONS: dict[AssignmentStatus, Set[AssignmentStatus]] = {
        AssignmentStatus.PENDING: {
            AssignmentStatus.OPEN,
            AssignmentStatus.DELETED,
        },
        AssignmentStatus.OPEN: {
            AssignmentStatus.CLOSED,
            AssignmentStatus.HIDDEN,
            AssignmentStatus.EXPIRED,
            AssignmentStatus.DELETED,
        },
        AssignmentStatus.CLOSED: {
            AssignmentStatus.OPEN,      # Can reopen closed assignments
            AssignmentStatus.DELETED,
        },
        AssignmentStatus.HIDDEN: {
            AssignmentStatus.OPEN,      # Can unhide
            AssignmentStatus.DELETED,
        },
        AssignmentStatus.EXPIRED: {
            AssignmentStatus.CLOSED,    # Mark as explicitly closed
            AssignmentStatus.DELETED,
        },
        AssignmentStatus.DELETED: set(),  # Terminal state - no transitions allowed
    }
    
    @classmethod
    def can_transition(cls, from_status: AssignmentStatus, to_status: AssignmentStatus) -> bool:
        """
        Check if a status transition is valid.
        
        Args:
            from_status: Current status
            to_status: Desired status
            
        Returns:
            True if transition is allowed, False otherwise
        """
        # Same status is always allowed (no-op)
        if from_status == to_status:
            return True
        
        valid_targets = cls.VALID_TRANSITIONS.get(from_status, set())
        return to_status in valid_targets
    
    @classmethod
    def transition(
        cls,
        from_status: AssignmentStatus,
        to_status: AssignmentStatus,
        assignment_id: Optional[str] = None,
        enforce: bool = True
    ) -> AssignmentStatus:
        """
        Execute a status transition with validation.
        
        Args:
            from_status: Current status
            to_status: Desired status
            assignment_id: Assignment ID for logging
            enforce: If True, raises exception on invalid transition. If False, logs warning and allows.
            
        Returns:
            The new status
            
        Raises:
            StatusTransitionError: If transition is invalid and enforce=True
        """
        # No-op if same status
        if from_status == to_status:
            return to_status
        
        # Check if transition is valid
        if not cls.can_transition(from_status, to_status):
            error_msg = f"Invalid transition: {from_status.value} → {to_status.value}"
            if assignment_id:
                error_msg += f" (assignment_id={assignment_id})"
            
            if enforce:
                logger.error(error_msg)
                raise StatusTransitionError(from_status, to_status)
            else:
                logger.warning(f"{error_msg} - allowing due to enforce=False")
        
        logger.info(
            "assignment_status_transition",
            extra={
                "assignment_id": assignment_id,
                "from_status": from_status.value,
                "to_status": to_status.value,
            }
        )
        
        return to_status
    
    @classmethod
    def get_valid_transitions(cls, from_status: AssignmentStatus) -> Set[AssignmentStatus]:
        """
        Get all valid transition targets from a given status.
        
        Args:
            from_status: Current status
            
        Returns:
            Set of valid target statuses
        """
        return cls.VALID_TRANSITIONS.get(from_status, set())
    
    @classmethod
    def is_terminal(cls, status: AssignmentStatus) -> bool:
        """
        Check if a status is terminal (no further transitions allowed).
        
        Args:
            status: Status to check
            
        Returns:
            True if status is terminal
        """
        return len(cls.VALID_TRANSITIONS.get(status, set())) == 0


# Convenience function for common transition checks
def validate_status_transition(
    current: str,
    new: str,
    assignment_id: Optional[str] = None,
    enforce: bool = True
) -> str:
    """
    Validate and execute a status transition from string values.
    
    Args:
        current: Current status (string)
        new: New status (string)
        assignment_id: Assignment ID for logging
        enforce: If True, raises on invalid transition
        
    Returns:
        New status as string
        
    Raises:
        StatusTransitionError: If transition is invalid and enforce=True
        ValueError: If status strings are not valid enum values
    """
    try:
        from_status = AssignmentStatus(current)
        to_status = AssignmentStatus(new)
    except ValueError as e:
        raise ValueError(f"Invalid assignment status: {e}")
    
    result = AssignmentStateMachine.transition(from_status, to_status, assignment_id, enforce)
    return result.value

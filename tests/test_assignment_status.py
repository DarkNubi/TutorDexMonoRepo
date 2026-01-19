"""
Tests for Assignment Status State Machine.

Verifies that the state machine enforces valid transitions and rejects invalid ones.
"""
import pytest
from shared.domain.assignment_status import (
    AssignmentStatus,
    AssignmentStateMachine,
    StatusTransitionError,
    validate_status_transition,
)


class TestAssignmentStatus:
    """Test AssignmentStatus enum."""

    def test_status_values(self):
        """Test that all expected statuses exist."""
        assert AssignmentStatus.PENDING.value == "pending"
        assert AssignmentStatus.OPEN.value == "open"
        assert AssignmentStatus.CLOSED.value == "closed"
        assert AssignmentStatus.HIDDEN.value == "hidden"
        assert AssignmentStatus.EXPIRED.value == "expired"
        assert AssignmentStatus.DELETED.value == "deleted"


class TestAssignmentStateMachine:
    """Test state machine transition logic."""

    def test_same_status_always_allowed(self):
        """Test that transitioning to same status is always allowed."""
        for status in AssignmentStatus:
            assert AssignmentStateMachine.can_transition(status, status)
            result = AssignmentStateMachine.transition(status, status)
            assert result == status

    def test_valid_transitions_from_pending(self):
        """Test valid transitions from PENDING status."""
        assert AssignmentStateMachine.can_transition(
            AssignmentStatus.PENDING,
            AssignmentStatus.OPEN
        )
        assert AssignmentStateMachine.can_transition(
            AssignmentStatus.PENDING,
            AssignmentStatus.DELETED
        )

    def test_invalid_transitions_from_pending(self):
        """Test invalid transitions from PENDING status."""
        assert not AssignmentStateMachine.can_transition(
            AssignmentStatus.PENDING,
            AssignmentStatus.CLOSED
        )
        assert not AssignmentStateMachine.can_transition(
            AssignmentStatus.PENDING,
            AssignmentStatus.EXPIRED
        )

    def test_valid_transitions_from_open(self):
        """Test valid transitions from OPEN status."""
        from_status = AssignmentStatus.OPEN
        valid_targets = [
            AssignmentStatus.CLOSED,
            AssignmentStatus.HIDDEN,
            AssignmentStatus.EXPIRED,
            AssignmentStatus.DELETED,
        ]
        for target in valid_targets:
            assert AssignmentStateMachine.can_transition(from_status, target)

    def test_cannot_reopen_deleted(self):
        """Test that DELETED is terminal - cannot transition out."""
        deleted = AssignmentStatus.DELETED
        for target in AssignmentStatus:
            if target != deleted:
                assert not AssignmentStateMachine.can_transition(deleted, target)

    def test_can_reopen_closed(self):
        """Test that closed assignments can be reopened."""
        assert AssignmentStateMachine.can_transition(
            AssignmentStatus.CLOSED,
            AssignmentStatus.OPEN
        )

    def test_can_unhide(self):
        """Test that hidden assignments can be unhidden."""
        assert AssignmentStateMachine.can_transition(
            AssignmentStatus.HIDDEN,
            AssignmentStatus.OPEN
        )

    def test_transition_raises_on_invalid(self):
        """Test that invalid transitions raise StatusTransitionError."""
        with pytest.raises(StatusTransitionError) as exc_info:
            AssignmentStateMachine.transition(
                AssignmentStatus.DELETED,
                AssignmentStatus.OPEN,
                enforce=True
            )

        assert exc_info.value.from_status == AssignmentStatus.DELETED
        assert exc_info.value.to_status == AssignmentStatus.OPEN

    def test_transition_allows_with_enforce_false(self):
        """Test that invalid transitions are allowed when enforce=False."""
        # Should not raise, but should log warning
        result = AssignmentStateMachine.transition(
            AssignmentStatus.DELETED,
            AssignmentStatus.OPEN,
            enforce=False
        )
        assert result == AssignmentStatus.OPEN

    def test_get_valid_transitions(self):
        """Test getting valid transitions for a status."""
        open_transitions = AssignmentStateMachine.get_valid_transitions(
            AssignmentStatus.OPEN
        )
        assert AssignmentStatus.CLOSED in open_transitions
        assert AssignmentStatus.HIDDEN in open_transitions
        assert AssignmentStatus.EXPIRED in open_transitions
        assert AssignmentStatus.DELETED in open_transitions
        assert len(open_transitions) == 4

    def test_is_terminal(self):
        """Test terminal status detection."""
        assert AssignmentStateMachine.is_terminal(AssignmentStatus.DELETED)
        assert not AssignmentStateMachine.is_terminal(AssignmentStatus.OPEN)
        assert not AssignmentStateMachine.is_terminal(AssignmentStatus.CLOSED)


class TestValidateStatusTransition:
    """Test the convenience function for string-based transitions."""

    def test_valid_string_transition(self):
        """Test valid transition with string inputs."""
        result = validate_status_transition("pending", "open")
        assert result == "open"

    def test_invalid_string_transition(self):
        """Test invalid transition with string inputs."""
        with pytest.raises(StatusTransitionError):
            validate_status_transition("deleted", "open", enforce=True)

    def test_invalid_status_string(self):
        """Test that invalid status strings raise ValueError."""
        with pytest.raises(ValueError):
            validate_status_transition("invalid", "open")

    def test_transition_with_assignment_id(self):
        """Test transition logging with assignment ID."""
        result = validate_status_transition(
            "open",
            "closed",
            assignment_id="test-123"
        )
        assert result == "closed"


# Run tests with: pytest tests/test_assignment_status.py -v

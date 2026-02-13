"""
Tests for non-assignment message detection.

Tests detection of messages that should be filtered early in the pipeline:
- Status-only messages (CLOSED, TAKEN, etc.)
- Redirect messages (reposted below, see above, etc.)
- Administrative/promotional messages (Calling All Tutors, job lists, etc.)
"""

from TutorDexAggregator.extractors.non_assignment_detector import (
    is_non_assignment,
    MessageType,
)


class TestStatusOnlyMessages:
    """Test detection of status-only messages that don't contain assignment details."""

    def test_simple_closed_message(self):
        text = "ASSIGNMENT CLOSED"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY
        assert "closed" in details.lower()

    def test_closed_with_whitespace(self):
        text = """

        ASSIGNMENT CLOSED

        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY

    def test_taken_message(self):
        text = "Assignment Taken"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY

    def test_filled_message(self):
        text = "FILLED"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY

    def test_expired_message(self):
        text = "EXPIRED"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY

    def test_closed_with_extra_text(self):
        # Should NOT trigger if there's substantial other content
        text = """
🔻 Level and Subject(s): Primary 5 Math
🔻 Location/Area: Jurong West
🔻 Hourly Rate: $40/hr
Assignment Status: CLOSED
        """
        is_non, msg_type, details = is_non_assignment(text)
        # This should NOT be detected as status-only since there's assignment content
        assert is_non is False


class TestRedirectMessages:
    """Test detection of redirect/reference messages."""

    def test_reposted_below(self):
        text = "👇 Assignment 11320 has been reposted below."
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.REDIRECT
        assert "repost" in details.lower()

    def test_see_message_above(self):
        # More explicit redirect pattern
        text = "See message above for details"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.REDIRECT

    def test_updated_below(self):
        text = "Assignment updated. See below for new details."
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.REDIRECT

    def test_reposted_with_arrow(self):
        text = "👇 Assignment 11337 has been reposted below."
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.REDIRECT


class TestAdministrativeMessages:
    """Test detection of administrative/promotional messages."""

    def test_calling_all_tutors(self):
        text = """🔥 Calling All Tutors!

There are many Tuition job opportunities. Apply now!

✅ Primary 5 English OR Science @ Kingsford Waterbay
✅ Primary 3 English @ 40+ Chai Chee Street
✅ Primary 6 English @ 720+ Jurong West
        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.ADMINISTRATIVE
        assert "promotional" in details.lower() or "list" in details.lower()

    def test_job_opportunities_message(self):
        text = "📢 New job opportunities available! Check our channel for details."
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.ADMINISTRATIVE

    def test_announcement(self):
        text = """📣 Important Announcement

Our agency will be closed during CNY.
We will resume operations on 5th Feb.
        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.ADMINISTRATIVE

    def test_whatsapp_number_upgrade_announcement(self):
        text = """Dear Tutors,

TutorNow is upgrading to an official WhatsApp Business API system.
👉 New TutorNow WhatsApp Number:
+65 8813 7923
Please save this new number in your contacts.

You may login to your TutorNow Tutor Account to view and apply for assignments:
https://www.tutornow.sg/login
        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.ADMINISTRATIVE

    def test_scroll_up_pm_me_admin_message(self):
        text = "Hello tutors, if you are do not have the time to scroll up/search for assignments, kindly PM me."
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.ADMINISTRATIVE


class TestValidAssignments:
    """Test that valid assignment messages are NOT filtered out."""

    def test_online_assignment_not_filtered(self):
        text = """Looking for Online Tutor to teach Economics (EC1002)- Online Tuition

🔻 Level and Subject(s):   Economics (EC1002)
🔻 Location/Area: Online Tuition

🔻 Hourly Rate: Kindly quote best rate
🔻 Lesson Per Week: Once a week, 1.5 hours per session
🔻 Student's Gender: Female (M)
🔻 Time: Kindly state your "Detailed" Available time slots from Monday to Sunday.

Job ID: NT29838
        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is False

    def test_regular_assignment_not_filtered(self):
        text = """🔻 Level and Subject(s): Secondary 3 Math
🔻 Location/Area: Bukit Batok 650123
🔻 Hourly Rate: $45/hr
🔻 Lesson Per Week: 2 times, 1.5 hours each
🔻 Time: Weekday evenings after 6pm

Job ID: ABC123
        """
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is False

    def test_assignment_with_closed_in_content(self):
        # Assignment that mentions "closed" but is actually an assignment
        text = """🔻 Level and Subject(s): Primary 5 English
🔻 Location/Area: Near closed-loop MRT station
🔻 Hourly Rate: $40/hr

Status: OPEN
Job ID: XYZ789
        """
        is_non, msg_type, details = is_non_assignment(text)
        # Should NOT be filtered - it's a real assignment
        assert is_non is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_message(self):
        text = ""
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is False  # Empty messages handled elsewhere

    def test_whitespace_only(self):
        text = "   \n\n   \t\t   "
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is False

    def test_very_short_message(self):
        text = "OK"
        is_non, msg_type, details = is_non_assignment(text)
        # Very short messages are ambiguous, let them through
        assert is_non is False

    def test_mixed_case_status(self):
        text = "aSsiGnMenT cLoSeD"
        is_non, msg_type, details = is_non_assignment(text)
        assert is_non is True
        assert msg_type == MessageType.STATUS_ONLY

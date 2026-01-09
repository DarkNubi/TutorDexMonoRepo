"""
Tests for assignment rating system.
"""

import unittest
from TutorDexBackend.assignment_rating import (
    calculate_distance_score,
    calculate_rate_score,
    calculate_assignment_rating,
    get_rating_components,
)


class TestDistanceScore(unittest.TestCase):
    def test_very_close(self):
        # < 1km should get +5.0
        self.assertEqual(calculate_distance_score(0.5), 5.0)
        self.assertEqual(calculate_distance_score(0.9), 5.0)
    
    def test_close(self):
        # 1-3km should get +3.0
        self.assertEqual(calculate_distance_score(1.5), 3.0)
        self.assertEqual(calculate_distance_score(2.9), 3.0)
    
    def test_moderate(self):
        # 3-5km should get +1.0
        self.assertEqual(calculate_distance_score(3.5), 1.0)
        self.assertEqual(calculate_distance_score(4.9), 1.0)
    
    def test_far(self):
        # 5-10km should be neutral (0.0)
        self.assertEqual(calculate_distance_score(5.0), 0.0)
        self.assertEqual(calculate_distance_score(9.9), 0.0)
    
    def test_very_far(self):
        # > 10km should get -2.0 penalty
        self.assertEqual(calculate_distance_score(10.1), -2.0)
        self.assertEqual(calculate_distance_score(20.0), -2.0)
    
    def test_none(self):
        # No distance info should be neutral
        self.assertEqual(calculate_distance_score(None), 0.0)


class TestRateScore(unittest.TestCase):
    def test_no_rate_info(self):
        # No rate should be neutral
        self.assertEqual(calculate_rate_score(None, None, 50.0), 0.0)
        self.assertEqual(calculate_rate_score(50, None, None), 0.0)
    
    def test_no_history(self):
        # No tutor history should be neutral
        self.assertEqual(calculate_rate_score(50, 60, None), 0.0)
    
    def test_around_average(self):
        # Within +/-20% of average should be neutral
        avg = 50.0
        self.assertEqual(calculate_rate_score(50, 50, avg), 0.0)
        self.assertEqual(calculate_rate_score(45, 55, avg), 0.0)  # 50 midpoint
        self.assertEqual(calculate_rate_score(58, 58, avg), 0.0)  # 16% above, below threshold
    
    def test_high_rate_bonus(self):
        # >20% above average should get bonus
        avg = 50.0
        score = calculate_rate_score(65, 65, avg)  # 30% above
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 3.0)  # Max bonus is 3.0
    
    def test_low_rate_penalty(self):
        # >30% below average should get penalty
        avg = 50.0
        score = calculate_rate_score(30, 30, avg)  # 40% below
        self.assertLess(score, 0.0)
        self.assertGreaterEqual(score, -2.0)  # Max penalty is -2.0


class TestAssignmentRating(unittest.TestCase):
    def test_basic_score_only(self):
        # With no distance or rate info, should equal base score
        rating = calculate_assignment_rating(base_score=5)
        self.assertEqual(rating, 5.0)
    
    def test_with_distance_bonus(self):
        # Base score + distance bonus
        rating = calculate_assignment_rating(base_score=5, distance_km=0.5)
        self.assertEqual(rating, 10.0)  # 5 + 5.0 distance bonus
    
    def test_with_rate_bonus(self):
        # Base score + rate bonus (high paying assignment)
        rating = calculate_assignment_rating(
            base_score=5,
            assignment_rate_min=75,
            assignment_rate_max=75,
            tutor_avg_rate=50.0,
        )
        self.assertGreater(rating, 5.0)  # Should have bonus
        self.assertLessEqual(rating, 8.0)  # 5 + max 3.0 bonus
    
    def test_combined_scoring(self):
        # All components together
        rating = calculate_assignment_rating(
            base_score=5,
            distance_km=0.8,  # Very close: +5.0
            assignment_rate_min=70,
            assignment_rate_max=80,  # 75 midpoint, 50% above 50 avg
            tutor_avg_rate=50.0,
        )
        # Should be roughly: 5 (base) + 5 (distance) + ~3 (rate) = 13
        self.assertGreater(rating, 10.0)
        self.assertLess(rating, 15.0)
    
    def test_components_breakdown(self):
        # Test getting component breakdown
        components = get_rating_components(
            base_score=5,
            distance_km=2.0,
            assignment_rate_min=65,
            tutor_avg_rate=50.0,
        )
        
        self.assertEqual(components["base_score"], 5.0)
        self.assertEqual(components["distance_score"], 3.0)  # 1-3km range
        self.assertGreater(components["rate_score"], 0.0)  # 30% above avg, should have bonus
        self.assertEqual(components["total_rating"], 
                        components["base_score"] + components["distance_score"] + components["rate_score"])


if __name__ == "__main__":
    unittest.main()

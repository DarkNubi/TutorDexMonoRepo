"""
Tests for assignment rating system with continuous scoring.
"""

import unittest
from TutorDexBackend.assignment_rating import (
    calculate_distance_score,
    calculate_rate_score,
    calculate_assignment_rating,
    get_rating_components,
)


class TestDistanceScore(unittest.TestCase):
    def test_at_zero(self):
        # At 0km should get perfect score
        self.assertEqual(calculate_distance_score(0.0), 5.0)
    
    def test_very_close(self):
        # Within 500m should be between 4.0 and 5.0
        score_100m = calculate_distance_score(0.1)
        score_400m = calculate_distance_score(0.4)
        self.assertGreater(score_100m, 4.0)
        self.assertLessEqual(score_100m, 5.0)
        self.assertGreater(score_400m, 4.0)
        self.assertLessEqual(score_400m, 5.0)
        # Closer should score higher
        self.assertGreater(score_100m, score_400m)
    
    def test_at_tier_boundaries(self):
        # At tier boundaries should match exact values
        self.assertEqual(calculate_distance_score(0.5), 4.0)
        self.assertEqual(calculate_distance_score(1.5), 3.0)
        self.assertEqual(calculate_distance_score(3.0), 2.0)
        self.assertEqual(calculate_distance_score(5.0), 1.0)
        self.assertEqual(calculate_distance_score(10.0), 0.0)
    
    def test_between_tiers(self):
        # Between 500m and 1.5km should interpolate smoothly
        score_1km = calculate_distance_score(1.0)
        self.assertGreater(score_1km, 3.0)  # Above 1.5km boundary
        self.assertLess(score_1km, 4.0)     # Below 500m boundary
        
        # Between 1.5km and 3km
        score_2km = calculate_distance_score(2.0)
        self.assertGreater(score_2km, 2.0)
        self.assertLess(score_2km, 3.0)
    
    def test_far(self):
        # Beyond 10km should get constant penalty
        self.assertEqual(calculate_distance_score(10.1), -2.0)
        self.assertEqual(calculate_distance_score(20.0), -2.0)
    
    def test_none(self):
        # No distance info should be neutral
        self.assertEqual(calculate_distance_score(None), 0.0)
    
    def test_continuous_decrease(self):
        # Score should decrease continuously as distance increases
        scores = [calculate_distance_score(d) for d in [0.2, 0.8, 2.0, 4.0, 8.0]]
        for i in range(len(scores) - 1):
            self.assertGreater(scores[i], scores[i + 1])


class TestRateScore(unittest.TestCase):
    def test_no_rate_info(self):
        # No rate should be neutral
        self.assertEqual(calculate_rate_score(None, None, 50.0), 0.0)
        self.assertEqual(calculate_rate_score(50, None, None), 0.0)
    
    def test_no_history(self):
        # No tutor history should be neutral
        self.assertEqual(calculate_rate_score(50, 60, None), 0.0)
    
    def test_at_average(self):
        # Exactly at average should be neutral
        avg = 50.0
        self.assertEqual(calculate_rate_score(50, 50, avg), 0.0)
    
    def test_continuous_bonus(self):
        # Rate bonus should increase continuously with rate difference
        avg = 50.0
        # 25% above (within bonus range)
        score_25 = calculate_rate_score(62, 63, avg)  # ~62.5 midpoint
        # 35% above (further in bonus range)
        score_35 = calculate_rate_score(67, 68, avg)  # ~67.5 midpoint
        
        self.assertGreater(score_25, 0.0)
        self.assertGreater(score_35, score_25)
        self.assertLessEqual(score_35, 3.0)
    
    def test_continuous_penalty(self):
        # Rate penalty should increase continuously with rate deficit
        avg = 50.0
        # -35% below (within penalty range)
        score_35 = calculate_rate_score(32, 33, avg)  # ~32.5 midpoint
        # -45% below (further in penalty range)
        score_45 = calculate_rate_score(27, 28, avg)  # ~27.5 midpoint
        
        self.assertLess(score_35, 0.0)
        self.assertLess(score_45, score_35)
        self.assertGreaterEqual(score_45, -2.0)
    
    def test_neutral_zone(self):
        # Within ±20% should be neutral (no bonus/penalty threshold not reached)
        avg = 50.0
        self.assertEqual(calculate_rate_score(55, 55, avg), 0.0)  # +10%
        self.assertEqual(calculate_rate_score(45, 45, avg), 0.0)  # -10%


class TestAssignmentRating(unittest.TestCase):
    def test_basic_score_only(self):
        # With no distance or rate info, should equal base score
        rating = calculate_assignment_rating(base_score=5)
        self.assertEqual(rating, 5.0)
    
    def test_with_distance_bonus(self):
        # Base score + distance bonus (at 500m boundary)
        rating = calculate_assignment_rating(base_score=5, distance_km=0.5)
        self.assertEqual(rating, 9.0)  # 5 + 4.0
    
    def test_with_continuous_distance(self):
        # Test continuous distance scoring
        rating_close = calculate_assignment_rating(base_score=5, distance_km=0.3)
        rating_moderate = calculate_assignment_rating(base_score=5, distance_km=2.0)
        
        # Closer should rate higher
        self.assertGreater(rating_close, rating_moderate)
        
        # Both should be above base score (within positive range)
        self.assertGreater(rating_close, 5.0)
        self.assertGreater(rating_moderate, 5.0)
    
    def test_with_rate_bonus(self):
        # Base score + rate bonus (high paying assignment)
        rating = calculate_assignment_rating(
            base_score=5,
            assignment_rate_min=75,
            assignment_rate_max=75,
            tutor_avg_rate=50.0,  # 50% above average
        )
        self.assertGreater(rating, 5.0)  # Should have bonus
        self.assertLessEqual(rating, 8.0)  # 5 + max 3.0 bonus
    
    def test_combined_scoring(self):
        # All components together
        rating = calculate_assignment_rating(
            base_score=5,
            distance_km=0.8,  # Between 500m and 1.5km, ~3.7 score
            assignment_rate_min=70,
            assignment_rate_max=80,  # 75 midpoint, 50% above 50 avg
            tutor_avg_rate=50.0,
        )
        # Should be roughly: 5 (base) + ~3.7 (distance) + ~3 (rate) = ~11.7
        self.assertGreater(rating, 10.0)
        self.assertLess(rating, 13.0)
    
    def test_components_breakdown(self):
        # Test getting component breakdown
        components = get_rating_components(
            base_score=5,
            distance_km=2.0,  # Between 1.5-3km
            assignment_rate_min=65,
            tutor_avg_rate=50.0,
        )
        
        self.assertEqual(components["base_score"], 5.0)
        self.assertGreater(components["distance_score"], 2.0)
        self.assertLess(components["distance_score"], 3.0)
        self.assertGreater(components["rate_score"], 0.0)  # 30% above avg, should have bonus
        self.assertEqual(components["total_rating"], 
                        components["base_score"] + components["distance_score"] + components["rate_score"])


if __name__ == "__main__":
    unittest.main()

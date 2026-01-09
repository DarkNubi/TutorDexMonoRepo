"""
Tests for assignment rating system with continuous scoring (Singapore-optimized).
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
    
    def test_at_breakpoints(self):
        # At specific breakpoints should match exact values
        self.assertAlmostEqual(calculate_distance_score(0.8), 4.0, places=1)
        self.assertAlmostEqual(calculate_distance_score(1.8), 3.0, places=1)
        self.assertAlmostEqual(calculate_distance_score(3.5), 2.0, places=1)
        self.assertAlmostEqual(calculate_distance_score(6.0), 1.0, places=1)
        self.assertEqual(calculate_distance_score(10.0), 0.0)
        self.assertEqual(calculate_distance_score(12.0), -1.5)
    
    def test_between_breakpoints(self):
        # Between 0 and 0.8km should interpolate
        score_0_4 = calculate_distance_score(0.4)
        self.assertGreater(score_0_4, 4.0)
        self.assertLess(score_0_4, 5.0)
        
        # Between 1.8 and 3.5km
        score_2_5 = calculate_distance_score(2.5)
        self.assertGreater(score_2_5, 2.0)
        self.assertLess(score_2_5, 3.0)
    
    def test_very_far(self):
        # Beyond 12km should get hard floor
        self.assertEqual(calculate_distance_score(12.1), -1.5)
        self.assertEqual(calculate_distance_score(20.0), -1.5)
    
    def test_none(self):
        # No distance info should be neutral
        self.assertEqual(calculate_distance_score(None), 0.0)
    
    def test_continuous_decrease(self):
        # Score should decrease continuously as distance increases
        scores = [calculate_distance_score(d) for d in [0.5, 1.5, 3.0, 5.0, 9.0]]
        for i in range(len(scores) - 1):
            self.assertGreater(scores[i], scores[i + 1])
    
    def test_singapore_realism(self):
        # Test Singapore-specific breakpoints
        # 0.8km = 1-2 bus stops, should score 4.0
        self.assertAlmostEqual(calculate_distance_score(0.8), 4.0, places=1)
        # 6km = peak-hour pain begins, should score 1.0
        self.assertAlmostEqual(calculate_distance_score(6.0), 1.0, places=1)


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
    
    def test_at_breakpoints(self):
        # Test specific breakpoints
        avg = 100.0
        
        # +25% = 125 → +2.0
        self.assertAlmostEqual(calculate_rate_score(125, 125, avg), 2.0, places=1)
        
        # +15% = 115 → +1.5
        self.assertAlmostEqual(calculate_rate_score(115, 115, avg), 1.5, places=1)
        
        # +10% = 110 → +1.0
        self.assertAlmostEqual(calculate_rate_score(110, 110, avg), 1.0, places=1)
        
        # +5% = 105 → +0.5
        self.assertAlmostEqual(calculate_rate_score(105, 105, avg), 0.5, places=1)
        
        # -5% = 95 → -0.5
        self.assertAlmostEqual(calculate_rate_score(95, 95, avg), -0.5, places=1)
        
        # -15% = 85 → -1.5
        self.assertAlmostEqual(calculate_rate_score(85, 85, avg), -1.5, places=1)
    
    def test_continuous_interpolation(self):
        # Between breakpoints should interpolate smoothly
        avg = 100.0
        
        # Between +5% and +10% (105-110)
        score_7_5 = calculate_rate_score(107, 108, avg)  # ~7.5% above
        self.assertGreater(score_7_5, 0.5)
        self.assertLess(score_7_5, 1.0)
    
    def test_extreme_values(self):
        # Beyond breakpoints should be capped
        avg = 100.0
        
        # +50% (way beyond +25% cap)
        self.assertEqual(calculate_rate_score(150, 150, avg), 2.0)
        
        # -50% (way beyond -25% floor)
        self.assertEqual(calculate_rate_score(50, 50, avg), -2.0)
    
    def test_hard_caps(self):
        # Verify hard caps are enforced
        avg = 50.0
        
        # Extreme positive should cap at +2.0
        score_high = calculate_rate_score(200, 200, avg)
        self.assertEqual(score_high, 2.0)
        
        # Extreme negative should floor at -2.0
        score_low = calculate_rate_score(10, 10, avg)
        self.assertEqual(score_low, -2.0)


class TestAssignmentRating(unittest.TestCase):
    def test_basic_score_only(self):
        # With no distance or rate info, should equal base score
        rating = calculate_assignment_rating(base_score=5)
        self.assertEqual(rating, 5.0)
    
    def test_with_distance_bonus(self):
        # Base score + distance bonus (at 0.8km breakpoint)
        rating = calculate_assignment_rating(base_score=5, distance_km=0.8)
        self.assertAlmostEqual(rating, 9.0, places=1)  # 5 + 4.0
    
    def test_with_continuous_distance(self):
        # Test continuous distance scoring
        rating_close = calculate_assignment_rating(base_score=5, distance_km=0.4)
        rating_moderate = calculate_assignment_rating(base_score=5, distance_km=2.5)
        
        # Closer should rate higher
        self.assertGreater(rating_close, rating_moderate)
        
        # Both should be above base score (within positive range)
        self.assertGreater(rating_close, 5.0)
        self.assertGreater(rating_moderate, 5.0)
    
    def test_with_rate_bonus(self):
        # Base score + rate bonus
        rating = calculate_assignment_rating(
            base_score=5,
            assignment_rate_min=115,
            assignment_rate_max=115,
            tutor_avg_rate=100.0,  # +15% above average
        )
        self.assertAlmostEqual(rating, 6.5, places=1)  # 5 + 1.5
    
    def test_combined_scoring(self):
        # All components together
        rating = calculate_assignment_rating(
            base_score=5,
            distance_km=1.0,     # Between 0.8-1.8km, ~3.6 score
            assignment_rate_min=110,
            assignment_rate_max=110,  # +10% above avg, +1.0 score
            tutor_avg_rate=100.0,
        )
        # Should be roughly: 5 (base) + ~3.6 (distance) + 1.0 (rate) = ~9.6
        self.assertGreater(rating, 9.0)
        self.assertLess(rating, 10.5)
    
    def test_singapore_realistic_scenario(self):
        # Realistic Singapore scenario: good match, close distance, decent rate
        rating = calculate_assignment_rating(
            base_score=6,        # Good subject/level match
            distance_km=1.5,     # Between 0.8-1.8km, ~3.2 score
            assignment_rate_min=55,
            assignment_rate_max=55,  # +10% above avg of 50
            tutor_avg_rate=50.0,
        )
        # Should be: 6 + ~3.2 + 1.0 = ~10.2
        self.assertGreater(rating, 9.5)
        self.assertLess(rating, 11.0)
    
    def test_components_breakdown(self):
        # Test getting component breakdown
        components = get_rating_components(
            base_score=5,
            distance_km=2.0,
            assignment_rate_min=105,
            tutor_avg_rate=100.0,
        )
        
        self.assertEqual(components["base_score"], 5.0)
        self.assertGreater(components["distance_score"], 2.0)
        self.assertLess(components["distance_score"], 3.0)
        self.assertAlmostEqual(components["rate_score"], 0.5, places=1)  # +5% → +0.5
        self.assertEqual(components["total_rating"], 
                        components["base_score"] + components["distance_score"] + components["rate_score"])


if __name__ == "__main__":
    unittest.main()

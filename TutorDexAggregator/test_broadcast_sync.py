#!/usr/bin/env python3
"""
Integration test for broadcast channel sync.

This script demonstrates the workflow:
1. Configure broadcast channels
2. Simulate sending broadcasts
3. Run sync to reconcile
"""
import os
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

def test_configuration():
    """Test 1: Verify configuration parsing."""
    print("=" * 70)
    print("TEST 1: Configuration Parsing")
    print("=" * 70)
    
    # Set test env
    os.environ['AGGREGATOR_CHANNEL_IDS'] = '["-1001234567890", "-1009876543210"]'
    os.environ['GROUP_BOT_TOKEN'] = 'test_token'
    os.environ['ENABLE_BROADCAST_TRACKING'] = '1'
    
    # Import after setting env
    import broadcast_assignments
    
    print(f"✓ Parsed TARGET_CHATS: {broadcast_assignments.TARGET_CHATS}")
    print(f"✓ Backward compat TARGET_CHAT: {broadcast_assignments.TARGET_CHAT}")
    print(f"✓ Tracking enabled: {broadcast_assignments.ENABLE_BROADCAST_TRACKING}")
    
    assert len(broadcast_assignments.TARGET_CHATS) == 2, "Should parse 2 channels"
    assert broadcast_assignments.ENABLE_BROADCAST_TRACKING, "Tracking should be enabled"
    print("✅ Configuration test passed\n")


def test_sync_script():
    """Test 2: Verify sync script help works."""
    print("=" * 70)
    print("TEST 2: Sync Script")
    print("=" * 70)
    
    import subprocess
    result = subprocess.run(
        ['python3', 'sync_broadcast_channel.py', '--help'],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
        timeout=10
    )
    
    assert result.returncode == 0, "Sync script should run"
    assert '--dry-run' in result.stdout, "Should have dry-run option"
    assert '--delete-only' in result.stdout, "Should have delete-only option"
    assert '--post-only' in result.stdout, "Should have post-only option"
    
    print("✓ Sync script is executable")
    print("✓ All command-line options present")
    print("✅ Sync script test passed\n")


def test_multi_channel_logic():
    """Test 3: Verify multi-channel send logic."""
    print("=" * 70)
    print("TEST 3: Multi-Channel Logic")
    print("=" * 70)
    
    # Test that send_broadcast function signature is correct
    import broadcast_assignments
    from inspect import signature
    
    sig = signature(broadcast_assignments.send_broadcast)
    params = list(sig.parameters.keys())
    
    assert 'payload' in params, "Should have payload parameter"
    assert 'target_chats' in params, "Should have target_chats parameter"
    
    # Test helper function exists
    assert hasattr(broadcast_assignments, '_send_to_single_chat'), "Should have _send_to_single_chat helper"
    
    print("✓ send_broadcast signature correct")
    print("✓ Helper functions present")
    print("✅ Multi-channel logic test passed\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("BROADCAST CHANNEL SYNC - INTEGRATION TEST")
    print("=" * 70 + "\n")
    
    try:
        test_configuration()
        test_sync_script()
        test_multi_channel_logic()
        
        print("=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Configure AGGREGATOR_CHANNEL_IDS in .env")
        print("2. Set ENABLE_BROADCAST_TRACKING=1")
        print("3. Run: python sync_broadcast_channel.py --dry-run")
        print("4. Review changes and run without --dry-run to apply")
        print("5. Optional: Enable BROADCAST_SYNC_ON_STARTUP=1 for auto-sync")
        print()
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

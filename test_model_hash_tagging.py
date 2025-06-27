#!/usr/bin/env python
"""
Test script to verify model-based hash tagging for Redis Cluster compatibility.

This script tests that:
1. Cache keys and invalidation keys for the same model use the same hash tag
2. Keys for different models use different hash tags
3. Multi-key operations (MGET) work correctly within the same model

Usage:
    python test_model_hash_tagging.py
"""

import os
import sys
import django
from django.conf import settings

# Configure Django settings for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'cacheops',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        # Configure Redis Cluster for testing
        CACHEOPS_REDIS_CLUSTER={
            'startup_nodes': [
                {'host': 'localhost', 'port': 7001},
                {'host': 'localhost', 'port': 7002},
                {'host': 'localhost', 'port': 7003},
            ],
            'socket_timeout': 5.0,
            'socket_connect_timeout': 5.0,
            'retry_on_timeout': True,
            'skip_full_coverage_check': True,
        },
        CACHEOPS_INSIDEOUT=True,
        CACHEOPS_DEFAULTS={
            'timeout': 60 * 15
        },
        CACHEOPS={
            'auth.user': {'ops': 'all'},
            'contenttypes.contenttype': {'ops': 'all'},
        },
        SECRET_KEY='test-key-for-hash-tagging',
    )
    django.setup()

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from cacheops.getset import dnfs_to_conj_keys, _extract_model_name_from_cond_dnfs, _apply_model_hash_tag
from cacheops.redis import redis_client


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")


def test_model_name_extraction():
    """Test that model names are correctly extracted from cond_dnfs"""
    print_section("Testing Model Name Extraction")

    # Test cases with different cond_dnfs structures
    test_cases = [
        ({'auth_user': [{'id': 1}]}, 'auth_user'),
        ({'contenttypes_contenttype': [{'app_label': 'auth'}]}, 'contenttypes_contenttype'),
        ({'my_app_mymodel': [{'field': 'value'}]}, 'my_app_mymodel'),
        ({}, 'default'),  # Empty case
    ]

    for cond_dnfs, expected in test_cases:
        result = _extract_model_name_from_cond_dnfs(cond_dnfs)
        status = "✅" if result == expected else "❌"
        print(f"{status} {cond_dnfs} -> '{result}' (expected: '{expected}')")

    print("\nModel name extraction test completed.")


def test_hash_tag_application():
    """Test that hash tags are correctly applied to cache keys"""
    print_section("Testing Hash Tag Application")

    test_cases = [
        ('q:abc123', 'auth_user', '{auth_user}:q:abc123'),
        ('prefix:key', 'my_model', '{my_model}:prefix:key'),
        ('{existing}:key', 'new_model', '{existing}:key'),  # Should not modify existing tags
        ('simple_key', 'default', '{default}:simple_key'),
    ]

    for original_key, model_name, expected in test_cases:
        result = _apply_model_hash_tag(original_key, model_name)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{original_key}' + '{model_name}' -> '{result}' (expected: '{expected}')")

    print("\nHash tag application test completed.")


def test_conj_keys_consistency():
    """Test that conj keys use consistent hash tagging"""
    print_section("Testing Conj Keys Consistency")

    # Simulate different model scenarios
    test_scenarios = [
        {
            'name': 'User model query',
            'prefix': 'test:',
            'cond_dnfs': {'auth_user': [{'id': 1}, {'username': 'testuser'}]},
            'expected_model': 'auth_user'
        },
        {
            'name': 'ContentType model query',
            'prefix': 'test:',
            'cond_dnfs': {'contenttypes_contenttype': [{'app_label': 'auth'}]},
            'expected_model': 'contenttypes_contenttype'
        },
    ]

    for scenario in test_scenarios:
        print(f"\nScenario: {scenario['name']}")
        conj_keys = dnfs_to_conj_keys(scenario['prefix'], scenario['cond_dnfs'])

        print(f"Generated {len(conj_keys)} conj keys:")
        for key in conj_keys:
            print(f"  - {key}")

        # Verify all keys use the same hash tag
        hash_tags = set()
        for key in conj_keys:
            if '{' in key and '}' in key:
                hash_tag = key[key.find('{')+1:key.find('}')]
                hash_tags.add(hash_tag)

        if len(hash_tags) <= 1:
            expected_tag = scenario['expected_model']
            actual_tag = hash_tags.pop() if hash_tags else 'none'
            status = "✅" if actual_tag == expected_tag else "❌"
            print(f"  {status} All keys use consistent hash tag: '{actual_tag}' (expected: '{expected_tag}')")
        else:
            print(f"  ❌ Inconsistent hash tags found: {hash_tags}")

    print("\nConj keys consistency test completed.")


def test_redis_cluster_slot_consistency():
    """Test that keys with the same hash tag map to the same Redis slot"""
    print_section("Testing Redis Cluster Slot Consistency")

    try:
        # Test different key patterns for the same model
        test_keys = [
            '{auth_user}:q:abc123',
            '{auth_user}:conj:auth_user:id=1',
            '{auth_user}:conj:auth_user:username=test',
            '{auth_user}:schemes:auth_user',
        ]

        print("Testing keys for 'auth_user' model:")

        # Calculate Redis slots for each key
        slots = {}
        for key in test_keys:
            try:
                # Use the Redis cluster client's keyslot method if available
                if hasattr(redis_client, 'keyslot'):
                    slot = redis_client.keyslot(key)
                    slots[key] = slot
                else:
                    # Fallback: simulate slot calculation
                    import binascii
                    import crc16
                    if '{' in key and '}' in key:
                        hash_part = key[key.find('{')+1:key.find('}')]
                    else:
                        hash_part = key
                    slot = crc16.crc16xmodem(hash_part.encode()) % 16384
                    slots[key] = slot
            except Exception as e:
                print(f"  Could not calculate slot for {key}: {e}")
                slots[key] = None

        # Display results
        unique_slots = set(slot for slot in slots.values() if slot is not None)

        for key, slot in slots.items():
            print(f"  {key} -> slot {slot}")

        if len(unique_slots) <= 1:
            print(f"  ✅ All keys map to the same slot: {unique_slots.pop() if unique_slots else 'unknown'}")
        else:
            print(f"  ❌ Keys map to different slots: {unique_slots}")

        # Test keys from different models should map to different slots
        print("\nTesting keys from different models:")
        different_model_keys = [
            '{auth_user}:test',
            '{contenttypes_contenttype}:test',
        ]

        different_slots = {}
        for key in different_model_keys:
            try:
                if hasattr(redis_client, 'keyslot'):
                    slot = redis_client.keyslot(key)
                else:
                    hash_part = key[key.find('{')+1:key.find('}')]
                    slot = crc16.crc16xmodem(hash_part.encode()) % 16384 if '{' in key else None
                different_slots[key] = slot
                print(f"  {key} -> slot {slot}")
            except Exception as e:
                print(f"  Could not calculate slot for {key}: {e}")

        different_unique_slots = set(slot for slot in different_slots.values() if slot is not None)
        if len(different_unique_slots) > 1:
            print(f"  ✅ Different models map to different slots: {different_unique_slots}")
        else:
            print(f"  ⚠️  Different models map to same slot (may be coincidental): {different_unique_slots}")

    except Exception as e:
        print(f"Could not test Redis slot consistency: {e}")
        print("This test requires a Redis Cluster connection")

    print("\nRedis slot consistency test completed.")


def test_mget_compatibility():
    """Test that MGET operations work with hash-tagged keys"""
    print_section("Testing MGET Compatibility")

    try:
        # Create test keys with consistent hash tags
        test_data = {
            '{auth_user}:test:key1': 'value1',
            '{auth_user}:test:key2': 'value2',
            '{auth_user}:test:key3': 'value3',
        }

        print("Setting up test data...")
        for key, value in test_data.items():
            redis_client.set(key, value)
            print(f"  Set {key} = {value}")

        # Test MGET operation
        print("\nTesting MGET operation...")
        keys_to_get = list(test_data.keys())
        try:
            results = redis_client.mget(keys_to_get)
            print("  ✅ MGET operation succeeded")

            for key, expected_value, actual_value in zip(keys_to_get, test_data.values(), results):
                actual_str = actual_value.decode() if isinstance(actual_value, bytes) else str(actual_value)
                status = "✅" if actual_str == expected_value else "❌"
                print(f"    {status} {key}: expected '{expected_value}', got '{actual_str}'")

        except Exception as e:
            print(f"  ❌ MGET operation failed: {e}")
            print("  This suggests keys are not in the same Redis Cluster slot")

        # Clean up test data
        print("\nCleaning up test data...")
        for key in test_data.keys():
            redis_client.delete(key)

    except Exception as e:
        print(f"Could not test MGET compatibility: {e}")
        print("This test requires a Redis connection")

    print("\nMGET compatibility test completed.")


def main():
    """Run all hash tagging tests"""
    print("Django Cacheops Model-Based Hash Tagging Test")
    print("=" * 60)

    test_model_name_extraction()
    test_hash_tag_application()
    test_conj_keys_consistency()
    test_redis_cluster_slot_consistency()
    test_mget_compatibility()

    print(f"\n{'='*60}")
    print("All tests completed!")
    print("If all tests show ✅, your model-based hash tagging is working correctly.")
    print("If you see ❌, there may be issues with Redis Cluster key distribution.")
    print("=" * 60)


if __name__ == "__main__":
    main()

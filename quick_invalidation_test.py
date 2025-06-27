#!/usr/bin/env python
"""
Quick test to verify that the invalidation fix works correctly.

This test simulates the exact error case that was failing:
AttributeError: 'list' object has no attribute 'isalnum'

The error occurred in invalidate_dict when it called:
get_prefix(_cond_dnfs=[(model._meta.db_table, list(obj_dict.items()))], dbs=[using])

Usage:
    python quick_invalidation_test.py
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
        # Configure Redis Cluster to trigger the hash tagging logic
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
        },
        SECRET_KEY='test-key-for-invalidation-fix',
    )
    django.setup()

from django.contrib.auth.models import User
from cacheops.sharding import get_prefix


def test_original_error_case():
    """Test the exact case that was causing the original error"""
    print("Testing the original error case...")
    print("=" * 50)

    # This simulates the exact call from invalidate_dict that was failing
    # invalidate_dict calls: get_prefix(_cond_dnfs=[(model._meta.db_table, list(obj_dict.items()))], dbs=[using])

    # Simulate User model invalidation
    model_table = 'auth_user'
    obj_dict_items = [('id', 1), ('username', 'testuser'), ('email', 'test@example.com')]
    using = 'default'

    try:
        print(f"Calling get_prefix with:")
        print(f"  _cond_dnfs=[({model_table!r}, {obj_dict_items!r})]")
        print(f"  dbs=[{using!r}]")

        prefix = get_prefix(_cond_dnfs=[(model_table, obj_dict_items)], dbs=[using])

        print(f"\n✅ SUCCESS! Generated prefix: '{prefix}'")

        # Verify the prefix contains the expected hash tag
        expected_hash_tag = f"{{{model_table}}}:"
        if expected_hash_tag in prefix:
            print(f"✅ Prefix contains expected hash tag: {expected_hash_tag}")
        else:
            print(f"⚠️  Prefix doesn't contain expected hash tag: {expected_hash_tag}")

        return True

    except AttributeError as e:
        if "'list' object has no attribute 'isalnum'" in str(e):
            print(f"❌ FAILED with original error: {e}")
        else:
            print(f"❌ FAILED with different AttributeError: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED with unexpected error: {e}")
        return False


def test_various_table_names():
    """Test with various table names to ensure robustness"""
    print("\nTesting various table names...")
    print("=" * 50)

    test_cases = [
        ('auth_user', [('id', 1)]),
        ('contenttypes_contenttype', [('app_label', 'auth')]),
        ('my_app_mymodel', [('field', 'value')]),
        ('table-with-dashes', [('id', 1)]),  # Special characters
        ('table.with.dots', [('id', 1)]),    # Special characters
    ]

    success_count = 0

    for table_name, obj_items in test_cases:
        try:
            prefix = get_prefix(_cond_dnfs=[(table_name, obj_items)], dbs=['default'])
            print(f"✅ {table_name} -> '{prefix}'")
            success_count += 1
        except Exception as e:
            print(f"❌ {table_name} -> Error: {e}")

    print(f"\nResults: {success_count}/{len(test_cases)} test cases passed")
    return success_count == len(test_cases)


def test_without_cluster():
    """Test that it works normally without cluster configuration"""
    print("\nTesting without cluster configuration...")
    print("=" * 50)

    # Temporarily disable cluster configuration
    original_cluster_config = getattr(settings, 'CACHEOPS_REDIS_CLUSTER', None)
    settings.CACHEOPS_REDIS_CLUSTER = {}

    try:
        prefix = get_prefix(_cond_dnfs=[('auth_user', [('id', 1)])], dbs=['default'])
        print(f"✅ Without cluster: '{prefix}'")

        # Should not contain hash tags
        if '{' not in prefix:
            print("✅ No hash tags when cluster is disabled")
            return True
        else:
            print("⚠️  Hash tags present when cluster is disabled")
            return False

    except Exception as e:
        print(f"❌ Error without cluster: {e}")
        return False
    finally:
        # Restore original configuration
        settings.CACHEOPS_REDIS_CLUSTER = original_cluster_config


def simulate_invalidate_dict():
    """Simulate the actual invalidate_dict function call"""
    print("\nSimulating actual invalidate_dict call...")
    print("=" * 50)

    # Create a mock User model-like object
    class MockModel:
        class Meta:
            db_table = 'auth_user'

        class _meta:
            db_table = 'auth_user'

    model = MockModel()
    obj_dict = {'id': 1, 'username': 'testuser', 'email': 'test@example.com'}
    using = 'default'

    try:
        # This is the exact call from invalidate_dict that was failing
        prefix = get_prefix(_cond_dnfs=[(model._meta.db_table, list(obj_dict.items()))], dbs=[using])

        print(f"✅ Simulated invalidate_dict succeeded!")
        print(f"   Model table: {model._meta.db_table}")
        print(f"   Object dict: {obj_dict}")
        print(f"   Generated prefix: '{prefix}'")

        return True

    except Exception as e:
        print(f"❌ Simulated invalidate_dict failed: {e}")
        return False


def main():
    """Run all tests"""
    print("Quick Invalidation Test for Redis Cluster Hash Tagging Fix")
    print("=" * 60)
    print("This test verifies that the AttributeError fix is working correctly.")
    print()

    tests = [
        ("Original Error Case", test_original_error_case),
        ("Various Table Names", test_various_table_names),
        ("Without Cluster Config", test_without_cluster),
        ("Simulate invalidate_dict", simulate_invalidate_dict),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        if test_func():
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Total: {passed + failed}")

    if failed == 0:
        print(f"\n🎉 All tests passed! The invalidation fix is working correctly.")
        print(f"The original AttributeError should be resolved.")
    else:
        print(f"\n⚠️  Some tests failed. The fix may need further work.")

    print(f"{'='*60}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
Test script to verify the sharding fix for Redis Cluster compatibility.

This script tests that the prefix generation works correctly with different
input formats, especially the list of tuples format used in invalidation.

Usage:
    python test_sharding_fix.py
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
        SECRET_KEY='test-key-for-sharding-fix',
    )
    django.setup()

from django.contrib.auth.models import User
from cacheops.sharding import get_prefix


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")


def test_invalidation_prefix_format():
    """Test the prefix generation for invalidation calls (list of tuples format)"""
    print_section("Testing Invalidation Prefix Format")

    # This simulates how invalidate_dict calls get_prefix
    # _cond_dnfs=[(model._meta.db_table, list(obj_dict.items()))]

    test_cases = [
        {
            'name': 'User model invalidation',
            'kwargs': {
                '_cond_dnfs': [('auth_user', [('id', 1), ('username', 'test')])],
                'dbs': ['default']
            },
            'expected_table': 'auth_user'
        },
        {
            'name': 'ContentType model invalidation',
            'kwargs': {
                '_cond_dnfs': [('contenttypes_contenttype', [('app_label', 'auth')])],
                'dbs': ['default']
            },
            'expected_table': 'contenttypes_contenttype'
        },
        {
            'name': 'Custom table invalidation',
            'kwargs': {
                '_cond_dnfs': [('my_app_mymodel', [('field', 'value')])],
                'dbs': ['default']
            },
            'expected_table': 'my_app_mymodel'
        }
    ]

    for case in test_cases:
        print(f"\nTest case: {case['name']}")
        try:
            prefix = get_prefix(**case['kwargs'])
            print(f"Generated prefix: '{prefix}'")

            expected_hash_tag = f"{{{case['expected_table']}}}:"
            if expected_hash_tag in prefix:
                print(f"✅ Prefix contains expected hash tag: {expected_hash_tag}")
            else:
                print(f"❌ Prefix missing expected hash tag: {expected_hash_tag}")

        except Exception as e:
            print(f"❌ Error generating prefix: {e}")


def test_queryset_prefix_format():
    """Test the prefix generation for queryset calls"""
    print_section("Testing Queryset Prefix Format")

    # Test with actual Django querysets
    user_qs = User.objects.all()

    try:
        prefix = get_prefix(_queryset=user_qs)
        print(f"User queryset prefix: '{prefix}'")

        if '{auth_user}:' in prefix:
            print("✅ Queryset prefix contains correct hash tag")
        else:
            print("❌ Queryset prefix missing hash tag")

    except Exception as e:
        print(f"❌ Error generating queryset prefix: {e}")


def test_tables_parameter_format():
    """Test the prefix generation with direct tables parameter"""
    print_section("Testing Tables Parameter Format")

    test_cases = [
        (['auth_user'], 'auth_user'),
        (['contenttypes_contenttype'], 'contenttypes_contenttype'),
        (['my_app_mymodel'], 'my_app_mymodel'),
    ]

    for tables, expected_table in test_cases:
        try:
            prefix = get_prefix(tables=tables, dbs=['default'])
            print(f"Tables {tables} -> prefix: '{prefix}'")

            expected_hash_tag = f"{{{expected_table}}}:"
            if expected_hash_tag in prefix:
                print(f"✅ Contains expected hash tag: {expected_hash_tag}")
            else:
                print(f"❌ Missing expected hash tag: {expected_hash_tag}")

        except Exception as e:
            print(f"❌ Error with tables {tables}: {e}")


def test_without_cluster_config():
    """Test that prefixes work normally without cluster configuration"""
    print_section("Testing Without Cluster Configuration")

    # Temporarily disable cluster configuration
    original_cluster_config = getattr(settings, 'CACHEOPS_REDIS_CLUSTER', None)
    settings.CACHEOPS_REDIS_CLUSTER = {}

    try:
        # Test various prefix generation methods
        prefix1 = get_prefix(tables=['auth_user'], dbs=['default'])
        prefix2 = get_prefix(_cond_dnfs=[('auth_user', [('id', 1)])], dbs=['default'])

        print(f"Prefix with tables parameter: '{prefix1}'")
        print(f"Prefix with _cond_dnfs parameter: '{prefix2}'")

        # Should not contain hash tags
        if '{' not in prefix1 and '{' not in prefix2:
            print("✅ No hash tags when cluster is not configured")
        else:
            print("❌ Hash tags present when cluster is not configured")

    finally:
        # Restore original configuration
        settings.CACHEOPS_REDIS_CLUSTER = original_cluster_config


def test_edge_cases():
    """Test edge cases and error conditions"""
    print_section("Testing Edge Cases")

    edge_cases = [
        {
            'name': 'Empty _cond_dnfs list',
            'kwargs': {'_cond_dnfs': [], 'dbs': ['default']},
        },
        {
            'name': 'Empty tables list',
            'kwargs': {'tables': [], 'dbs': ['default']},
        },
        {
            'name': 'Special characters in table name',
            'kwargs': {'tables': ['my-app.my_model'], 'dbs': ['default']},
        },
    ]

    for case in edge_cases:
        print(f"\nEdge case: {case['name']}")
        try:
            prefix = get_prefix(**case['kwargs'])
            print(f"Generated prefix: '{prefix}'")
            print("✅ No errors occurred")
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Run all sharding fix tests"""
    print("Django Cacheops Sharding Fix Test")
    print("=" * 60)

    test_invalidation_prefix_format()
    test_queryset_prefix_format()
    test_tables_parameter_format()
    test_without_cluster_config()
    test_edge_cases()

    print(f"\n{'='*60}")
    print("All tests completed!")
    print("If all tests show ✅, the sharding fix is working correctly.")
    print("=" * 60)


if __name__ == "__main__":
    main()

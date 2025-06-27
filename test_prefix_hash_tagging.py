#!/usr/bin/env python
"""
Test script to verify prefix-based hash tagging for Redis Cluster compatibility.

This script tests that:
1. Prefixes include table name hash tags when Redis Cluster is configured
2. All cache operations for the same model use the same hash tag
3. Keys for different models use different hash tags

Usage:
    python test_prefix_hash_tagging.py
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
        SECRET_KEY='test-key-for-prefix-hash-tagging',
    )
    django.setup()

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from cacheops.sharding import get_prefix


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")


def test_prefix_hash_tagging():
    """Test that prefixes include hash tags for Redis Cluster"""
    print_section("Testing Prefix Hash Tagging")

    # Test User model prefix
    user_prefix = get_prefix(tables=['auth_user'])
    print(f"User model prefix: '{user_prefix}'")

    # Test ContentType model prefix
    contenttype_prefix = get_prefix(tables=['contenttypes_contenttype'])
    print(f"ContentType model prefix: '{contenttype_prefix}'")

    # Verify hash tags are present
    if '{auth_user}:' in user_prefix:
        print("✅ User model prefix contains correct hash tag")
    else:
        print("❌ User model prefix missing hash tag")

    if '{contenttypes_contenttype}:' in contenttype_prefix:
        print("✅ ContentType model prefix contains correct hash tag")
    else:
        print("❌ ContentType model prefix missing hash tag")

    # Verify different models have different prefixes
    if user_prefix != contenttype_prefix:
        print("✅ Different models have different prefixes")
    else:
        print("❌ Different models have the same prefix")


def test_queryset_prefix():
    """Test prefix generation from querysets"""
    print_section("Testing Queryset Prefix Generation")

    # Create test models to get querysets
    user_qs = User.objects.all()
    contenttype_qs = ContentType.objects.all()

    # Test prefix generation from querysets
    user_prefix = get_prefix(_queryset=user_qs)
    contenttype_prefix = get_prefix(_queryset=contenttype_qs)

    print(f"User queryset prefix: '{user_prefix}'")
    print(f"ContentType queryset prefix: '{contenttype_prefix}'")

    # Verify hash tags
    if '{auth_user}:' in user_prefix:
        print("✅ User queryset prefix contains correct hash tag")
    else:
        print("❌ User queryset prefix missing hash tag")

    if '{contenttypes_contenttype}:' in contenttype_prefix:
        print("✅ ContentType queryset prefix contains correct hash tag")
    else:
        print("❌ ContentType queryset prefix missing hash tag")


def test_cache_key_generation():
    """Test that cache keys use the hash-tagged prefix"""
    print_section("Testing Cache Key Generation")

    # Get a queryset and its cache key
    user_qs = User.objects.filter(id=1)
    cache_key = user_qs._cache_key()

    print(f"User cache key: '{cache_key}'")

    # Verify the cache key starts with the hash-tagged prefix
    if cache_key.startswith('{auth_user}:'):
        print("✅ Cache key starts with correct hash tag")
    else:
        print("❌ Cache key doesn't start with hash tag")


def test_conj_keys():
    """Test that conj keys inherit the hash-tagged prefix"""
    print_section("Testing Conj Keys")

    from cacheops.getset import dnfs_to_conj_keys

    # Simulate a condition DNF for User model
    cond_dnfs = {'auth_user': [{'id': 1}, {'username': 'test'}]}

    # Get prefix for this table
    prefix = get_prefix(tables=['auth_user'])
    print(f"Prefix: '{prefix}'")

    # Generate conj keys
    conj_keys = dnfs_to_conj_keys(prefix, cond_dnfs)

    print(f"Generated {len(conj_keys)} conj keys:")
    for key in conj_keys:
        print(f"  - {key}")

    # Verify all conj keys start with the same hash tag
    hash_tag_consistent = all(key.startswith('{auth_user}:') for key in conj_keys)

    if hash_tag_consistent:
        print("✅ All conj keys use consistent hash tag")
    else:
        print("❌ Conj keys have inconsistent hash tags")


def test_without_cluster():
    """Test that prefixes work normally when cluster is not configured"""
    print_section("Testing Without Redis Cluster Configuration")

    # Temporarily disable cluster configuration
    original_cluster_config = getattr(settings, 'CACHEOPS_REDIS_CLUSTER', None)
    settings.CACHEOPS_REDIS_CLUSTER = {}

    try:
        # Test prefix generation without cluster
        user_prefix = get_prefix(tables=['auth_user'])
        print(f"Prefix without cluster: '{user_prefix}'")

        # Should not contain hash tags
        if '{' not in user_prefix:
            print("✅ No hash tags when cluster is not configured")
        else:
            print("❌ Hash tags present when cluster is not configured")

    finally:
        # Restore original configuration
        settings.CACHEOPS_REDIS_CLUSTER = original_cluster_config


def main():
    """Run all prefix hash tagging tests"""
    print("Django Cacheops Prefix-Based Hash Tagging Test")
    print("=" * 60)

    test_prefix_hash_tagging()
    test_queryset_prefix()
    test_cache_key_generation()
    test_conj_keys()
    test_without_cluster()

    print(f"\n{'='*60}")
    print("All tests completed!")
    print("If all tests show ✅, your prefix-based hash tagging is working correctly.")
    print("=" * 60)


if __name__ == "__main__":
    main()

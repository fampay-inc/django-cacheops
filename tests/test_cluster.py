from unittest import TestCase, skipIf
from unittest.mock import patch, MagicMock
import django
from django.test import override_settings

try:
    from redis.cluster import RedisCluster
    REDIS_CLUSTER_AVAILABLE = True
except ImportError:
    REDIS_CLUSTER_AVAILABLE = False

from cacheops.conf import settings
from cacheops.redis import redis_client


@skipIf(not REDIS_CLUSTER_AVAILABLE, "redis-py-cluster not installed")
class RedisClusterTest(TestCase):
    """
    Tests for Redis Cluster support.
    These tests mock the Redis Cluster client to avoid requiring a real cluster.
    """

    def setUp(self):
        # Save original settings
        self.original_redis = settings.CACHEOPS_REDIS
        self.original_redis_cluster = getattr(settings, 'CACHEOPS_REDIS_CLUSTER', {})
        self.original_insideout = settings.CACHEOPS_INSIDEOUT

        # Clear redis_client cached property
        if hasattr(redis_client, '_setup_done'):
            delattr(redis_client, '_setup_done')

    def tearDown(self):
        # Restore original settings
        settings.CACHEOPS_REDIS = self.original_redis
        settings.CACHEOPS_REDIS_CLUSTER = self.original_redis_cluster
        settings.CACHEOPS_INSIDEOUT = self.original_insideout

        # Clear redis_client cached property
        if hasattr(redis_client, '_setup_done'):
            delattr(redis_client, '_setup_done')

    @override_settings(CACHEOPS_REDIS={})
    @patch('cacheops.redis.RedisCluster')
    def test_cluster_config_dict(self, MockRedisCluster):
        """Test that Redis Cluster is properly configured with a dict config."""
        # Configure cluster with dict
        settings.CACHEOPS_REDIS_CLUSTER = {
            'startup_nodes': [{'host': 'localhost', 'port': 7000}],
            'skip_full_coverage_check': True,
        }
        settings.CACHEOPS_INSIDEOUT = True

        # Access redis_client to trigger initialization
        client = redis_client._setup()

        # Verify RedisCluster was created with the right config
        MockRedisCluster.assert_called_once_with(
            startup_nodes=[{'host': 'localhost', 'port': 7000}],
            skip_full_coverage_check=True,
        )

    @override_settings(CACHEOPS_REDIS={})
    @patch('cacheops.redis.RedisCluster')
    def test_cluster_config_url(self, MockRedisCluster):
        """Test that Redis Cluster is properly configured with a URL."""
        # Configure cluster with URL
        settings.CACHEOPS_REDIS_CLUSTER = "redis://localhost:7000"
        settings.CACHEOPS_INSIDEOUT = True

        # Access redis_client to trigger initialization
        client = redis_client._setup()

        # Verify RedisCluster.from_url was called
        MockRedisCluster.from_url.assert_called_once_with("redis://localhost:7000")

    @override_settings(CACHEOPS_REDIS={})
    def test_insideout_requirement(self):
        """Test that inside out mode is required for Redis Cluster."""
        # Configure cluster without inside out mode
        settings.CACHEOPS_REDIS_CLUSTER = {
            'startup_nodes': [{'host': 'localhost', 'port': 7000}],
        }
        settings.CACHEOPS_INSIDEOUT = False

        # Access redis_client should raise ImproperlyConfigured
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured) as cm:
            client = redis_client._setup()

        self.assertIn("CACHEOPS_INSIDEOUT must be set to True", str(cm.exception))

    @override_settings(CACHEOPS_REDIS={})
    def test_mutually_exclusive_configs(self):
        """Test that Redis and Redis Cluster configs can't be used together."""
        # Configure both Redis and Redis Cluster
        settings.CACHEOPS_REDIS = {'host': 'localhost'}
        settings.CACHEOPS_REDIS_CLUSTER = {
            'startup_nodes': [{'host': 'localhost', 'port': 7000}],
        }
        settings.CACHEOPS_INSIDEOUT = True

        # Access redis_client should raise ImproperlyConfigured
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured) as cm:
            client = redis_client._setup()

        self.assertIn("mutually exclusive", str(cm.exception))

    @override_settings(CACHEOPS_REDIS={})
    @patch('cacheops.redis.RedisCluster')
    def test_key_tagging(self, MockRedisCluster):
        """Test that key tagging is used with Redis Cluster."""
        # Setup a mock Redis Cluster client
        mock_client = MagicMock()
        MockRedisCluster.return_value = mock_client

        # Configure cluster
        settings.CACHEOPS_REDIS_CLUSTER = {
            'startup_nodes': [{'host': 'localhost', 'port': 7000}],
        }
        settings.CACHEOPS_INSIDEOUT = True

        # Initialize redis client
        client = redis_client._setup()

        # Import and use the function that generates keys
        from cacheops.getset import dnfs_to_conj_keys

        # Create a sample DNF
        cond_dnfs = {
            'test_table': [{'field1': 'value1', 'field2': 'value2'}]
        }

        # Generate keys
        keys = dnfs_to_conj_keys('prefix:', cond_dnfs)

        # Verify key contains the proper tagging format
        self.assertEqual(len(keys), 1)
        self.assertIn('conj:{test_table}:', keys[0])

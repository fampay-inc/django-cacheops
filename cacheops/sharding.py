from funcy import cached_property
from django.core.exceptions import ImproperlyConfigured

from .conf import settings


def get_prefix(**kwargs):
    prefix = settings.CACHEOPS_PREFIX(PrefixQuery(**kwargs))

    # Add hash tag for Redis Cluster if configured
    if hasattr(settings, 'CACHEOPS_REDIS_CLUSTER') and settings.CACHEOPS_REDIS_CLUSTER:
        query = PrefixQuery(**kwargs)
        if hasattr(query, 'tables') and query.tables:
            # Use the first table name as the hash tag
            table_name = query.tables[0]
            # Sanitize table name for hash tag
            safe_table = ''.join(c for c in table_name if c.isalnum() or c == '_') or 'default'
            prefix = f"{{{safe_table}}}:{prefix}" if prefix else f"{{{safe_table}}}:"
        elif hasattr(query, '_queryset') and query._queryset:
            # Extract table from queryset
            table_name = query._queryset.model._meta.db_table
            safe_table = ''.join(c for c in table_name if c.isalnum() or c == '_') or 'default'
            prefix = f"{{{safe_table}}}:{prefix}" if prefix else f"{{{safe_table}}}:"
        elif hasattr(query, '_cond_dnfs') and query._cond_dnfs:
            # Extract from cond_dnfs
            table_name = next(iter(query._cond_dnfs.keys()))
            safe_table = ''.join(c for c in table_name if c.isalnum() or c == '_') or 'default'
            prefix = f"{{{safe_table}}}:{prefix}" if prefix else f"{{{safe_table}}}:"

    return prefix


class PrefixQuery(object):
    def __init__(self, **kwargs):
        assert set(kwargs) <= {'func', '_queryset', '_cond_dnfs', 'dbs', 'tables'}
        kwargs.setdefault('func', None)
        self.__dict__.update(kwargs)

    @cached_property
    def dbs(self):
        return [self._queryset.db]

    @cached_property
    def db(self):
        if len(self.dbs) > 1:
            dbs_str = ', '.join(self.dbs)
            raise ImproperlyConfigured('Single db required, but several used: ' + dbs_str)
        return self.dbs[0]

    # TODO: think if I should expose it and how. Same for queryset.
    @cached_property
    def _cond_dnfs(self):
        return self._queryset._cond_dnfs

    @cached_property
    def tables(self):
        return list(self._cond_dnfs)

    @cached_property
    def table(self):
        if len(self.tables) > 1:
            tables_str = ', '.join(self.tables)
            raise ImproperlyConfigured('Single table required, but several used: ' + tables_str)
        return self.tables[0]

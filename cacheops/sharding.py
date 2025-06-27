from funcy import cached_property
from django.core.exceptions import ImproperlyConfigured

from .conf import settings


def get_prefix(**kwargs):
    prefix = settings.CACHEOPS_PREFIX(PrefixQuery(**kwargs))

    # Add hash tag for Redis Cluster if configured
    if hasattr(settings, 'CACHEOPS_REDIS_CLUSTER') and settings.CACHEOPS_REDIS_CLUSTER:
        query = PrefixQuery(**kwargs)
        table_name = None

        # Try to extract table name from different sources
        if hasattr(query, 'tables') and query.tables:
            table_name = query.tables[0]
        elif hasattr(query, '_queryset') and query._queryset:
            table_name = query._queryset.model._meta.db_table
        elif hasattr(query, '_cond_dnfs') and query._cond_dnfs:
            # Handle both dict format and list of tuples format
            if isinstance(query._cond_dnfs, dict):
                table_name = next(iter(query._cond_dnfs.keys()))
            elif isinstance(query._cond_dnfs, list) and query._cond_dnfs:
                # _cond_dnfs is a list of tuples like [(table_name, conditions)]
                table_name = query._cond_dnfs[0][0]
        elif 'tables' in kwargs and kwargs['tables']:
            # Direct tables parameter
            table_name = kwargs['tables'][0]

        if table_name:
            # Sanitize table name for hash tag
            safe_table = ''.join(c for c in str(table_name) if c.isalnum() or c == '_') or 'default'
            prefix = f"{{{safe_table}}}:{prefix}" if prefix else f"{{{safe_table}}}:"

    return prefix


class PrefixQuery(object):
    def __init__(self, **kwargs):
        assert set(kwargs) <= {'func', '_queryset', '_cond_dnfs', 'dbs', 'tables'}
        kwargs.setdefault('func', None)
        # Handle _cond_dnfs being passed directly
        if '_cond_dnfs' in kwargs:
            self._cond_dnfs_direct = kwargs.pop('_cond_dnfs')
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
        # Check if _cond_dnfs was passed directly
        if hasattr(self, '_cond_dnfs_direct'):
            return self._cond_dnfs_direct
        return self._queryset._cond_dnfs

    @cached_property
    def tables(self):
        if isinstance(self._cond_dnfs, dict):
            return list(self._cond_dnfs.keys())
        elif isinstance(self._cond_dnfs, list):
            # Handle list of tuples format [(table_name, conditions)]
            return [item[0] for item in self._cond_dnfs]
        else:
            return []

    @cached_property
    def table(self):
        if len(self.tables) > 1:
            tables_str = ', '.join(self.tables)
            raise ImproperlyConfigured('Single table required, but several used: ' + tables_str)
        return self.tables[0]

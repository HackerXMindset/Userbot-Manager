import time


class SourceCacheMixin:
    """Cache helpers reused by multiple mixins."""

    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)."""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds

    async def get_cached_sources(self):
        """Get sources with caching."""
        if self.is_fresh("sources"):
            return self.cache["sources"]

        sources = await self.source_model.get_all_sources()
        self.cache["sources"] = sources
        self.cache_time["sources"] = time.time()
        return sources

    async def get_cached_groups(self):
        """Get groups with caching."""
        if self.is_fresh("groups"):
            return self.cache["groups"]

        groups = await self.group_model.get_groups_with_stats()
        self.cache["groups"] = groups
        self.cache_time["groups"] = time.time()
        return groups

    def clear_cache(self):
        """Clear all cached data."""
        self.cache.clear()
        self.cache_time.clear()

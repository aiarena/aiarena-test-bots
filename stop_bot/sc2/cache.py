from collections import Counter
from functools import wraps


def cache_forever(f):
    f.cache = {}

    @wraps(f)
    def inner(*args):
        if args not in f.cache:
            f.cache[args] = f(*args)
        return f.cache[args]

    return inner

def property_cache_forever(f):
    @wraps(f)
    def inner(self):
        property_cache = "_cache_" + f.__name__
        cache_updated = hasattr(self, property_cache)
        if not cache_updated:
            setattr(self, property_cache, f(self))
        cache = getattr(self, property_cache)
        return cache

    return property(inner)


def property_cache_once_per_frame(f):
    """ This decorator caches the return value for one game loop,
    then clears it if it is accessed in a different game loop.
    Only works on properties of the bot object, because it requires
    access to self.state.game_loop """

    @wraps(f)
    def inner(self):
        property_cache = "_cache_" + f.__name__
        state_cache = "_frame_" + f.__name__
        cache_updated = hasattr(self, property_cache) and getattr(self, state_cache, None) == self.state.game_loop
        if not cache_updated:
            setattr(self, property_cache, f(self))
            setattr(self, state_cache, self.state.game_loop)

        cache = getattr(self, property_cache)
        should_copy = type(cache).__name__ == "Units" or isinstance(cache, (list, set, dict, Counter))
        if should_copy:
            return cache.copy()
        return cache

    return property(inner)


def property_immutable_cache(f):
    @wraps(f)
    def inner(self):
        if f.__name__ not in self.cache:
            self.cache[f.__name__] = f(self)
        return self.cache[f.__name__]

    return property(inner)


def property_mutable_cache(f):
    @wraps(f)
    def inner(self):
        if f.__name__ not in self.cache:
            self.cache[f.__name__] = f(self)
        return self.cache[f.__name__].copy()

    return property(inner)

import os

from zappa.async import task

def memoize(func):
    def decorator_memoize(*key):
        if os.environ.get('PYTEST_CURRENT_TEST'):
            return func(*key)
        if key not in func.__dict__:
            func.__dict__[key] = func(*key)
        return func.__dict__[key]
    return decorator_memoize

import os

from multiprocessing import Process

def memoize(func):
    def decorator_memoize(*key):
        if os.environ.get('PYTEST_CURRENT_TEST'):
            return func(*key)
        if key not in func.__dict__:
            func.__dict__[key] = func(*key)
        return func.__dict__[key]
    return decorator_memoize

def task(func):
    def decorator_task(*args, **kwargs):
        if os.environ.get('PYTEST_CURRENT_TEST'):
            return func(*args, **kwargs)
        p = Process(target=func, args=args, kwargs=kwargs)
        p.start()
    return decorator_task

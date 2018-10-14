import os

REDIS_URL = 'redis://%s:6379' % os.environ['REDIS_HOST']

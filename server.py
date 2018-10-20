from gevent import monkey; monkey.patch_all()

import os
import sys
sys.stdout = sys.stderr  # Redirect output to stderr.

from app import app
from gevent.pywsgi import WSGIServer

if __name__ == '__main__':
    WSGIServer(('0.0.0.0', os.environ.get('PORT', 5000)), app).serve_forever()

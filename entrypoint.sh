#!/bin/bash

# mkdir -p /shared/app/etc/nginx/conf.d/

# cp /code/default.conf /shared/app/etc/nginx/conf.d/

# uwsgi --ini uwsgi.ini
flask run -h 0.0.0.0 -p 8000
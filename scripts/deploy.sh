#!/usr/bin/env bash -x

set -e

ROOT_PASSWORD=$1

BRANCH=feature/leave-lambda
FLASK_ENV=production
FLASK_INSTANCE=production.py
MRTALLYMAN="sudo -sHu mrtallyman"

if ! dpkg -s mysql-server > /dev/null; then
  sudo apt update -y
  sudo apt install -y mysql-server mysql-client
fi

cd ~mrtallyman

if [ ! -e mrtallyman ]; then
  $MRTALLYMAN git clone git@github.com:datashaman/mrtallyman.git
fi

cd mrtallyman

$MRTALLYMAN git checkout $BRANCH
$MRTALLYMAN git pull --ff-only

if [ ! -e .env ]; then
  echo "Enter the MySQL host: "
  read MYSQL_HOST

  echo "Enter the MySQL DB: "
  read MYSQL_DB

  echo "Enter the MySQL user: "
  read MYSQL_USER

  echo "Enter the MySQL password: "
  read MYSQL_PASSWORD

  echo "Enter the Slack API Token: "
  read SLACK_API_TOKEN

  echo "Enter the Slack Client ID: "
  read SLACK_CLIENT_ID

  echo "Enter the Slack Client Secret: "
  read SLACK_CLIENT_SECRET

  echo "Enter the Slack Signing Secret: "
  read SLACK_SIGNING_SECRET

  $MRTALLYMAN cp .env.example .env
  $MRTALLYMAN sed -i "s/FLASK_ENV=development/FLASK_ENV=production/
          s/FLASK_INSTANCE=development.py/FLASK_INSTANCE=${FLASK_INSTANCE}/
          s/MYSQL_DB=db/MYSQL_DB=${MYSQL_DB}/
          s/MYSQL_HOST=host/MYSQL_HOST=${MYSQL_HOST}/
          s/MYSQL_PASS=password/MYSQL_PASSWORD=${MYSQL_PASSWORD}/
          s/MYSQL_USER=user/MYSQL_USER=${MYSQL_USER}/
          s/SLACK_API_TOKEN = '1234567890'/SLACK_API_TOKEN = '${SLACK_API_TOKEN}'/
          s/SLACK_CLIENT_ID = '1234567890'/SLACK_CLIENT_ID = '${SLACK_CLIENT_ID}'/
          s/SLACK_CLIENT_SECRET = '1234567890'/SLACK_CLIENT_SECRET = '${SLACK_CLIENT_SECRET}'/
          s/SLACK_SIGNING_SECRET = '1234567890'/SLACK_SIGNING_SECRET = '${SLACK_CLIENT_ID}'/" .env
fi

source .env

sudo mysql -e "CREATE DATABASE IF NOT EXISTS ${MYSQL_DB}"
sudo mysql -e "CREATE USER IF NOT EXISTS '${MYSQL_USER}'@'$(hostname)' IDENTIFIED BY '${MYSQL_PASSWORD}'"
sudo mysql -e "GRANT ALL PRIVILEGES ON ${MYSQL_DB}.* TO '${MYSQL_USER}'@'$(hostname)'"
sudo mysql -e "FLUSH PRIVILEGES"

if ! dpkg -s python3 > /dev/null; then
  sudo apt install python3 pip3-python
fi

if ! dpkg -s virtualenvwrapper > /dev/null; then
  sudo apt install virtualenvwrapper
fi

$MRTALLYMAN bash -c "source /etc/bash_completion.d/virtualenvwrapper && mkvirtualenv --clear -p /usr/bin/python3 -r requirements.txt mrtallyman"
$MRTALLYMAN bash -c "source /etc/bash_completion.d/virtualenvwrapper && workon mrtallyman && pip install uwsgi"

if ! dpkg -s nginx > /dev/null; then
  sudo apt install nginx
fi

sudo rm -f /etc/nginx/sites-enabled/default

if [ ! -e /etc/nginx/sites-enabled/mrtallyman.conf ]; then
  sudo ln -sf ~mrtallyman/mrtallyman/etc/nginx.conf /etc/nginx/sites-available/mrtallyman.conf
  sudo ln -sf /etc/nginx/sites-available/mrtallyman.conf /etc/nginx/sites-enabled/mrtallyman.conf
  sudo /etc/init.d/nginx restart
fi

sudo mkdir -p /var/log/mrtallyman
sudo chown -R www-data:www-data /var/log/mrtallyman ~mrtallyman/mrtallyman

if [ ! -e /etc/systemd/system/mrtallyman.service ]; then
  sudo ln -sf ~mrtallyman/mrtallyman/etc/uwsgi.service /etc/systemd/system/mrtallyman.uwsgi
  sudo systemctl enable mrtallyman.service
fi

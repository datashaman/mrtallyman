#!/usr/bin/env bash

set -e

if [ $# -lt 1 ]; then
  echo "Usage: $0 branch"
fi

DEPLOY_BRANCH=$1
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

sudo chown -R mrtallyman:mrtallyman .

$MRTALLYMAN git fetch
$MRTALLYMAN git checkout origin/$DEPLOY_BRANCH

if [ ! -e .env ]; then
  echo "Enter the Google Analytics ID: "
  read GOOGLE_ANALYTICS_ID

  echo "Enter the MySQL host: "
  read MYSQL_HOST

  echo "Enter the MySQL port: "
  read MYSQL_PORT

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
  $MRTALLYMAN sed -i "
    s/GOOGLE_ANALYTICS_ID=db/GOOGLE_ANALYTICS_ID=${GOOGLE_ANALYTICS_ID}/
    s/MYSQL_DB=db/MYSQL_DB=${MYSQL_DB}/
    s/MYSQL_HOST=host/MYSQL_HOST=${MYSQL_HOST}/
    s/MYSQL_PASS=password/MYSQL_PASSWORD=${MYSQL_PASSWORD}/
    s/MYSQL_PORT=3306/MYSQL_PORT=${MYSQL_PORT}/
    s/MYSQL_USER=user/MYSQL_USER=${MYSQL_USER}/
    s/SLACK_API_TOKEN=1234567890/SLACK_API_TOKEN=${SLACK_API_TOKEN}/
    s/SLACK_CLIENT_ID=1234567890/SLACK_CLIENT_ID=${SLACK_CLIENT_ID}/
    s/SLACK_CLIENT_SECRET=1234567890/SLACK_CLIENT_SECRET=${SLACK_CLIENT_SECRET}/
    s/SLACK_SIGNING_SECRET=1234567890/SLACK_SIGNING_SECRET=${SLACK_CLIENT_ID}/
  " .env
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

if [ ! -e ~mrtallyman/.virtualenvs/mrtallyman ]; then
  $MRTALLYMAN bash -c "source /etc/bash_completion.d/virtualenvwrapper && mkvirtualenv -p /usr/bin/python3 mrtallyman"
fi

$MRTALLYMAN bash -c "source /etc/bash_completion.d/virtualenvwrapper && workon mrtallyman && pip install -r requirements.txt uwsgi"

if ! dpkg -s nginx > /dev/null; then
  sudo apt install nginx
fi

if [ -e /etc/nginx/sites-enabled/default ]; then
  sudo rm -f /etc/nginx/sites-enabled/default
fi

if [ ! -e /etc/nginx/sites-enabled/mrtallyman.conf ]; then
  sudo ln -sf ~mrtallyman/mrtallyman/etc/nginx.conf /etc/nginx/sites-available/mrtallyman.conf
  sudo ln -sf /etc/nginx/sites-available/mrtallyman.conf /etc/nginx/sites-enabled/mrtallyman.conf
  sudo /etc/init.d/nginx restart
fi

if [ ! -e /etc/systemd/system/mrtallyman.service ]; then
  sudo ln -sf ~mrtallyman/mrtallyman/etc/mrtallyman.service /etc/systemd/system/mrtallyman.service
  sudo systemctl daemon-reload
  sudo systemctl enable mrtallyman.service
  sudo systemctl restart mrtallyman.service
fi

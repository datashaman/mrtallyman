PIP = pip3
PORT = 5000
STAGE = dev

MYSQL_ARGS = -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" -h"$(MYSQL_HOST)" -P"$(MYSQL_PORT)"
MYSQL_CMD = mysql $(MYSQL_ARGS)

pip-install-requirements:
	$(PIP) install -r requirements.txt

pip-install:
	pip install -r requirements.txt

pip-install-testing:
	pip install -r requirements-testing.txt

dev-run:
	flask run -p $(PORT)

dev-ngrok:
	ngrok http --region eu $(PORT)

dynamodb-local:
	scripts/dynamodb-local.sh

test:
	pytest -sv -x tests/

test-fast:
	pytest -sv --ff -x tests/

test-coverage:
	pytest -sv --cov-report term-missing --cov=app --fulltrace tests/

clean:
	rm -rf .coverage .pytest_cache/
	find . -type f -name *.pyc -delete
	find . -type d -name __pycache__  -delete

mysql:
	$(MYSQL_CMD) "$(MYSQL_DB)"

mysql-recreate:
	$(MYSQL_CMD) -e "drop database if exists $(MYSQL_DB); create database $(MYSQL_DB);"

deploy:
	cat scripts/deploy.sh | ssh $(DEPLOY_HOST) 'cat>deploy.sh'
	ssh $(DEPLOY_HOST) "bash deploy.sh $(DEPLOY_BRANCH)"

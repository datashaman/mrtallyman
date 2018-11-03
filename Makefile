PIP = pip3
PORT = 5000
STAGE = dev

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
	mysql -u$(MYSQL_USER) -p$(MYSQL_PASSWORD) -h$(MYSQL_HOST) $(MYSQL_DB)

mysql-recreate:
	mysqladmin -u$(MYSQL_USER) -p$(MYSQL_PASSWORD) -h$(MYSQL_HOST) drop $(MYSQL_DB)
	mysqladmin -u$(MYSQL_USER) -p$(MYSQL_PASSWORD) -h$(MYSQL_HOST) create $(MYSQL_DB)

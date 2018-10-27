#!/usr/bin/env bash
#
# This downloads and starts a DynamoDB local server for development and testing.
#
# Meant to be run from the base of the project like so:
#
#     scripts/dynamodb-local.sh

mkdir -p .cache
cd .cache

if [ ! -e DynamoDBLocal.jar ]; then
  if [ ! -e dynamodb_local_latest.tar.gz ]; then
    wget https://s3.eu-central-1.amazonaws.com/dynamodb-local-frankfurt/dynamodb_local_latest.tar.gz
  fi
  tar xzf dynamodb_local_latest.tar.gz
fi

exec java -Djava.library.path=DynamoDBLocal_lib -jar DynamoDBLocal.jar -inMemory

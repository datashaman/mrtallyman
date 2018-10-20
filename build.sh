#!/usr/bin/env bash

APP=$(pwd)
BUILD=$APP/build

rm -rf $BUILD
mkdir $BUILD

cd $VIRTUAL_ENV/lib/python3.6/site-packages
cp -a * $BUILD
find $BUILD -type d -name '*-info' -exec rm -rf {} +
find $BUILD -type d -name 'tests' -exec rm -rf {} +
rm -rf $BUILD/boto3
rm -rf $BUILD/botocore
rm -rf $BUILD/dateutil
rm -rf $BUILD/docutils
rm -rf $BUILD/jinja2
rm -rf $BUILD/jmespath
rm -rf $BUILD/pip
rm -rf $BUILD/s3transfer
rm -rf $BUILD/setuptools

cd $APP
python -m py_compile *.py
cp -a __pycache__ $BUILD
find $BUILD -type f -name '*.pyc' | while read f; do n=$(echo $f | sed 's/__pycache__\///' | sed 's/.cpython-36//'); cp $f $n; done;
find $BUILD -type d -a -name '__pycache__' -print0 | xargs -0 rm -rf
find $BUILD -type f -a -name '*.py' -print0 | xargs -0 rm -f

cd $BUILD
zip -r9 $APP/build.zip .

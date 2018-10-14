FROM python:3.6-alpine
ADD . /app
WORKDIR /app
RUN pip install -r requirements.txt
ENV FLASK_APP robocop.py
CMD ["flask", "run", "-h", "0.0.0.0"]

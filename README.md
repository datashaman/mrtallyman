# robocop

Slack responder that handles events and commands. Uses gipc and gevent to spawn long-running processes.

Setup an app on Slack, subscribe to events (and setup the needed OAuth scopes), or create a command.

Change _app.py_ to handle specific events and commands, run ngrok to expose an endpoint during development.

Installation:

    mkvirtualenv -r requirements.txt

Configuration:

    cp .env.example .env

Running:

    python server.py

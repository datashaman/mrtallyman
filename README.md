# robocop

Slack responder that handles events and commands. Uses gipc and gevent to spawn long-running processes.

Setup an app and a bot on Slack, subscribe to events (and setup the needed OAuth scopes), or create a command.

Change _app.py_ to handle specific events and commands, run ngrok to expose an endpoint during development.

Installation:

    mkvirtualenv -r requirements.txt

Configuration:

    cp .env.example .env

Running:

    python server.py

In your Flask application decorate functions as follows:

    import robocop

    @robocop.on('app_mention')
    def app_mention_event(event):
        # Do your thing.
        pass

    @robocop.on('/robocop')
    def robocop_command(form):
        # Do your thing.
        return 'Immediate response'

The _on_ decorator is for events and commands. If the parameter starts with _/_, it is handled like a command, otherwise as an event.

For event handlers, the parameter is the event type. All event handlers are run in a separate process and the return results are ignored.

You may have multiple event handlers for the same event type.

If no event handler exists for a specific event type, the endpoint aborts with HTTP status code _400_. If an event handler exists, it returns a blank response with HTTP status _200_.

For command handlers, the parameter is the command prefixed with _/_. The command handler is run in the same process as the web server. If you want to spawn a new process to deal with long-running calculation use `gipc.start_process`.

There can be only be one command handler per command, and you are advised to return an immediate response to let the user know something is taking place.

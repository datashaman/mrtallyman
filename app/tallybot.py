import hashlib
import hmac
import time

handlers = {}

def on(name):
    def decorator_on(func):
        global handlers

        if name[0] == '/':
            handlers[name] = func
        else:
            if name not in handlers:
                handlers[name] = []
            found = False
            for handler in handlers[name]:
                if (handler.__module__, handler.__name__) == (func.__module__, func.__name__):
                    found = True
                    break
            if not found:
                handlers[name].append(func)
        return func
    return decorator_on

def handle_command(form):
    command = form.get('command')
    if command in handlers:
        return handlers[command](form)
    return False

def handle_event(payload):
    event_type = payload['event']['type']

    if event_type in handlers:
        for func in handlers[event_type]:
            if func(payload) == False:
                return False
        return True
    return False

def generate_signature(timestamp, slack_signing_secret, data):
    key = bytes(slack_signing_secret, 'utf-8')
    msg = ('v0:' + timestamp + ':' + data).encode('utf-8')
    return 'v0=' + hmac.new(key, msg, hashlib.sha256).hexdigest()

def valid_request(app, request):
    timestamp = request.headers['X-Slack-Request-Timestamp']
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    signature = generate_signature(timestamp, app.config['SLACK_SIGNING_SECRET'], request.get_data().decode())
    return hmac.compare_digest(signature, request.headers['X-Slack-Signature'])

def handle(app, request):
    if valid_request(app, request):
        if 'command' in request.form:
            return handle_command(request.form)

        payload = request.get_json()

        if payload['type'] == 'event_callback':
            return handle_event(payload)
        elif payload['type'] == 'url_verification':
            return payload['challenge']
    return False

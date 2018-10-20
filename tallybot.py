import hashlib
import hmac
import os
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

def valid_request(request):
    timestamp = request.headers['X-Slack-Request-Timestamp']
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    key = bytes(os.environ['SLACK_SIGNING_SECRET'], 'utf-8')
    msg = ('v0:' + timestamp + ':' + request.get_data().decode()).encode('utf-8')
    signature = 'v0=' + hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, request.headers['X-Slack-Signature'])

def handle(request):
    if valid_request(request):
        if 'command' in request.form:
            return handle_command(request.form)

        payload = request.get_json()

        if payload['type'] == 'event_callback':
            return handle_event(payload)
        elif payload['type'] == 'url_verification':
            return payload['challenge']
    return False

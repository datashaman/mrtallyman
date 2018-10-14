import calendar
import dateutil.parser
import hashlib
import hmac
import json
import logging
import os
import requests
import sys
import time

from flask import Flask, abort, request
from redis import Redis
from rq import Queue
from slackclient import SlackClient
from wit import Wit

module = sys.modules[__name__]
queue = Queue(connection=Redis(host=os.environ['REDIS_HOST']))
slack = SlackClient(os.environ['SLACK_API_TOKEN'])
wit = Wit(os.environ['WIT_TOKEN'])

app = Flask(__name__)
app.logger.level = logging.DEBUG

bot_id = slack.api_call('auth.test')['user_id']

def dispatch(data, enqueue=True):
    function = data['type']
    if hasattr(module, function):
        if enqueue:
            queue.enqueue(getattr(module, function), data)
            return 'OK'
        else:
            return getattr(module, function)(data)
    else:
        app.logger.warn('%s not handled', function)
        abort(400)

def valid_request():
    timestamp = request.headers['X-Slack-Request-Timestamp']
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    key = bytes(os.environ['SLACK_SIGNING_SECRET'], 'utf-8')
    msg = ('v0:' + timestamp + ':' + request.data.decode()).encode('utf-8')
    signature = 'v0=' + hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, request.headers['X-Slack-Signature'])

# Callback handlers
def event_callback(payload):
    event = payload['event']
    if event['type'] == 'message' and event.get('subtype') == 'bot_message':
        return 'OK'
    return dispatch(event)

def url_verification(payload):
    return payload['challenge']

def strip_bot_id(text):
    return text.replace('<@%s>' % bot_id, '')

# Event handlers
def app_mention(event):
    wit_response = wit.message(strip_bot_id(event['text']))

    if wit_response['entities']['intent'][0]['value'] == 'weather':
        location = wit_response['entities']['location'][0]
        coords = location['resolved']['values'][0]['coords']
        url = 'https://api.darksky.net/forecast/%s/%s,%s' % (os.environ['DARK_SKY_KEY'],
                                                             coords['lat'],
                                                             coords['long'])
        if 'datetime' in wit_response['entities']:
            when = dateutil.parser.parse(wit_response['entities']['datetime'][0]['value'])
            timestamp = calendar.timegm(when.utctimetuple())
            url += ',%s' % timestamp

        response = requests.get(url)
        weather = response.json()
        print(json.dumps(weather, indent=4))
        slack.api_call(
            'chat.postMessage',
            channel=event['channel'],
            text=weather['currently']['summary'],
        )

    return 'OK'

def message(event):
    slack.api_call(
        'chat.postMessage',
        channel=event['channel'],
        text=event['text']
    )
    return 'OK'

@app.route('/', methods=['POST'])
def home():
    if valid_request():
        payload = request.get_json()
        app.logger.debug('payload %s', payload)
        enqueue = payload['type'] not in ['event_callback', 'url_verification']
        return dispatch(payload, enqueue)
    abort(400)

import robocop
import os

from flask import Flask, abort, request
from slackclient import SlackClient

slack = SlackClient(os.environ['SLACK_API_TOKEN'])

app = Flask(__name__)

@robocop.on('/robocop')
def command(form):
    return 'Your wish is my command'

@robocop.on('app_mention')
def echo(event):
    if event.get('subtype') != 'bot_message':
        slack.api_call(
            'chat.postMessage',
            channel=event['channel'],
            text=event['text']
        )

@app.route('/', methods=['POST'])
def home():
    response = robocop.handle(request)

    if response is True:
        return ''
    elif response is False:
        abort(400)

    return response

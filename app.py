import re
import robocop
import os

from flask import Flask, abort, request
from kev import Document, CharProperty, IntegerProperty
from kev.loading import KevHandler
from slackclient import SlackClient

kev_handler = KevHandler({
    's3': {
        'backend': 'kev.backends.s3.db.S3DB',
        'connection': {
            'bucket': os.environ['KEV_S3_BUCKET'],
        },
    },
})

class BananaLog(Document):
    sender = CharProperty(required=True, index=True)
    recipient = CharProperty(required=True, index=True)
    amount = IntegerProperty(default_value=1, min_value=1, max_value=5)

    def __unicode__(self):
        return '%s gave %d bananas to %s' % (self.sender, self.amount, self.recipient)

    class Meta:
        use_db = 's3'
        handler = kev_handler

# log = BananaLog(sender='sender', recipient='recipient', amount=1)
# log.save()

slack = SlackClient(os.environ['SLACK_API_TOKEN'])
bot_id = slack.api_call('auth.test')['user_id']

app = Flask(__name__)

@robocop.on('app_mention')
def app_mention_event(event):
    if event.get('subtype') != 'bot_message':
        if event['text'] == '<@%s> leaderboard' % bot_id:
            logs = list(BananaLog.all())
            recipients = {}

            for log in logs:
                if log.recipient not in recipients:
                    recipients[log.recipient] = 0
                recipients[log.recipient] += log.amount

            leaderboard = ''
            for index, recipient in enumerate(sorted(recipients, key=recipients.get, reverse=True)[:10]):
                leaderboard += '%d. <@%s> - %d\n' % (index+1, recipient, recipients[recipient])

            slack.api_call(
                'chat.postMessage',
                channel=event['channel'],
                text=leaderboard
            )

@robocop.on('message')
def message_event(event):
    if event['channel_type'] == 'channel' and event.get('subtype') != 'bot_message':
        sender = event['user']
        bananas = re.findall(r':banana:', event['text'])
        if bananas:
            for recipient in re.findall(r'<@([A-Z0-9]+)>', event['text']):
                log = BananaLog(sender=sender, recipient=recipient, amount=len(bananas))
                log.save()

@app.route('/', methods=['POST'])
def home():
    response = robocop.handle(request)

    if response is True:
        return ''
    elif response is False:
        abort(400)

    return response

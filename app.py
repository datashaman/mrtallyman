import boto3
import operator
import re
import random
import tallybot
import os
import settings
import sys
sys.stdout = sys.stderr

from botocore.exceptions import ClientError
from flask import Flask, abort, request
from slackclient import SlackClient
from zappa.async import task

app = Flask(__name__)

EMOJI = ':banana:'

dynamodb = boto3.resource('dynamodb')

def delete_table(event=None):
    app.logger.debug('Deleting table')
    post_message(event, 'Deleting table')

    try:
        table.delete()
        table.wait_until_not_exists()
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            app.logger.debug('Table is deleting')
            post_message(event, 'Table is deleting')
            table.wait_until_not_exists()
        elif exc.response['Error']['Code'] != 'ResourceNotFoundException':
            app.logger.debug('Table does not exist')
            post_message(event, 'Table does not exist')
            raise exc
    app.logger.debug('Table deleted')
    post_message(event, 'Table deleted')

def create_table(event=None):
    app.logger.debug('Creating table')
    post_message(event, 'Creating table')

    try:
        table = dynamodb.create_table(
            TableName=os.environ['DYNAMODB_TABLE'],
            KeySchema=[
                {
                    'AttributeName': 'user_id',
                    'KeyType': 'HASH',
                },
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'user_id',
                    'AttributeType': 'S',
                },
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 1,
                'WriteCapacityUnits': 1,
            }
        )
        table.wait_until_exists()
        app.logger.debug('Table created')
        post_message(event, 'Table created')
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            app.logger.debug('Table exists')
            post_message(event, 'Table exists')
            table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
        else:
            raise exc

    return table

def post_message(event, text):
    if event is not None:
        app.logger.debug('Sending message %s to channel %s', text, event['channel'])
        slack.api_call(
            'chat.postMessage',
            channel=event['channel'],
            text=text
        )

@task
def reset_table(event):
    global table

    response = slack.api_call(
        'users.info',
        user=event['user']
    )

    if response['user']['is_admin']:
        app.logger.debug('Resetting table')
        post_message(event, 'Resetting table')

        delete_table(event)
        table = create_table(event)
    else:
        post_message(event, "Nice try, buddy!")

table = create_table()

slack = SlackClient(os.environ['SLACK_API_TOKEN'])
auth_test = slack.api_call('auth.test')
bot_id = auth_test['user_id']

def generate_leaderboard(users, column='received'):
    leaderboard = []
    for index, user in enumerate(sorted(users, key=operator.itemgetter(column), reverse=True)[:10]):
        leaderboard.append('%d. <@%s> - %d %s' % (index+1, user['user_id'], user[column], EMOJI))
    return '\n'.join(leaderboard)

@task
def generate_leaderboards(event):
    try:
        table.wait_until_exists()
        response = table.scan()
        users = response['Items']
        if users:
            received = generate_leaderboard(users, 'received')
            given = generate_leaderboard(users, 'given')
            leaderboards = '*Received*\n\n%s\n\n*Given*\n\n%s' % (received, given)
        else:
            leaderboards = 'nothing to see here'
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            leaderboards = 'resetting, try again in a minute'
        else:
            raise exc

    post_message(event, leaderboards)

@tallybot.on('app_mention')
def app_mention_event(event):
    if event.get('subtype') != 'bot_message' and not event.get('edited'):
        if event['text'] == '<@%s> leaderboard' % bot_id:
            generate_leaderboards(event)

def generate_affirmation():
    return random.choice([
        'Accomplishment achieved!',
        'Brilliantly executed!',
        'Civilized.',
        'Completed.',
        'Decent.',
        'Dignified.',
        'Done.',
        'Effective immediately!',
        'Executed!',
        'Fitting!',
        'Nice.',
        'Okay.',
        'Perfect.',
        'Polite.',
        'Respectable.',
        'Seemly.',
        'Sexy!',
        'Success!',
        "That's great!",
        'Very suitable.',
        'Well done!',
    ])

def update_user(user_id, attribute, value):
    response = table.get_item(
        Key={
            'user_id': user_id,
        }
    )

    if 'Item' in response:
        user = response['Item']
        user[attribute] += value
        table.update_item(
            Key={
                'user_id': user_id,
            },
            UpdateExpression='SET %s = :value' % attribute,
            ExpressionAttributeValues={
                ':value': user[attribute],
            }
        )
    else:
        user = {'user_id': user_id, attribute: value}
        if attribute == 'received':
            user['given'] = 0
        else:
            user['received'] = 0
        table.put_item(Item=user)

    return user

def update_users(giver, recipients, count):
    table.wait_until_exists()

    report = []

    update_user(giver, 'given', count)

    for user_id in recipients:
        if user_id == giver:
            report.append('<@%s> no :banana: for you! (nice try, human)' % giver) 
        else:
            user = update_user(user_id, 'received', count)
            report.append('<@%s> has %d %s!' % (user_id, user['received'], EMOJI))

    return report

@task
def update_scores(event):
    if 'message' in event:
        message = event['message']
    else:
        message = event

    emojis = re.findall(EMOJI, message['text'])
    if emojis:
        recipients = re.findall(r'<@([A-Z0-9]+)>', message['text'])

        if recipients:
            report = update_users(event['user'], recipients, len(emojis))
            text = '%s %s' % (generate_affirmation(), ', '.join(report))
            post_message(event, text)

@tallybot.on('message')
def message_event(event):
    if event['channel_type'] == 'channel'and 'subtype' not in event:
        update_scores(event)

    elif event['channel_type'] == 'im' and event['text'] == 'reset!':
        reset_table(event)

    elif event['channel_type'] == 'im' and event['text'] == 'leaderboard':
        generate_leaderboards(event)

@app.route('/', methods=['POST'])
def home():
    response = tallybot.handle(request)

    if response is True:
        return ''
    elif response is False:
        abort(400)

    return response

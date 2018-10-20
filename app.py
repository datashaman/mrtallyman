import boto3
import functools
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

EMOJI = ':banana:'

app = Flask(__name__)
dynamodb = boto3.resource('dynamodb')

def memoize(func):
    def decorator_memoize(*key):
        if key not in func.__dict__:
            func.__dict__[key] = func(*key)
        return func.__dict__[key]
    return decorator_memoize

def app_log(message, level='debug'):
    getattr(app.logger, level)(message)

def team_log(team_id, message, channel=None, level='debug'):
    app_log('%s: %s' % (team_id, message))
    if channel:
        post_message(team_id, message, channel)

def get_table_name(suffix):
    return '%s-%s' % (os.environ['DYNAMODB_PREFIX'], suffix)

def create_config_table():
    table_name = get_table_name('config')
    app_log('Creating table %s' % table_name)

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'team_id',
                    'KeyType': 'HASH',
                },
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'team_id',
                    'AttributeType': 'S',
                },
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 1,
                'WriteCapacityUnits': 1,
            }
        )
        table.wait_until_exists()
        app_log('Table %s created' % table_name)
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            app_log('Table %s exists' % table_name)
            table = dynamodb.Table(table_name)
        else:
            raise exc

    return table

@memoize
def get_config_table():
    return create_config_table()

def update_local_token():
    if os.environ.get('SLACK_API_TOKEN'):
        token = os.environ['SLACK_API_TOKEN']
        client = SlackClient(token)
        auth_test = client.api_call('auth.test')

        if auth_test['ok']:
            table = get_config_table()

            response = table.get_item(
                Key={
                    'team_id': auth_test['team_id'],
                }
            )

            if 'Item' in response:
                config = response['Item']
                if config['token'] != token:
                    table.update_item(
                        Key={
                            'team_id': auth_test['team_id'],
                        },
                        UpdateExpression='UPDATE token = :token',
                        ExpressionAttributeValues={
                            ':token': token,
                        }
                    )
            else:
                table.put_item(
                    Item={
                        'team_id': auth_test['team_id'],
                        'token': token,
                    }
                )

update_local_token()

@memoize
def get_bot_id(team_id):
    response = get_client(team_id).api_call('auth.test')
    return response['user_id']

@memoize
def get_client(team_id):
    token = get_token(team_id)
    return SlackClient(token)

@memoize
def get_team_table(team_id):
    return create_team_table(team_id)

@memoize
def get_user_info(team_id, user_id):
    return get_client(team_id).api_call('users.info', user=user_id)

def team_table_exists(team_id):
    table_name = get_table_name(team_id)
    try:
        dynamodb.describe_table(TableName=table_name)
        return True
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ResourceNotFoundException':
            return False
        else:
            raise exc

def get_token(team_id):
    table = get_config_table()
    response = table.get_item(
        Key={
            'team_id': team_id,
        }
    )
    if 'Item' in response:
        return response['Item']['token']

def delete_team_table(team_id, channel):
    table_name = get_table_name(team_id)

    if not team_table_exists(team_id):
        team_log(team_id, 'Table %s is not there' % table_name, channel)
        return

    table = get_team_table(team_id, channel)
    team_log(team_id, 'Deleting table %s' % table_name, channel)

    try:
        table.delete()
        table.wait_until_not_exists()
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            team_log(team_id, 'Table %s is deleting' % table_name, channel)
            table.wait_until_not_exists()
        elif exc.response['Error']['Code'] != 'ResourceNotFoundException':
            team_log(team_id, 'Table %s does not exist' % table_name, channel)
            raise exc
    team_log(team_id, 'Table %s deleted' % table_name, channel)

def create_team_table(team_id, channel=None):
    table_name = get_table_name(team_id)
    team_log(team_id, 'Creating table %s' % table_name, channel)

    try:
        table = dynamodb.create_table(
            TableName=table_name,
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
        team_log(team_id, 'Table %s created' % table_name, channel)
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            team_log(team_id, 'Table %s exists' % table_name, channel)
            table = dynamodb.Table(table_name)
        else:
            raise exc

    return table

def post_message(team_id, text, channel):
    app.logger.debug("%s: sending message '%s' to channel %s", team_id, text, channel)
    get_client(team_id).api_call(
        'chat.postMessage',
        channel=channel,
        text=text
    )

@task
def reset_team_table(team_id, event):
    channel = event['channel']

    response = get_client(team_id).api_call(
        'users.info',
        user=event['user']
    )

    if response['user']['is_admin']:
        log('Resetting table', event)

        delete_team_table(team_id, channel)
        create_team_table(team_id, channel)
    else:
        post_message(team_id, "Nice try, buddy!", channel)

def generate_leaderboard(team_id, users, column='received'):
    leaderboard = []
    for index, user in enumerate(sorted(users, key=operator.itemgetter(column), reverse=True)[:10]):
        info = get_user_info(team_id, user['user_id'])
        leaderboard.append('%d. %s - %d %s' % (index+1, info['user']['name'], user[column], EMOJI))
    return '\n'.join(leaderboard)

@task
def generate_leaderboards(team_id, channel):
    try:
        table = get_team_table(team_id)
        response = table.scan()
        users = response['Items']
        if users:
            received = generate_leaderboard(team_id, users, 'received')
            given = generate_leaderboard(team_id, users, 'given')
            leaderboards = '*Received*\n\n%s\n\n*Given*\n\n%s' % (received, given)
        else:
            leaderboards = 'nothing to see here'
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            leaderboards = 'resetting, try again in a minute'
        else:
            raise exc

    post_message(team_id, leaderboards, channel)

@tallybot.on('app_mention')
def app_mention_event(payload):
    print(payload)
    event = payload['event']
    team_id = payload['team_id']
    if event.get('subtype') != 'bot_message' and not event.get('edited'):
        if event['text'] == '<@%s> leaderboard' % get_bot_id(team_id):
            generate_leaderboards(team_id, event['channel'])

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

def update_user(table, user_id, attribute, value):
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
        user = {
            'user_id': user_id,
            attribute: value
        }
        if attribute == 'received':
            user['given'] = 0
        else:
            user['received'] = 0
        table.put_item(Item=user)

    return user

def update_users(team_id, channel, giver, recipients, count):
    table = get_team_table(team_id)
    table.wait_until_exists()

    recipients = set(recipients)

    if giver in recipients:
        return ['No :banana: for you! _nice try, human_']

    report = []

    update_user(table, giver, 'given', count * len(recipients))

    for recipient in recipients:
        user = update_user(table, recipient, 'received', count)
        info = get_user_info(team_id, user['user_id'])
        report.append('%s %s has %d %s!' % (generate_affirmation(), info['user']['name'], user['received'], EMOJI))

    return report

@task
def update_scores(team_id, event):
    if 'message' in event:
        message = event['message']
    else:
        message = event

    emojis = re.findall(EMOJI, message['text'])
    if emojis:
        recipients = re.findall(r'<@([A-Z0-9]+)>', message['text'])

        if recipients:
            channel = event['channel']
            report = update_users(team_id, channel, event['user'], recipients, len(emojis))
            text = ', '.join(report)
            post_message(team_id, text, channel)

@tallybot.on('message')
def message_event(payload):
    event = payload['event']
    team_id = payload['team_id']
    if event['channel_type'] == 'channel'and 'subtype' not in event:
        update_scores(team_id, event)

    elif event['channel_type'] == 'im' and event['text'] == 'reset!':
        reset_team_table(team_id, event)

    elif event['channel_type'] == 'im' and event['text'] == 'leaderboard':
        generate_leaderboards(team_id, event)

@app.route('/slack', methods=['POST'])
def slack():
    response = tallybot.handle(request)

    if response is True:
        return ''
    elif response is False:
        abort(400)

    return response

import click
import os
import random
import re
import requests

from flask import Flask, abort, redirect, request, url_for
from flask.cli import with_appcontext

from app import tallybot
from app.db import (init_db,
                    create_team_table,
                    delete_team_table,
                    get_table,
                    update_config,
                    update_user)
from app.constants import (AFFIRMATIONS,
                           BANANA_URLS,
                           DAYO_URLS,
                           EMOJI,
                           REACTION,
                           TROLLS)
from app.decorators import memoize, task
from app.slack import (get_bot_id,
                       get_client,
                       post_message)
from botocore.exceptions import ClientError

def generate_leaderboard(team_id, users, column='received'):
    emoji = EMOJI
    if column == 'trolls':
        emoji = ':%s:' % TROLLS[0]

    leaderboard = []
    filtered_users = [user for user in users if user.get(column, 0) > 0]
    if not filtered_users:
        return None
    sorted_users = sorted(filtered_users, key=lambda u: u.get(column, 0), reverse=True)[:10]
    for index, user in enumerate(sorted_users):
        info = get_user_info(team_id, user['user_id'])
        display_name = info['user']['profile']['display_name']
        leaderboard.append('%d. %s - %d %s' % (index+1, display_name, user.get(column, 0), emoji))
    return '\n'.join(leaderboard)

@memoize
def get_user_info(team_id, user_id):
    return get_client(team_id).api_call('users.info', user=user_id)

@task
def generate_leaderboards(team_id, event):
    leaderboards = []

    try:
        table = get_table(team_id)
        response = table.scan()
        users = response['Items']
        if users:
            received = generate_leaderboard(team_id, users, 'received')
            if received:
                leaderboards.append('*Received*\n\n%s' % received)

            given = generate_leaderboard(team_id, users, 'given')
            if given:
                leaderboards.append('*Given*\n\n%s' % given)

            trolls = generate_leaderboard(team_id, users, 'trolls')
            if trolls:
                leaderboards.append('*Trolls*\n\n%s' % trolls)
        else:
            leaderboards.append('Needs moar %s' % EMOJI)
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            leaderboards = ['resetting, try again in a minute']
        else:
            raise exc

    post_message(team_id, '\n\n'.join(leaderboards), event['channel'])

@task
def reset_team_table(team_id, event, token):
    channel = event['channel']

    response = get_client(team_id).api_call(
        'users.info',
        user=event['user']
    )

    admins = os.environ.get('ADMINS', '').split(',')

    if response['user']['is_admin'] or response['user'].get('name') in admins:
        delete_team_table(team_id, channel)
        create_team_table(team_id, channel)
    else:
        post_message(team_id, "Nice try, buddy!", channel)

@task
def generate_me(team_id, event):
    try:
        table = get_table(team_id)
        response = table.get_item(
            Key={
                'user_id': event['user'],
            }
        )

        text = 'nothing to see here'

        if 'Item' in response:
            text = []

            user = response['Item']
            for column in ['received', 'given', 'trolls']:
                if user.get(column, 0) > 0:
                    if column == 'trolls':
                        text.append('received %d :%s:' % (user['trolls'], TROLLS[0]))
                    else:
                        text.append('%s %d %s' % (column, user[column], EMOJI))

            if text:
                text = 'You have ' + ', '.join(text)
            else:
                text = ''
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            text = 'resetting, try again in a minute'
        else:
            raise exc

    if text:
        post_message(team_id, text, event['channel'])

def update_users(team_id, channel, giver, recipients, count, multiplier=1, report=True):
    table = get_table(team_id)

    recipients = set(recipients)

    if giver in recipients:
        return ['No :banana: for you! _nice try, human_']

    if report:
        output = []
    given = 0

    for recipient in recipients:
        info = get_user_info(team_id, recipient)
        if info['user']['is_bot']:
            if report:
                display_name = info['user']['profile']['real_name_normalized']
                output.append("%s is a bot. Bots don't need %s."  % (display_name, EMOJI))
        else:
            given += multiplier * count
            user = update_user(table, recipient, 'received', multiplier * count)

            if report:
                display_name = info['user']['profile']['display_name']
                if os.environ.get('PYTEST_CURRENT_TEST'):
                    affirmation = 'Done.'
                else:
                    affirmation = random.choice(AFFIRMATIONS)
                output.append('%s %s has %d %s!'% (affirmation, display_name, user['received'], EMOJI))

    update_user(table, giver, 'given', given)

    if report:
        return output

def update_trolls(team_id, recipient, multiplier=1):
    table = get_table(team_id)
    info = get_user_info(team_id, recipient)
    if not info['user']['is_bot']:
        update_user(table, recipient, 'trolls', multiplier * 1)

@task
def update_scores_message(team_id, event):
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

@task
def update_scores_reaction(team_id, event):
    multiplier = 1
    if event['type'] == 'reaction_removed':
        multiplier = -1
    if event['reaction'] == REACTION and event.get('item_user') and event['user'] != event['item_user']:
        update_users(team_id, None, event['user'], [event['item_user']], 1, multiplier, False)
    elif event['reaction'] in TROLLS and event.get('item_user') and event['user'] != event['item_user']:
        update_trolls(team_id, event['item_user'], multiplier)

def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_envvar('FLASK_INSTANCE', silent=True)

    if config:
        app.config.from_mapping(config)

    with app.app_context():
        init_db(app)

    @app.route('/slack', methods=['POST'])
    def slack():
        response = tallybot.handle(app, request)

        if response is True:
            return ''
        elif response is False:
            abort(400)

        return response

    @app.route('/auth', methods=['GET'])
    def auth():
        if 'code' not in request.args:
            abort(403)

        data = {
            'client_id': app.config['SLACK_CLIENT_ID'],
            'client_secret': app.config['SLACK_CLIENT_SECRET'],
            'code': request.args['code'],
        }

        response = requests.post('https://slack.com/api/oauth.access', data=data)
        data = response.json()

        if data['ok']:
            config = {
                'access_token': data['access_token'],
                'team_name': data['team_name'],
                'bot_token': data['bot']['bot_access_token'],
            }
            update_config(data['team_id'], config)
            create_team_table(data['team_id'])

            return redirect(url_for('thanks'))
        else:
            abort(403)

    @app.route('/thanks')
    def thanks():
        return 'Thanks for installing tallybot!'

    @tallybot.on('app_mention')
    def app_mention_event(payload):
        event = payload['event']
        if event.get('subtype') != 'bot_message' and not event.get('edited'):
            team_id = payload['team_id']
            bot_id = get_bot_id(team_id)
            channel = event['channel']

            if event['text'] in ['<@%s> leaderboard' % bot_id,
                                '<@%s> tally' % bot_id,
                                '<@%s> bananas' % bot_id]:
                generate_leaderboards(team_id, event)

            elif event['text'] in ['<@%s> tally me' % bot_id,
                                   '<@%s> tallyme' % bot_id]:
                generate_me(team_id, event)

            elif event['text'] == '<@%s> banana' % bot_id:
                post_message(team_id, random.choice(BANANA_URLS), channel)

            elif event['text'] == '<@%s> dayo' % bot_id:
                post_message(team_id, random.choice(DAYO_URLS), channel)

    @tallybot.on('message')
    def message_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        channel_type = event['channel_type']
        event_text = event.get('text')

        if channel_type == 'channel' and 'subtype' not in event:
            update_scores_message(team_id, event)

        elif channel_type == 'im' and event_text == 'reset!':
            reset_team_table(team_id, event, app.config['SLACK_API_TOKEN'])

        elif channel_type == 'im' and event_text in ['bananas', 'leaderboard', 'tally']:
            generate_leaderboards(team_id, event)

        elif channel_type == 'im' and event_text in ['tally me', 'tallyme']:
            generate_me(team_id, event)

    @tallybot.on('reaction_added')
    def reaction_added_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        update_scores_reaction(team_id, event)

    @tallybot.on('reaction_removed')
    def reaction_removed_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        update_scores_reaction(team_id, event)

    @app.cli.command('init-db')
    def init_db_command():
        init_db(app)
        click.echo('Initialized the database')

    return app

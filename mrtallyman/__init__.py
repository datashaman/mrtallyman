import click
import json
import os
import random
import re
import requests

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_menu import Menu, register_menu

from .db import (init_db,
                    create_team_table,
                    delete_team_table,
                    get_team_config,
                    get_team_user,
                    get_team_users,
                    get_teams_info,
                    reset_team_quotas,
                    reset_team_scores,
                    update_team_config,
                    update_team_user)
from .constants import (AFFIRMATIONS,
                           BANANA_URLS,
                           DAYO_URLS)
from .db import get_bot_id
from .decorators import memoize, task
from .slack import (get_client,
                    handle_request,
                    on,
                    post_message,
                    valid_request)

def get_reward_emojis(team):
    return team['reward_emojis'].split(',')

def get_troll_emojis(team):
    return team['troll_emojis'].split(',')

def get_user_name(info):
    return info['user']['profile']['display_name'] or info['user']['profile']['real_name']

def generate_leaderboard(team, users, column='received'):
    if column == 'trolls':
        emoji = ':%s:' % get_troll_emojis(team)[0]
    else:
        emoji = ':%s:' % get_reward_emojis(team)[0]

    leaderboard = []
    filtered_users = [user for user in users if user.get(column, 0) > 0]
    if not filtered_users:
        return None
    sorted_users = sorted(filtered_users, key=lambda u: u.get(column, 0), reverse=True)[:10]
    for index, user in enumerate(sorted_users):
        info = get_user_info(team['id'], user['user_id'])
        user_name = get_user_name(info)
        leaderboard.append('%d. %s - %d %s' % (index+1, user_name, user.get(column, 0), emoji))
    return '\n'.join(leaderboard)

@memoize
def get_user_info(team_id, user_id):
    return get_client(team_id).users_info(user=user_id)

@task
def generate_leaderboards(team_id, event):
    leaderboards = []

    team = get_team_config(team_id)
    users = get_team_users(team_id)

    if users:
        received = generate_leaderboard(team, users, 'received')
        if received:
            leaderboards.append('*Received*\n\n%s' % received)

        given = generate_leaderboard(team, users, 'given')
        if given:
            leaderboards.append('*Given*\n\n%s' % given)

        trolls = generate_leaderboard(team, users, 'trolls')
        if trolls:
            leaderboards.append('*Trolls*\n\n%s' % trolls)

    if not leaderboards:
        emoji = get_reward_emojis(team)[0]
        leaderboards.append('Needs moar :%s:' % emoji)

    post_message(team_id, '\n\n'.join(leaderboards), event['channel'], event['ts'])

@task
def reset_team_table(team_id, event):
    channel = event['channel']

    response = get_client(team_id).users_info(
        user=event['user']
    )

    team = get_team_config(team_id)

    if response['user']['is_admin'] or response['user'].get('name') == team['user_id']:
        delete_team_table(team_id, channel)
        create_team_table(team_id, channel)
    else:
        if event.get('subtype') == 'message_replied':
            ts = event['ts']
        else:
            ts = None
        post_message(team_id, "Nice try, buddy!", channel, ts)

@task
def generate_me(team_id, event):
    team = get_team_config(team_id)
    user = get_team_user(team_id, event['user'])

    text = 'nothing to see here'
    reward_emoji = get_reward_emojis(team)[0]
    troll_emoji = get_troll_emojis(team)[0]

    if user:
        text = []

        for column in ['received', 'given', 'trolls']:
            if user.get(column, 0) > 0:
                if column == 'trolls':
                    text.append('received %d :%s:' % (user['trolls'], troll_emoji))
                else:
                    text.append('%s %d :%s:' % (column, user[column], reward_emoji))

        if text:
            text = 'You have ' + ', '.join(text)
        else:
            text = ''

    if text:
        if event.get('subtype') == 'message_replied':
            ts = event['ts']
        else:
            ts = None
        post_message(team_id, text, event['channel'], ts)

def update_users(team_id, channel, giver, recipients, score=1, report=True):
    recipients = set(recipients)

    if giver in recipients:
        return ['No :banana: for you! _nice try, human_']

    if report:
        output = []

    team = get_team_config(team_id)
    emoji = get_reward_emojis(team)[0]

    given = 0

    for recipient in recipients:
        info = get_user_info(team_id, recipient)
        if info['user']['is_bot']:
            if report:
                user_name = get_user_name(info)
                output.append("%s is a bot. Bots don't need :%s:."  % (user_name, emoji))
        else:
            given += score
            user = update_team_user(team_id, recipient, 'received', score)

            if report:
                user_name = get_user_name(info)
                if os.environ.get('PYTEST_CURRENT_TEST'):
                    affirmation = 'Done.'
                else:
                    affirmation = random.choice(AFFIRMATIONS)
                output.append('%s %s has %d :%s:!'% (affirmation, user_name, user['received'], emoji))

    update_team_user(team_id, giver, 'given', given)

    if report:
        return output

def update_trolls(team_id, recipient, score=1):
    info = get_user_info(team_id, recipient)
    if not info['user']['is_bot']:
        update_team_user(team_id, recipient, 'trolls', score)

@task
def update_scores_message(team_id, event):
    if 'message' in event:
        message = event['message']
    else:
        message = event

    if event.get('subtype') == 'message_replied':
        ts = event['ts']
    else:
        ts = None

    team = get_team_config(team_id)

    for emoji in get_reward_emojis(team):
        found = re.search(':%s:' % emoji, message['text'])
        if found:
            recipients = re.findall(r'<@([A-Z0-9]+)>', message['text'])

            if recipients:
                channel = event['channel']
                report = update_users(team_id, channel, event['user'], recipients)
                text = ' '.join(report)
                post_message(team_id, text, channel, ts)

@task
def update_scores_reaction(team_id, event):
    team = get_team_config(team_id)
    score = 1
    if event['type'] == 'reaction_removed':
        score = -1
    if event['reaction'] in get_reward_emojis(team) and event.get('item_user') and event['user'] != event['item_user']:
        update_users(team_id, None, event['user'], [event['item_user']], score, False)
    elif event['reaction'] in get_troll_emojis(team) and event.get('item_user') and event['user'] != event['item_user']:
        update_trolls(team_id, event['item_user'], score)

def handle_config(request):
    team_id = request.form['team_id']
    team = get_team_config(team_id)
    payload = {
        'trigger_id': request.form['trigger_id'],
        'dialog': {
            'callback_id': 'config',
            'title': 'Configure mrtallyman',
            'elements': [
                {
                    'type': 'text',
                    'label': 'Reward emojis',
                    'name': 'reward_emojis',
                    'hint': 'Comma-separated list of emojis considered rewards.',
                    'value': team['reward_emojis'],
                },
                {
                    'type': 'text',
                    'label': 'Troll emojis',
                    'name': 'troll_emojis',
                    'hint': 'Comma-separated list of emojis considered trolls. Leave blank to disable.',
                    'optional': True,
                    'value': team['troll_emojis'],
                },
                {
                    'type': 'select',
                    'label': 'Reset interval',
                    'name': 'reset_interval',
                    'value': team['reset_interval'],
                    'options': [
                        {
                            'label': 'Never Reset',
                            'value': 'never',
                        },
                        {
                            'label': 'Reset Daily',
                            'value': 'daily',
                        },
                        {
                            'label': 'Reset Weekly',
                            'value': 'weekly',
                        },
                        {
                            'label': 'Reset Monthly',
                            'value': 'monthly',
                        },
                    ],
                },
                {
                    'type': 'select',
                    'label': 'Daily quota',
                    'hint': 'Maximum number of rewards or trolls that can be given by a user per day.',
                    'name': 'daily_quota',
                    'value': team['daily_quota'],
                    'options': [
                        {
                            'label': 'Unlimited',
                            'value': 0,
                        },
                        {
                            'label': 'Three per day',
                            'value': 3,
                        },
                        {
                            'label': 'Five per day',
                            'value': 5,
                        },
                        {
                            'label': 'Ten per day',
                            'value': 10,
                        },
                    ],
                },
            ]
        },
    }

    response = get_client(request.form['team_id']).dialog_open(**payload)

    if not response['ok']:
        print(response)

def create_app(config=None):
    from dotenv import load_dotenv
    load_dotenv()

    app = Flask(__name__)

    if config:
        app.config.from_mapping(config)

    with app.app_context():
        init_db(app)

    Menu(app)

    @app.route('/slack/event', methods=['POST'])
    def event():
        if 'X-Slack-Retry-Num' in request.headers:
            return 'OK'

        response = handle_request(app, request)

        if response is True:
            return 'OK'
        elif response is False:
            abort(400)

        return response

    @app.route('/slack/action', methods=['POST'])
    def action():
        if valid_request(app, request):
            payload = json.loads(request.form['payload'])
            if payload['type'] == 'dialog_submission':
                if payload['callback_id'] == 'config':
                    update_team_config(payload['team']['id'], **payload['submission'])
                return ''
        abort(403)

    @app.route('/slack/command', methods=['POST'])
    def command():
        if valid_request(app, request):
            text = request.form['text']

            if text == 'ping':
                return 'Pong'

            if text in ['config', 'configure']:
                handle_config(request)

            return ''
        abort(403)

    @app.route('/slack/auth', methods=['GET'])
    def auth():
        if 'error' in request.args:
            return redirect(url_for('sorry'))

        if 'code' not in request.args:
            abort(403)

        data = {
            'client_id': os.environ['SLACK_CLIENT_ID'],
            'client_secret': os.environ['SLACK_CLIENT_SECRET'],
            'code': request.args['code'],
        }

        response = requests.post('https://slack.com/api/oauth.access', data=data)
        data = response.json()

        if data['ok']:
            config = {
                'access_token': data['access_token'],
                'bot_access_token': data['bot']['bot_access_token'],
                'bot_user_id': data['bot']['bot_user_id'],
                'team_name': data['team_name'],
                'user_id': data['user_id'],
            }
            update_team_config(data['team_id'], **config)
            create_team_table(data['team_id'])

            return redirect(url_for('thanks'))
        else:
            abort(403)

    @app.route('/thanks')
    def thanks():
        return render_template('thanks.html')

    @app.route('/sorry')
    def sorry():
        return render_template('sorry.html')

    @app.route('/')
    @register_menu(app, '.', 'Home')
    def home():
        return render_template('home.html')

    @app.route('/how-it-works')
    @register_menu(app, '.how-it-works', 'How It Works')
    def how_it_works():
        return render_template('how-it-works.html')

    @app.route('/info')
    def info():
        info = get_teams_info()
        return render_template('info.html', info=info)

    @app.route('/pricing')
    @register_menu(app, '.pricing', 'Pricing')
    def pricing():
        return render_template('pricing.html')

    @app.route('/privacy-policy')
    @register_menu(app, '.privacy-policy', 'Privacy Policy')
    def privacy_policy():
        return render_template('privacy-policy.html')

    @on('app_mention')
    def app_mention_event(payload):
        event = payload['event']
        if event.get('subtype') != 'bot_message' and not event.get('edited'):
            if event.get('subtype') == 'message_replied':
                ts = event['ts']
            else:
                ts = None

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
                post_message(team_id, random.choice(BANANA_URLS), channel, ts)

            elif event['text'] == '<@%s> dayo' % bot_id:
                post_message(team_id, random.choice(DAYO_URLS), channel, ts)

    @on('message')
    def message_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        channel_type = event['channel_type']
        event_text = event.get('text')

        if channel_type == 'channel' and 'subtype' not in event:
            update_scores_message(team_id, event)

        elif channel_type == 'im' and event_text == 'reset!':
            reset_team_table(team_id, event)

        elif channel_type == 'im' and event_text in ['bananas', 'leaderboard', 'tally']:
            generate_leaderboards(team_id, event)

        elif channel_type == 'im' and event_text in ['tally me', 'tallyme']:
            generate_me(team_id, event)

    @on('reaction_added')
    def reaction_added_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        update_scores_reaction(team_id, event)

    @on('reaction_removed')
    def reaction_removed_event(payload):
        team_id = payload['team_id']
        event = payload['event']
        update_scores_reaction(team_id, event)

    @app.cli.command('init-db')
    def init_db_command():
        init_db(app)
        click.echo('Initialized the database')

    @app.cli.command('reset-scores')
    @click.argument('reset_interval')
    def reset_scores_command(reset_interval):
        reset_team_scores(reset_interval)

    @app.cli.command('reset-quotas')
    def reset_quotas_command():
        reset_team_quotas()

    @app.context_processor
    def inject_google_analytics_id():
        return dict(google_analytics_id=os.environ['GOOGLE_ANALYTICS_ID'])

    return app

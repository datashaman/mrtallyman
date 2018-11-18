import json
import os
import time

from mrtallyman.db import (delete_team_table,
                    get_table_name,
                    get_team_user)
from mrtallyman.slack import generate_signature
from urllib.parse import parse_qsl, urlencode

def post_as_slack(client, app, body, endpoint='event', timestamp=None, secret=None):
    if timestamp is None:
        timestamp = str(time.time())
    if secret is None:
        secret = os.environ['SLACK_SIGNING_SECRET']
    signature = generate_signature(timestamp,
                                   secret,
                                   json.dumps(body, sort_keys=True))
    return client.post(
        '/slack/%s' % endpoint,
        json=body,
        headers={
            'X-Slack-Request-Timestamp': timestamp,
            'X-Slack-Signature': signature,
        }
    )

def test_url_verification(client, app):
    response = post_as_slack(
        client,
        app,
        {
            'type': 'url_verification',
            'challenge': '1234567890',
        }
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == '1234567890'

def test_invalid_signature(client, app):
    response = post_as_slack(
        client,
        app,
        {
            'type': 'url_verification',
            'challenge': '1234567890',
        },
        secret='987654321'
    )

    assert response.status_code == 400

def test_invalid_timestamp(client, app):
    response = post_as_slack(
        client,
        app,
        {
            'type': 'url_verification',
            'challenge': '1234567890',
        },
        timestamp='0',
    )

    assert response.status_code == 400

def test_event_callback(client, app):
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'channel',
                'text': 'hi',
                'type': 'message',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

def test_unknown_event_callback(client, app):
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'channel',
                'text': 'hi',
                'type': 'unknown',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 400

def test_event_message_reset_as_user(requests_mock, client, app):
    users_info = requests_mock.post('https://slack.com/api/users.info', json={'user': {'is_admin': False, 'name': 'USER'}})
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'im',
                'channel': 'CHANNEL',
                'text': 'reset!',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert users_info.called
    assert post_message.called

def test_event_message_reset_as_admin(requests_mock, client, app):
    users_info = requests_mock.post('https://slack.com/api/users.info', json={'user': {'is_admin': True}})
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'im',
                'channel': 'CHANNEL',
                'text': 'reset!',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert users_info.called
    assert post_message.called

def test_event_message_leaderboard(create_team_user, requests_mock, client, app):
    create_team_user('TEAM', 'USER1', given=3, received=2, trolls=0)
    create_team_user('TEAM', 'USER2', given=2, received=1, trolls=3)
    create_team_user('TEAM', 'USER3', given=1, received=3, trolls=1)

    def json_callback(request, context):
        form = dict(parse_qsl(request._request.body))
        return {
            'user': {
                'profile': {
                    'display_name': form['user'],
                },
            },
        }

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        json=json_callback
    )
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'im',
                'channel': 'CHANNEL',
                'text': 'leaderboard',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert post_message.called
    assert post_message.last_request.body == urlencode({
        'channel': 'CHANNEL',
        'text': '''*Received*

1. USER3 - 3 :banana:
2. USER1 - 2 :banana:
3. USER2 - 1 :banana:

*Given*

1. USER1 - 3 :banana:
2. USER2 - 2 :banana:
3. USER3 - 1 :banana:

*Trolls*

1. USER2 - 3 :troll:
2. USER3 - 1 :troll:'''})

def test_event_message_empty_leaderboard(requests_mock, client, app):
    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        json={
            'ok': True,
            'user': {
                'is_bot': False,
                'profile': {
                    'display_name': 'User',
                },
            },
        }
    )
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'im',
                'channel': 'CHANNEL',
                'text': 'leaderboard',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert post_message.called
    assert post_message.last_request.body == urlencode({
        'channel': 'CHANNEL',
        'text': 'Needs moar :banana:',
    })

def test_event_message_tally_me(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER', given=5, received=3, trolls=1)

    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel_type': 'im',
                'channel': 'CHANNEL',
                'text': 'tally me',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert post_message.called
    assert post_message.last_request.body == urlencode({
        'channel': 'CHANNEL',
        'text': 'You have received 3 :banana:, given 5 :banana:, received 1 :troll:',
    })

def test_event_app_mention(requests_mock, client, app):
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@BOT> hi',
                'type': 'app_mention',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

def test_event_app_mention_leaderboard(requests_mock, client, app):
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@BOT> leaderboard',
                'type': 'app_mention',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert post_message.called

def test_event_app_mention_me(requests_mock, client, app):
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@BOT> tally me',
                'type': 'app_mention',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert post_message.called

def test_event_app_mention_banana(requests_mock, client, app):
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@BOT> banana',
                'type': 'app_mention',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200

    assert post_message.called

def test_event_app_mention_dayo(requests_mock, client, app):
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@BOT> dayo',
                'type': 'app_mention',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert post_message.called

def test_event_message_banana(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')
    create_team_user('TEAM', 'OTHER')

    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})

    def match_args(request):
        return 'user=OTHER' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': False,
                'profile': {
                    'display_name': 'Item User',
                },
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'channel': 'CHANNEL',
                'channel_type': 'channel',
                'text': '<@OTHER> :banana:',
                'type': 'message',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert post_message.called
    assert post_message.last_request.body == urlencode({
        'channel': 'CHANNEL',
        'text': 'Done. Item User has 1 :banana:!',
    })
    assert users_info.called

    user = get_team_user('TEAM', 'USER')
    assert user['given'] == 1

    other = get_team_user('TEAM', 'OTHER')
    assert other['received'] == 1

def test_event_reaction_added_banana(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')
    create_team_user('TEAM', 'ITEM_USER')

    def match_args(request):
        return 'user=ITEM_USER' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': False,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'ITEM_USER',
                'reaction': 'banana',
                'type': 'reaction_added',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

    user = get_team_user('TEAM', 'USER')
    assert user['given'] == 1

    item_user = get_team_user('TEAM', 'ITEM_USER')
    assert item_user['received'] == 1

def test_event_reaction_removed_banana(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER', given=1)
    create_team_user('TEAM', 'ITEM_USER', received=1)

    def match_args(request):
        return 'user=ITEM_USER' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': False,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'ITEM_USER',
                'reaction': 'banana',
                'type': 'reaction_removed',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

    user = get_team_user('TEAM', 'USER')
    assert user['given'] == 0

    item_user = get_team_user('TEAM', 'ITEM_USER')
    assert item_user['received'] == 0

def test_event_reaction_added_banana_to_bot(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')

    def match_args(request):
        return 'user=BOT' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': True,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'BOT',
                'reaction': 'banana',
                'type': 'reaction_added',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

    user = get_team_user('TEAM', 'USER')
    assert user['given'] == 0

def test_event_reaction_added_troll(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')
    create_team_user('TEAM', 'ITEM_USER')

    def match_args(request):
        return 'user=ITEM_USER' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': False,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'ITEM_USER',
                'reaction': 'troll',
                'type': 'reaction_added',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

    item_user = get_team_user('TEAM', 'ITEM_USER')
    assert item_user['trolls'] == 1

def test_event_reaction_removed_troll(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')
    create_team_user('TEAM', 'ITEM_USER', trolls=1)

    def match_args(request):
        return 'user=ITEM_USER' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': False,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'ITEM_USER',
                'reaction': 'troll',
                'type': 'reaction_removed',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

    item_user = get_team_user('TEAM', 'ITEM_USER')
    assert item_user['trolls'] == 0

def test_event_reaction_added_troll_to_bot(requests_mock, create_team_user, client, app):
    create_team_user('TEAM', 'USER')

    def match_args(request):
        return 'user=BOT' == request._request.body

    users_info = requests_mock.post(
        'https://slack.com/api/users.info',
        additional_matcher=match_args,
        json={
            'user': {
                'is_bot': True,
            },
        }
    )

    response = post_as_slack(
        client,
        app,
        {
            'event': {
                'item_user': 'BOT',
                'reaction': 'banana',
                'type': 'reaction_added',
                'user': 'USER',
            },
            'team_id': 'TEAM',
            'type': 'event_callback',
        }
    )

    assert response.status_code == 200
    assert users_info.called

def test_cli_init_db(app):
    init_db_command = app.cli.commands['init-db']
    runner = app.test_cli_runner()
    result = runner.invoke(init_db_command)
    assert 'Initialized the database\n' == result.output

def test_delete_missing_table(requests_mock, app):
    post_message = requests_mock.post('https://slack.com/api/chat.postMessage', json={'ok': True})
    delete_team_table('UNKNOWN', 'CHANNEL')
    assert post_message.called
    table_name = get_table_name('UNKNOWN')
    assert post_message.last_request.body == urlencode({
        'channel': 'CHANNEL',
        'text': 'Table %s is not there' % table_name,
    })

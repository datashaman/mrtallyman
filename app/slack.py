from slackclient import SlackClient
from app.decorators import memoize

def get_bot_token(team_id):
    from app.db import get_table
    table = get_table('config')
    response = table.get_item(
        Key={
            'team_id': team_id,
        }
    )
    if 'Item' in response:
        return response['Item']['bot_token']

@memoize
def get_client(team_id):
    token = get_bot_token(team_id)
    return SlackClient(token)

@memoize
def get_bot_id(team_id):
    response = get_client(team_id).api_call('auth.test')
    return response['user_id']

def get_bot_by_token(token):
    client = SlackClient(token)
    return client.api_call('auth.test')

def post_message(team_id, text, channel):
    get_client(team_id).api_call(
        'chat.postMessage',
        channel=channel,
        text=text
    )

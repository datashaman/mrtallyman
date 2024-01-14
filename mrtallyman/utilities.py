from .decorators import memoize
from .slack import get_client, post_message

def team_log(team_id, message, channel=None, level='debug'):
    if channel:
        post_message(team_id, message, channel)

def get_reward_emojis(team):
    return team['reward_emojis'].split(',')

def get_golden_emoji(team):
    return team['golden_emoji']

def get_golden_threshold(team):
    return team['golden_threshold']

def get_troll_emojis(team):
    return team['troll_emojis'].split(',')

def get_user_name(info):
    return info['user']['profile']['display_name'] or info['user']['profile']['real_name']

@memoize
def get_user_info(team_id, user_id):
    return get_client(team_id).users_info(user=user_id)

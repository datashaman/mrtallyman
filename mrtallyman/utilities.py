from .slack import post_message

def team_log(team_id, message, channel=None, level='debug'):
    if channel:
        post_message(team_id, message, channel)

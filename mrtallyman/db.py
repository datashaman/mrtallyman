import pymysql
import os
import slack

from .decorators import memoize
from .utilities import team_log
from .slack import get_bot_by_token
from contextlib import contextmanager
from pymysql.err import ProgrammingError

@contextmanager
def db_cursor():
    db = pymysql.connect(
        host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
        user=os.environ.get('MYSQL_USER'),
        password=os.environ.get('MYSQL_PASSWORD'),
        db=os.environ.get('MYSQL_DB'),
        autocommit=True,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor)
    db.show_warnings()

    yield db.cursor()

    db.close()

def get_table_name(suffix):
    return 'team_%s' % suffix

@memoize
def get_bot_access_token(team_id):
    team = get_team_config(team_id)

    if team:
        return team['bot_access_token']

@memoize
def get_bot_id(team_id):
    team = get_team_config(team_id)

    if team:
        if team['bot_user_id']:
            return team['bot_user_id']

def create_config_table():
    table_name = get_table_name('config')

    if table_exists(table_name):
        return

    sql = '''
    CREATE TABLE `%s` (
        `id` varchar(255) not null,
        `team_name` varchar(255),
        `access_token` varchar(255),
        `bot_access_token` varchar(255),
        `bot_user_id` varchar(255),
        `user_id` varchar(255),
        `reward_emojis` varchar(255),
        `troll_emojis` varchar(255),
        `reset_interval` varchar(255),
        `daily_quota` int,
        primary key (`id`)
    );''' % get_table_name('config')

    with db_cursor() as cursor:
        cursor.execute(sql)

def create_team_table(team_id, channel=None):
    table_name = get_table_name(team_id)

    if table_exists(table_name):
        return

    team_log(team_id, 'Creating table %s' % table_name, channel)

    sql = '''
    CREATE TABLE IF NOT EXISTS `%s` (
        `id` int auto_increment,
        `team_id` varchar(255) not null,
        `user_id` varchar(255) not null,
        `rewards_given` int default 0 not null,
        `rewards_given_today` int default 0 not null,
        `rewards_received` int default 0 not null,
        `trolls_given` int default 0 not null,
        `trolls_given_today` int default 0 not null,
        `trolls_received` int default 0 not null,
        primary key (`id`),
        unique key (`team_id`, `user_id`),
        foreign key (`team_id`) references `team_config`(`id`)
    );''' % table_name

    with db_cursor() as cursor:
        cursor.execute(sql)

    team_log(team_id, 'Table %s created' % table_name, channel)

def get_team_config(team_id):
    sql = 'SELECT * FROM `team_config` WHERE `id` = %s'

    with db_cursor() as cursor:
        cursor.execute(sql, (team_id,))
        return cursor.fetchone()

def get_team_user(team_id, user_id):
    sql = 'SELECT * FROM `team_%s`' % team_id + ' WHERE `user_id` = %s'

    with db_cursor() as cursor:
        cursor.execute(sql, (user_id,))
        return cursor.fetchone()

def get_team_users(team_id):
    sql = 'SELECT * FROM `team_%s`' % team_id

    with db_cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()

def get_teams_info():
    info = []

    with db_cursor() as cursor:
        sql = 'SELECT * FROM `team_config` ORDER BY `team_name`'
        cursor.execute(sql)
        teams = cursor.fetchall()

        for team in teams:
            with db_cursor() as users_cursor:
                sql = 'SELECT COUNT(*) AS `user_count` FROM `team_%s`' % team['id']
                users_cursor.execute(sql)
                result = users_cursor.fetchone()
                info.append({'team': team, 'user_count': result['user_count']})

    return info

def update_team_user(team_id, user_id, attribute, value):
    user = get_team_user(team_id, user_id)

    if user:
        user[attribute] = max(0, user[attribute] + value)

        sql = 'UPDATE `team_%s` SET `%s`' % (team_id, attribute) + ' = %s WHERE `user_id` = %s'
        args = (user[attribute], user_id)

        with db_cursor() as cursor:
            cursor.execute(sql, args)
    else:
        user = create_team_user(team_id, user_id, **{attribute: max(0, value)})

    return user

def create_team_user(team_id, user_id, **attrs):
    user = {
        'team_id': team_id,
        'user_id': user_id,
        'rewards_given': 0,
        'rewards_given_today': 0,
        'rewards_received': 0,
        'trolls_given': 0,
        'trolls_given_today': 0,
        'trolls_received': 0,
    }
    user.update(attrs)

    sql = 'INSERT INTO `team_%s`' % team_id + ' (`team_id`, `user_id`, `rewards_given`, `rewards_given_today`, `rewards_received`, `trolls_given`, `trolls_given_today`, `trolls_received`) values (%(team_id)s, %(user_id)s, %(rewards_given)s, %(rewards_given_today)s, %(rewards_received)s, %(trolls_given)s, %(trolls_given_today)s, %(trolls_received)s)'

    with db_cursor() as cursor:
        cursor.execute(sql, user)

    return user

def delete_team_user(team_id, user_id):
    sql = 'DELETE FROM `team_%s`' % team_id + ' WHERE `user_id` = %s'

    with db_cursor() as cursor:
        cursor.execute(sql, (user_id,))

def update_team_config(team_id, **attrs):
    team = get_team_config(team_id)

    if team:
        sql = 'UPDATE `team_config` SET ' + ', '.join([f'`{key}` = %({key})s' for key in attrs.keys()]) + ' WHERE `id` = %(id)s'
        args = attrs
        args['id'] = team_id
    else:
        sql = 'INSERT INTO `team_config` (id, team_name, access_token, bot_access_token, bot_user_id, reward_emojis, troll_emojis, reset_interval, daily_quota, user_id) values (%(id)s, %(team_name)s, %(access_token)s, %(bot_access_token)s, %(bot_user_id)s, %(reward_emojis)s, %(troll_emojis)s, %(reset_interval)s, %(daily_quota)s, %(user_id)s)'
        team = {
            'access_token': '',
            'bot_access_token': '',
            'bot_user_id': '',
            'daily_quota': None,
            'id': team_id,
            'reset_interval': 'never',
            'reward_emojis': 'banana',
            'team_name': '',
            'troll_emojis': 'troll,trollface',
            'user_id': '',
        }
        args = team
        args.update(attrs)

    with db_cursor() as cursor:
        cursor.execute(sql, args)

    team.update(attrs)

    return team

def table_exists(table_name):
    sql = 'SELECT 1 FROM `%s` LIMIT 1' % table_name
    try:
        with db_cursor() as cursor:
            cursor.execute(sql)
        return True
    except ProgrammingError as exc:
        if exc.args[0] == 1146:
            return False
        raise exc

def delete_team_table(team_id, channel):
    table_name = get_table_name(team_id)

    if not table_exists(table_name):
        team_log(team_id, 'Table %s is not there' % table_name, channel)
        return

    sql = 'DROP TABLE `%s`' % table_name

    with db_cursor() as cursor:
        cursor.execute(sql)

    team_log(team_id, 'Table %s deleted' % table_name, channel)

def init_db(app):
    create_config_table()

    token = os.environ['SLACK_API_TOKEN']
    client = slack.WebClient(token=token)
    response = client.auth_test()
    if not response['ok']:
        abort(400)
    create_team_table(response['team_id'])
    update_team_config(response['team_id'], team_name=response['team'], bot_access_token=token, bot_user_id=response['user_id'])

def reset_team_scores(reset_interval):
    with db_cursor() as cursor:
        sql = 'SELECT `id` FROM `team_config` WHERE `reset_interval` = %s'
        cursor.execute(sql, (reset_interval,))
        teams = cursor.fetchall()

        for team in teams:
            delete_team_table(team['id'], None)
            create_team_table(team['id'], None)

def reset_team_quotas():
    with db_cursor() as cursor:
        sql = 'SELECT `id` FROM `team_config`'
        cursor.execute(sql)
        teams = cursor.fetchall()

        for team in teams:
            sql = 'UPDATE `team_' + team['id'] + '` SET rewards_given_today = %s, trolls_given_today = %s'
            cursor.execute(sql, (0, 0))

import boto3
import os

from botocore.exceptions import ClientError
from slackclient import SlackClient
from app.decorators import memoize
from app.utilities import team_log
from app.slack import get_bot_by_token

@memoize
def get_db():
    endpoint_url = os.environ.get('DYNAMODB_ENDPOINT_URL')
    return boto3.resource('dynamodb', endpoint_url=endpoint_url)

def get_table_name(suffix):
    return 'tallybot-%s' % suffix

def create_config_table():
    table_name = get_table_name('config')

    try:
        table = get_db().create_table(
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
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            pass
        else:
            raise exc

@memoize
def get_table(suffix):
    table_name = get_table_name(suffix)
    return get_db().Table(table_name)

def create_team_table(team_id, channel=None):
    table_name = get_table_name(team_id)
    team_log(team_id, 'Creating table %s' % table_name, channel)

    try:
        table = get_db().create_table(
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
            table = get_db().Table(table_name)
        else:
            raise exc

    return table

def get_user(team_id, user_id):
    table = get_table(team_id)
    response = table.get_item(
        Key={
            'user_id': user_id,
        }
    )
    return response.get('Item')

def update_user(table, user_id, attribute, value):
    response = table.get_item(
        Key={
            'user_id': user_id,
        }
    )

    if 'Item' in response:
        user = response['Item']
        user[attribute] = max(0, user.get(attribute, 0) + value)
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
            'given': 0,
            'received': 0,
            'trolls': 0,
        }
        user[attribute] = max(0, value)
        table.put_item(Item=user)

    return user

def create_team_user(team_id, user_id, **attrs):
    user = {
        'team_id': team_id,
        'user_id': user_id,
        'given': 0,
        'received': 0,
        'trolls': 0,
    }
    user.update(attrs)
    table = get_table(team_id)
    table.put_item(Item=user)
    return user

def delete_team_user(team_id, user_id):
    table = get_table(team_id)
    table.delete_item(
        Key={
            'user_id': user_id,
        }
    )

def update_config(team_id, data):
    table = get_table('config')

    response = table.get_item(
        Key={
            'team_id': team_id
        }
    )

    if 'Item' in response:
        expression = 'SET %s' % ', '.join(['%s = :%s' % (key, key) for key in data.keys()])
        values = dict((':%s' % key, value) for key, value in data.items())

        table.update_item(
            Key={
                'team_id': team_id,
            },
            UpdateExpression=expression,
            ExpressionAttributeValues=values
        )
    else:
        data['team_id'] = team_id
        table.put_item(Item=data)

def update_local_token(token):
    client = SlackClient(token)
    auth_test = client.api_call('auth.test')

    if auth_test['ok']:
        update_config(auth_test['team_id'], {'bot_token': token})

def table_exists(table_name):
    try:
        get_db().meta.client.describe_table(TableName=table_name)
        return True
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            return False
        else:
            raise exc

def delete_config_table():
    table_name = get_table_name('config')

    if not table_exists(table_name):
        return

    table = get_table('config')

    try:
        table.delete()
        table.wait_until_not_exists()
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceInUseException':
            table.wait_until_not_exists()
        elif exc.response['Error']['Code'] != 'ResourceNotFoundException':
            raise exc

def delete_team_table(team_id, channel):
    table_name = get_table_name(team_id)

    if not table_exists(table_name):
        team_log(team_id, 'Table %s is not there' % table_name, channel)
        return

    table = get_table(team_id)
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

def init_db(app):
    create_config_table()
    update_local_token(app.config['SLACK_API_TOKEN'])
    bot = get_bot_by_token(app.config['SLACK_API_TOKEN'])
    create_team_table(bot['team_id'])

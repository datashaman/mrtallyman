import pytest
import app.constants as constants
constants.AFFIRMATIONS = ['Done.']

from app import create_app
from app.db import create_team_user, delete_team_user, get_db

@pytest.fixture
def app(requests_mock):
    requests_mock.post('https://slack.com/api/auth.test', json={'ok': True, 'team_id': 'TEAM', 'user_id': 'BOT'})
    app = create_app({
        'SLACK_API_TOKEN': '1234567890',
        'SLACK_SIGNING_SECRET': '1234567890',
    })
    app.testing = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def create_user(app):
    with app.app_context():
        users = []

        def _create_user(team_id, user_id, **attrs):
            user = create_team_user(team_id, user_id, **attrs)
            users.append(user)
            return user

        yield _create_user

        for user in users:
            delete_team_user(user['team_id'], user['user_id'])

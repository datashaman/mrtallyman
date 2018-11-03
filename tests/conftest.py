import pytest
import mrtallyman.constants as constants
constants.AFFIRMATIONS = ['Done.']

from mrtallyman import create_app
from mrtallyman.db import create_team_user as _create_team_user, delete_team_user

@pytest.fixture
def app(requests_mock):
    requests_mock.post('https://slack.com/api/auth.test', json={'ok': True, 'team': 'Team', 'team_id': 'TEAM', 'user_id': 'BOT'})
    app = create_app()
    app.testing = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def create_team_user(app):
    with app.app_context():
        users = []

        def func(team_id, user_id, **attrs):
            user = _create_team_user(team_id, user_id, **attrs)
            users.append(user)
            return user

        yield func

        for user in users:
            delete_team_user(user['team_id'], user['user_id'])

# tallybot

Slack bot that tallies scores for a team. Uses DynamoDB to store results and gevent to spawn long-running threads.

Requires AWS credentials to be setup on the host.

Setup an app and a bot on Slack, deploy the app to a host somewhere. Verify the Request URL and subscribe to the following events:

- `app_mention`
- `message.channels`
- `message.im`

Grant the following OAuth scopes to the bot:

- `channels:history`
- `channels:read`

Installation:

    mkvirtualenv -r requirements.txt tallybot

Configuration:

    cp .env.example .env

Running:

    flask run

## operations

The bot must be invited to a channel to respond to events.

To add a reward to a user, mention them in a message with a variable number of reward emojis (default :banana:):

    @user1 here have a :banana:
    @user2 @user3 you deserve 2! :banana: :banana:

To see the leaderboard:

    @tallybot leaderboard

If you are an admin you can privately message the bot to reset the leaderboards:

    reset!

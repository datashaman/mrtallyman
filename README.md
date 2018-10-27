# tallybot

Slack bot that tallies scores for a team. Uses DynamoDB to store results and zappa.task to spawn long-running threads.

Requires AWS credentials to be setup on the host.

Setup an app and a bot on Slack, deploy the app to a host somewhere. Verify the Request URL and subscribe to the following events:

- `app_mention`
- `message.channels`
- `message.im`

Grant the following OAuth scopes to the bot:

- `channels:history`
- `channels:read`

## Local Development

Installation (production):

    mkvirtualenv -r requirements.txt tallybot

Installation (testing and development):

    mkvirtualenv -r requirements-testing.txt tallybot

Configuration for development:

    cp .env.example .env

Configuration for development:

    cp instance/example.py instance/development.py

Set `FLASK_INSTANCE` in your environment to use the instance configuration you've defined.

Running:

    flask run

## AWS Lambda Development

Installation:

    zappa init

First time deployment of the lambda:

    zappa deploy dev

Updating the running lambda with new changes:

    zappa update dev

To tail the _CloudWatch_ logs:

    zappa tail dev

The endpoint URL with _/slack_ appended should be input into the _Request URL_ on your bot's Event Subscription page. The bot takes care of verifying the challenge.

## Operations

The bot must be invited to a channel to respond to events.

To reward a user, mention them in a message with a variable number of reward emojis (default :banana:):

    @user1 here have a :banana:
    @user2 @user3 you deserve 2! :banana: :banana:

Mentions such as the above cannot be edited to remove the reward. Once it's posted, it's scored.

Another way to reward a user is to add a :banana: reaction to their messages.

As a public service to all, you can also mark a user as a troll by adding a _troll_ reaction to a message of theirs.

Removing a reaction of :banana: or :troll: will reduce the score of the user appropriately.

A user cannot reward themselves or bot users, either by app mentions or reactions.

To see the leaderboard use one of the following:

    @tallybot bananas
    @tallybot leaderboard
    @tallybot tally

The leaderboard shows the names of the top users who've given and received rewards since the last table reset, as well as the _troll_ scores.

It displays names instead of user mentions to avoid notification fatigue when someone wants to see the leaderboard.

To see your own scores use one of the following:

    @tallybot tallyme
    @tallybot tally me

All of the above app mentions can also be used in a private channel with the bot (without the bot prefix):

    bananas
    leaderboard
    tally
    tallyme
    tally me

If you are an admin you can privately message the bot to reset the leaderboards:

    reset!

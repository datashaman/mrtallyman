# mrtallyman

Slack bot that tallies scores for a team. Uses MySQL to store results and multiprocessing.Process to handle long running tasks.

Setup an app and a bot on Slack, deploy the app to a host somewhere. Verify the Request URL and subscribe to the following events:

- `app_mention`
- `message.channels`
- `message.im`
- `reaction_added`
- `reaction_removed`

Grant the following OAuth scopes to the bot:

- `bot`
- `channels:history`
- `im:history`
- `reactions:read`

## Local Development

Installation (production):

    mkvirtualenv -r requirements.txt mrtallyman

Installation (testing and development):

    mkvirtualenv -r requirements-testing.txt mrtallyman

Configuration for development:

    cp .env.example .env

Edit the .env to match your app's details.

Running:

    flask run

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

    @mrtallyman bananas
    @mrtallyman leaderboard
    @mrtallyman tally

The leaderboard shows the names of the top users who've given and received rewards since the last table reset, as well as the _troll_ scores.

It displays names instead of user mentions to avoid notification fatigue when someone wants to see the leaderboard.

To see your own scores use one of the following:

    @mrtallyman tallyme
    @mrtallyman tally me

All of the above app mentions can also be used in a private channel with the bot (without the bot prefix):

    bananas
    leaderboard
    tally
    tallyme
    tally me

If you are an admin in the workspace or your username is in the comma-separated environment variable _ADMINS_, you can privately message the bot to reset the leaderboards:

    reset!

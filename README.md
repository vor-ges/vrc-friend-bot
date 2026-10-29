# vrc-friend-bot

A Discord bot for tracking and notifying you about your VRChat friends' online activity.

## Concept

This project started with a simple question: When are my friends usually online?

As the popularity of [vrc-meikan](https://vrc-meikan.com/) grew, I added more friends, many of whom I have not yet had the chance to meet.

I wanted to understand their usual login times.

If I knew that a friend tended to come online earlier than I expected, I might be able to log in earlier myself and increase the chances of meeting them.

That idea led to the development of this bot.

## Overview

vrc-friend-bot sends notifications to Discord when your VRChat friends' online statuses or other status information change.

It also records their login times, making it easier to understand their activity patterns.

For long-term tracking, running the bot on a server that can stay online 24/7 is recommended.

I run mine on an Ubuntu server hosted on Oracle Cloud.

## Features

・Mention notifications when a friend comes online

・Notifications when a friend goes offline

・Information about the worlds and instances that friends join

・Notifications when a friend's status changes

・Logging, statistics, and analysis of friends' login times

Note: Logging in to VRChat through the website is not counted when determining whether a friend is online or offline.

It is planed to add a language change feature in the future.

## Requirement

See requirements.txt for the required Python packages.

## How to use

1. Create a Discord bot and configure the necessary permissions.
2. Use .env.example as a template to create your .env file and configure the required environment variables.
3. Install Python.
4. Install the required packages listed in requirements.txt.
5. Make sure all required files are in the same directory.
6. Run bot.py to start the bot.

Detailed setup instructions and the supported Python version may be added in the future.

## Security

The .env file contains sensitive information, such as your Discord bot token.

Do not share or publish this file.

Before publishing the project on GitHub, make sure that .env is excluded from version control.

Use .env.example to provide a template without exposing actual credentials.

## Version

1.0.0

## Development

This project was originally created for personal use.

## Author

nur_ieren

[X](https://x.com/nur_ieren)

## Acknowledgements

Development assistance tools, including Claude Code, were used during development.

## Licence

This project is licensed under the MIT License. See LICENSE for details.

[MIT License](https://opensource.org/license/mit)

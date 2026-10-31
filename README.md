
# vrc-friend-bot

A Discord bot for tracking and notifying you about your VRChat friends' online activity.

## Concept

This project started with a simple question from a friend: When are my friends usually online?

As the popularity of [vrc-meikan](https://vrc-meikan.com/) grew, he added more friends, many of whom he had not yet had the chance to meet.

He wanted to understand their usual login times.

If he knew that a friend tended to come online earlier than expected, he might be able to log in earlier himself and increase the chances of meeting them.

That idea led to the development of this bot.

## Overview

vrc-friend-bot monitors registered VRChat friends and sends notifications to Discord when their in-game activity or status changes.

It also records login times and in-game activity, making it easier to understand friends' activity patterns over time.

For long-term tracking, running the bot on a server that can stay online 24/7 is recommended.

It currently runs on an Ubuntu server hosted on Oracle Cloud, for example.

## Features

- **Online Notifications** — Sends a Discord notification and mentions the bot owner when a registered friend logs in to VRChat in-game.
- **Offline Notifications** — Notifies you when a friend leaves VRChat in-game.
- **Location Tracking** — Notifies you when a friend moves to another world or instance.
- **World Information** — Displays world names, instance types, regions, and player counts when available.
- **Instance Owner Information** — Retrieves the name of the instance owner, including VRChat group names when applicable.
- **Status Change Notifications** — Notifies you when a friend's VRChat status or status description changes.
- **Friend-specific Channels** — Creates a dedicated Discord text channel for each registered friend.
- **Friend Management** — Adds, removes, and lists registered friends through Discord slash commands.
- **Login Statistics** — Records in-game login times and calculates activity statistics.
- **Activity Analysis** — Shows login frequency by hour and status usage based on time spent in-game.
- **Per-friend Statistics** — Displays statistics for all registered friends in the main channel or for an individual friend in their dedicated channel.
- **Language Switching** — Switches the bot's displayed language between Japanese and English using the `/lang` command.
- **Persistent Language Settings** — Saves the selected language in the database so that it is retained after restarting the bot.

### Important distinction: In-game and web activity

VRChat reports in-game login activity and web activity as different events.

This bot focuses on in-game activity:
- Logging in through the VRChat website alone does not trigger an online notification.
- Web-only activity is not counted as an in-game login.
- Offline notifications are sent when a friend who was detected in-game leaves.

## Requirements

- Python
- Discord bot account
- VRChat account
- Required Python packages listed in `requirements.txt`

## How to use

### 1. Setup

1. Create a Discord bot and configure the necessary permissions.
2. Use `.env.example` as a template to create your `.env` file.
3. Configure the required environment variables:
   - `DISCORD_TOKEN`
   - `GUILD_ID`
   - `MAIN_CHANNEL_ID`
   - `OWNER_ID`
   - `VRC_USERNAME`
   - `VRC_PASSWORD`
   - `VRC_USER_AGENT`
4. Install Python.
5. Install the required packages:

   ```bash
   pip install -r requirements.txt
   ```

6. Make sure all required files are in the same directory.
7. Run the bot:

   ```bash
   python bot.py
   ```

### 2. Friend management

Use the following slash commands in the configured Discord server.

| Command | Description |
|---|---|
| `/friend add url:` | Adds a friend using their VRChat profile URL or user ID. |
| `/friend remove target:` | Removes a registered friend. |
| `/friend list` | Displays the registered friend list. |

Each registered friend gets a dedicated text channel under the `VRC-Friends` category.

Removing a friend deactivates their registration but keeps their channel and its message history. The friend can be registered again later.

### 3. Login statistics

Use:

```text
/stats
```

- In the main channel, displays statistics for all currently registered friends.
- In a friend's dedicated channel, displays statistics for that friend.
- Optionally specify `days` to limit the statistics to a period of up to 365 days.
- If `days` is omitted, statistics cover the entire available tracking period.

Statistics include:
- Login frequency by hour
- Total in-game login count
- Total time spent in-game
- VRChat status usage percentages
- Individual friend statistics when used in the main channel

### 4. Language switching

Use the `/lang` command to change the bot's display language.

| Command | Description |
|---|---|
| `/lang` | Displays the currently selected language. |
| `/lang language:ja` | Switches the display language to Japanese. |
| `/lang language:en` | Switches the display language to English. |

The language setting is shared by the bot and saved in its database.

The selected language is retained after restarting the bot.

The default language is Japanese.

Note: Translations are provided for supported messages. Text without an available translation is displayed in Japanese.

## Important notes

- Only the configured bot owner can use the management, statistics, and language-switching commands.
- Friend management commands must be used in the configured main channel.
- The bot's VRChat account must be friends with the users you want to monitor. Otherwise, notifications may not arrive.
- VRChat API access is subject to authentication requirements and rate limits.
- Initial VRChat authentication may require two-factor authentication (2FA).
- Login statistics are based on activity recorded by the bot. Friends added after tracking begins are counted only from the time they are registered.
- Only in-game activity is included in login statistics. Web-only activity is excluded.

## Security

The `.env` file contains sensitive information, including your Discord bot token and VRChat credentials.

Do not share or publish this file.

Before publishing the project on GitHub, make sure `.env` is excluded from version control.

Use `.env.example` to provide a configuration template without exposing actual credentials.

## Version

1.1.0

## Development

This project was originally created for personal use.

## Author

- vor_ges
- nur_ieren

## Acknowledgements

Development assistance tools, including Claude Code, were used during development.

## Copyright

Copyright © 2026 vor_ges and nur_ieren.

All rights reserved.

No part of this project, including its source code,
design, text, images, or other content, may be
reproduced, modified, distributed, or used without
prior written permission from the copyright holder.

This project is not licensed for reuse.

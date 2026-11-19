# vrc-friend-bot

A Discord bot that tracks your VRChat friends' in-game activity, notifies you of status changes, and records login statistics.

[日本語](README.ja.md)

## Concept

This project started with a simple question from a friend:

"When are my friends usually online?"

As the popularity of [vrc-meikan](https://vrc-meikan.com/) grew, he added more friends, including many people he had not yet had the chance to meet.

He wanted to understand their usual login times. If he knew that a friend tended to come online earlier than expected, he could log in earlier himself and increase the chances of meeting them.

That idea led to the development of this bot.

## Overview

`vrc-friend-bot` monitors registered VRChat friends and sends notifications to Discord when their in-game activity, location, or status changes.

It also records login times and in-game activity, allowing you to analyze your friends' activity patterns over time.

For continuous, long-term tracking, running the bot on a server that can stay online 24/7 is recommended.

The bot currently runs on an Ubuntu server hosted on Oracle Cloud.

## Features

- **Online Notifications** — Notifies you when a registered friend logs in to VRChat in-game.
- **Offline Notifications** — Notifies you when a friend who was detected in-game goes offline.
- **Location Tracking** — Notifies you when a friend moves to another world or instance.
- **World Information** — Displays world names, instance types, regions, and player counts when available.
- **Instance Owner Information** — Retrieves the instance owner's name, including VRChat group names when applicable.
- **Status Change Notifications** — Notifies you when a friend's VRChat status or status description changes.
- **Friend-specific Channels** — Creates a dedicated Discord text channel for each registered friend.
- **Friend Management** — Adds, removes, and lists registered friends through slash commands.
- **Login Statistics** — Records in-game login times and calculates activity statistics.
- **Activity Analysis** — Displays login frequency by hour and VRChat status usage based on time spent in-game.
- **Per-friend Statistics** — Shows statistics for all registered friends in the main channel or for an individual friend in their dedicated channel.
- **Language Switching** — Switches the bot's display language between Japanese and English using `/lang`.
- **Persistent Language Settings** — Saves the selected language in the database and retains it after restarting the bot.

### In-game Activity vs. Web Activity

VRChat treats in-game login activity and website activity as separate events. This bot focuses exclusively on in-game activity.

- Logging in through the VRChat website alone does not trigger an online notification.
- Web-only activity is not counted as an in-game login.
- Offline notifications are sent when a friend previously detected in-game leaves VRChat.

## Requirements

- Python
- A Discord bot account
- A VRChat account
- The Python packages listed in `requirements.txt`

## Installation

### 1. Create a Discord Bot

1. Create a bot application through the Discord Developer Portal.
2. Configure the necessary permissions and invite the bot to your server.
3. Prepare the IDs required by the configuration.

### 2. Configure Environment Variables

Use `.env.example` as a template and create your own `.env` file.

Configure the following environment variables:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Discord bot token |
| `GUILD_ID` | Discord server ID |
| `MAIN_CHANNEL_ID` | Main channel ID |
| `OWNER_ID` | Discord user ID of the bot owner |
| `VRC_USERNAME` | VRChat username |
| `VRC_PASSWORD` | VRChat password |
| `VRC_USER_AGENT` | User-Agent used for VRChat API requests |

### 3. Install Dependencies

Install Python and the required packages:

```bash
pip install -r requirements.txt
```

### 4. Run the Bot

Make sure all required project files are in the same directory, then run:

```bash
python bot.py
```

## Usage

### 1. Friend Management

Use the following slash commands in the configured Discord server.

| Command | Description |
|---|---|
| `/friend add url:` | Registers a friend using their VRChat profile URL or user ID. |
| `/friend remove target:` | Removes a registered friend. |
| `/friend list` | Displays the registered friend list. |

Each registered friend gets a dedicated text channel under the `VRC-Friends` category.

Removing a friend deactivates their registration but does not delete their channel or message history. They can be registered again later.

### 2. Login Statistics

Use:

```text
/stats
```

The results depend on the channel where the command is used:

- **Main channel:** Displays statistics for all currently registered friends.
- **Friend-specific channel:** Displays statistics for that particular friend.

You can optionally specify `days` to limit the statistics to a period of up to 365 days.

If `days` is omitted, statistics cover the entire available tracking period.

The statistics include:

- Login frequency by hour
- Total in-game login count
- Total time spent in-game
- VRChat status usage percentages

### 3. Language Switching

Use `/lang` to change the bot's display language.

| Command | Description |
|---|---|
| `/lang code:ja` | Switches the display language to Japanese. |
| `/lang code:en` | Switches the display language to English. |

The language setting is shared by the bot and stored in its database.

The selected language is retained after restarting the bot.

The default language is Japanese.

**Note:** Translations are provided for supported messages. Text without an available translation is displayed in Japanese.

## Important Notes

- Only the configured bot owner can use the management, statistics, and language-switching commands.
- Friend management commands must be used in the configured main channel.
- The bot's VRChat account must be friends with the users you want to monitor. Otherwise, notifications may not arrive.
- VRChat API access is subject to authentication requirements and rate limits.
- Initial VRChat authentication may require two-factor authentication (2FA).
- Login statistics are based on activity recorded by the bot. Friends added after tracking begins are counted only from the time they are registered.
- Only in-game activity is included in login statistics. Web-only activity is excluded.

## Security

The `.env` file contains sensitive information, including your Discord bot token and VRChat credentials.

- Never share or publish your `.env` file.
- Make sure `.env` is excluded from Git version control.
- Use `.env.example` to provide a configuration template without exposing actual credentials.

## Version

`1.2.1`

## Development

This project was originally created for personal use.

## Authors

- [vor_ges](https://github.com/vor-ges)
- [nur_ieren](https://github.com/nur-ieren)

## Acknowledgements

Development assistance tools, including Claude Code, were used during development.

## Copyright

Copyright © 2026 vor_ges and nur_ieren.

All rights reserved.

No part of this project, including its source code, design, text, images, or other content, may be reproduced, modified, distributed, or used without prior written permission from the copyright holders.

This project is not licensed for reuse.

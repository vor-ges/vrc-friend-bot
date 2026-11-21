
# vrc-friend-bot

A Discord bot that monitors VRChat friends, sends activity notifications, and tracks in-game activity statistics for all friends, regardless of their Discord notification registration status.

[日本語](README.ja.md)

## Concept

This project started with a simple question from a friend:

"When are my friends usually online?"

As the popularity of [vrc-meikan](https://vrc-meikan.com/) grew, he added more friends, including many people he had not yet had the chance to meet.

He wanted to understand their usual login times. If he knew that a friend tended to come online earlier than expected, he could log in earlier himself and increase the chances of meeting them.

That idea led to the development of this bot.

## Overview

`vrc-friend-bot` monitors VRChat friends and sends notifications to Discord when their in-game activity, location, or status changes.

It also records in-game activity statistics for all VRChat friends, independently of whether they are registered for Discord notifications.

This separation allows you to maintain activity records even after removing someone from Discord notifications.

For continuous, long-term tracking, running the bot on a server that can stay online 24/7 is recommended.

The bot currently runs on an Ubuntu server hosted on Oracle Cloud.

## Features

- **Online Notifications** — Notifies you when a registered friend logs in to VRChat in-game.
- **Offline Notifications** — Notifies you when a registered friend who was detected in-game goes offline.
- **Location Tracking** — Notifies you when a registered friend moves to another world or instance.
- **World Information** — Displays world names, instance types, regions, and player counts when available.
- **Instance Owner Information** — Retrieves the instance owner's name, including VRChat group names when applicable.
- **Status Change Notifications** — Notifies you when a registered friend's VRChat status or status description changes.
- **Friend-specific Channels** — Creates a dedicated Discord text channel for each notification-registered friend.
- **Friend Management** — Adds, removes, and lists notification-registered friends through slash commands.
- **Autocomplete Friend Selection** — Selects VRChat friends by display name when adding or removing notification registrations.
- **Removal Confirmation** — Displays a confirmation dialog before removing a notification registration.
- **Paginated Friend List** — Displays registered friends across multiple pages.
- **Login Statistics** — Records in-game login times, login counts, and time spent in-game for all VRChat friends.
- **All-friend Activity Tracking** — Collects activity statistics independently of Discord notification registration.
- **Automatic Friend Synchronization** — Synchronizes the VRChat friend list at startup, after WebSocket reconnections, and every six hours.
- **Friend-specific Statistics** — Analyzes individual friends, including those not registered for Discord notifications.
- **Flexible Statistics Selection** — Selects a friend through `/stats` autocomplete, including removed, unregistered, and unfriended users with existing records.
- **Activity Analysis** — Displays login frequency by hour, time spent in-game, and VRChat status usage based on time spent in each status.
- **Persistent Statistics** — Retains historical activity records even after a friend is removed from notification registration or unfriends the bot account.
- **Automatic Display Name Updates** — Updates stored friend names when VRChat display names change.
- **Mention Settings** — Controls Discord mentions in online notifications globally or individually for each friend.
- **Language Switching** — Switches the bot's display language between Japanese and English using `/lang`.
- **Persistent Settings** — Saves language and mention preferences in the database.

### Notification Tracking vs. Activity Tracking

The bot separates Discord notification registration from VRChat activity tracking.

| Feature | All VRChat Friends | Notification-registered Friends |
|---|---|---|
| Activity statistics | Yes | Yes |
| Login history | Yes | Yes |
| Time spent in-game | Yes | Yes |
| Status usage statistics | Yes | Yes |
| Online notifications | No | Yes |
| Offline notifications | No | Yes |
| Location change notifications | No | Yes |
| Status change notifications | No | Yes |
| Dedicated Discord channel | No | Yes |

Removing a friend using `/remove` only disables Discord notifications. Activity tracking continues as long as the user remains a VRChat friend.

If the user unfriends the bot's VRChat account, automatic tracking stops, but previously recorded statistics are retained.

### Automatic Friend Synchronization

The bot periodically retrieves the VRChat friend list to keep its activity records synchronized.

Synchronization takes place:

- When the bot starts.
- Whenever the VRChat WebSocket connection is re-established.
- Every six hours as a fallback.

Both online and offline friends are retrieved, with pagination of up to 100 entries per request.

Synchronization updates friend information and reconciles current in-game states with stored activity records. It does not send notifications.

If the WebSocket connection is interrupted, the bot uses synchronization after reconnection to compensate for missed state changes.

### In-game Activity vs. Web Activity

VRChat treats in-game login activity and website activity as separate events.

This bot focuses exclusively on in-game activity.

- Logging in through the VRChat website alone does not trigger an online notification.
- Web-only activity is not counted as an in-game login.
- Offline notifications are sent when a registered friend previously detected in-game leaves VRChat.

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
| `STATS_TZ` | Time zone used for statistics (optional; defaults to `Asia/Tokyo`) |

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

Use the following slash commands in the configured main channel.

| Command | Description |
|---|---|
| `/add target:` | Registers a VRChat friend for Discord notifications. |
| `/remove target:` | Removes a notification registration. |
| `/list` | Displays the notification-registered friend list. |

#### `/add`

Registers a VRChat friend for Discord notifications.

- Select a friend from autocomplete suggestions.
- Search by display name.
- Alternatively, provide a VRChat profile URL or user ID.
- A dedicated text channel is created under the `VRC-Friends` category.

Only current VRChat friends who are not already registered for notifications appear in the autocomplete suggestions. Previously removed friends can be registered again.

If the user is already known through automatic friend synchronization, the bot can use the stored information without making an additional user lookup request.

If the supplied profile belongs to someone who is not a VRChat friend, the notification registration can still be created, but the bot displays a warning that notifications may not arrive.

#### `/remove`

Removes a friend's Discord notification registration.

- Select a registered friend from autocomplete suggestions.
- Search by display name or user ID.
- The last six characters of the user ID are displayed to distinguish users with identical names.
- A confirmation dialog is displayed before removal.
- The confirmation dialog expires after 60 seconds.

Removing a friend does not delete their dedicated channel or message history.

**Important:** Removing a friend only stops Discord notifications. Activity statistics continue to be collected while the user remains a VRChat friend.

#### `/list`

Displays the notification-registered friend list.

The following options are available:

| Option | Description |
|---|---|
| `show_uid` | Displays user IDs in the list. |
| `include_removed` | Includes previously removed notification registrations. |

When the list contains many friends, navigation buttons allow you to browse multiple pages.

The list also displays each friend's current mention setting.

### 2. Login Statistics

Use:

```text
/stats
```

The results depend on the channel and options used.

| Usage | Result |
|---|---|
| `/stats` in the main channel | Statistics for all currently notification-registered friends. |
| `/stats` in a friend-specific channel | Statistics for that particular friend. |
| `/stats who:` | Statistics for the selected friend, regardless of notification registration status. |
| `/stats days:` | Limits the statistics to the specified number of days. |

The `who` option provides autocomplete suggestions for known VRChat friends and previously registered users.

It supports:

- Currently notification-registered friends.
- Previously removed registrations.
- VRChat friends not registered for Discord notifications.
- Users who have unfriended the bot account but have existing records.

A user can be selected by display name or UID.

When a friend is selected, their individual collection start time is used as the beginning of the statistical period.

The `days` option accepts values from 1 to 365. If omitted, the entire available collection period is used.

The statistics include:

- Login frequency by hour.
- Total in-game login count.
- Total time spent in-game.
- VRChat status usage percentages.
- Individual friend statistics when viewing multiple friends.

**Note:** A friend who is already in-game when first detected may be recorded as a resumed session. This contributes to time spent in-game but does not count as a newly detected login.

### 3. Mention Settings

Use `/mention` to control whether Discord mentions are included in online notifications.

| Command | Description |
|---|---|
| `/mention state:on` | Enables mentions in online notifications. |
| `/mention state:off` | Disables mentions in online notifications. |
| `/mention state:reset` | Resets an individual friend's setting to the global setting. |

The target depends on the channel where the command is used:

- **Main channel:** Changes the global setting.
- **Friend-specific channel:** Changes the setting for that particular friend.

Individual settings take priority over the global setting.

The `reset` option is only available in friend-specific channels.

Mentions are enabled by default.

### 4. Language Switching

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

- Only the configured bot owner can use the management, statistics, language-switching, and mention-setting commands.
- Friend management commands must be used in the configured main channel.
- Statistics commands must be used in the main channel or a friend-specific channel.
- The bot's VRChat account must be friends with users for automatic friend-list synchronization and continuous activity tracking.
- Users who are not VRChat friends can still be registered for Discord notifications, but notifications may not arrive.
- VRChat API access is subject to authentication requirements and rate limits.
- Initial VRChat authentication may require two-factor authentication (2FA).
- Activity tracking begins when the bot first detects a friend. Historical activity from before tracking began cannot be reconstructed.
- Statistics are based on events received and state reconciliation performed by the bot. They are not an official VRChat activity history.
- Only in-game activity is included. Web-only activity is excluded.
- If the friend list cannot be retrieved completely, the bot uses a safety check to avoid incorrectly marking large numbers of users as unfriended.

## Security

The `.env` file contains sensitive information, including your Discord bot token and VRChat credentials.

- Never share or publish your `.env` file.
- Make sure `.env` is excluded from Git version control.
- Use `.env.example` to provide a configuration template without exposing actual credentials.

## Version

`1.4.0`

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

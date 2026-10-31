"""表示言語の切り替え。

日本語の文をそのままキーにして tr() で包む方式(gettext風)。
- ja : 表を引かずそのまま出す(= 従来の表示と完全に同じ)
- 他言語: 下の TABLES から引く。表に無い文は日本語のまま出すので、翻訳漏れがあっても壊れない
- 言語を足すには LANGS に追加し、TABLES に同じキーで翻訳を書くだけ({name} などの{}は同じものを残す)
- 選択中の言語は DB(bot_settings)に保存され、再起動後も保たれる
"""
import logging

log = logging.getLogger("vrcbot")

LANGS = {"ja": "日本語", "en": "English"}
# /lang に入力できるコード: ISO 639-1(2文字) と ISO 639-2/3(3文字)。"jp" はISO 639ではないが入力しがちなので別名として許可。
# 言語を足すときは LANGS と TABLES に加え、ここにもコードを書く。
CODES = {"ja": "ja", "jpn": "ja", "jp": "ja", "en": "en", "eng": "en"}
_lang = "ja"


def resolve(text):
    """ユーザー入力(en / ja / jpn / jp / en-US など)を LANGS のコードに変換。不明なら None。"""
    s = (text or "").strip().lower().replace("_", "-").split("-")[0]  # en-US, ja_JP -> en / ja
    return CODES.get(s)

TABLES = {
    "en": {
        # --- ワールド/インスタンス情報 ---
        "取得不可": "Unavailable",
        "場所": "Location",
        "Private / 取得不可": "Private / Unavailable",
        "ワールド": "World",
        "インスタンス": "Instance",
        "人数": "Players",
        "オーナー": "Owner",
        "{name} (グループ)": "{name} (Group)",
        "説明": "Description",
        # --- 通知 ---
        "🟢 {name} がオンライン": "🟢 {name} is online",
        "プラットフォーム": "Platform",
        "⚫ {name} がオフライン": "⚫ {name} went offline",
        "🚪 {name} が移動": "🚪 {name} moved",
        "{emoji} {name} のステータス変更": "{emoji} {name} changed status",
        "変更前": "Before",
        "変更後": "After",
        # --- /stats ---
        "所有者のみ実行できます。": "Only the owner can run this.",
        "登録フレンドがいません。": "No friends are registered.",
        "📊 ログイン統計 (登録フレンド全員)": "📊 Login stats (all registered friends)",
        "📊 {name} のログイン統計": "📊 Login stats for {name}",
        " (削除済み)": " (removed)",
        "メインチャンネルか、フレンド用チャンネルで実行してください。": "Run this in the main channel or in a friend's channel.",
        "📅 **集計期間**: {start} 〜 {end} ({tz}) ・約{days:.1f}日間\n🔢 **ゲーム内ログイン**: {logins}回 ・ ゲーム内滞在 {hours:.1f}時間":
            "📅 **Period**: {start} – {end} ({tz}) · about {days:.1f} days\n🔢 **In-game logins**: {logins} · Time in game: {hours:.1f} h",
        "⏰ ログイン頻度 (時間帯別)": "⏰ Login frequency (by hour)",
        "まだ記録がありません": "No data yet",
        "{h}時台({c}回)": "{h}:00 ({c}x)",
        "{h:02d}時": "{h:02d}h",
        "最多: {top}": "Peak: {top}",
        "🎭 ステータス使用割合": "🎭 Status usage",
        "🎭 ステータス使用割合 (ゲーム内の滞在時間ベース)": "🎭 Status usage (by time in game)",
        "{emoji} {k} **{pct:.1f}%** ({hours:.1f}時間)": "{emoji} {k} **{pct:.1f}%** ({hours:.1f} h)",
        "不明": "Unknown",
        "**{name}** — {logins}回 / 最多 {peak}時台 / {hours:.1f}h": "**{name}** — {logins} logins / peak {peak}:00 / {hours:.1f} h",
        "**{name}** — {hours:.1f}h (ログイン記録なし)": "**{name}** — {hours:.1f} h (no login records)",
        "**{name}** — 記録なし": "**{name}** — no data",
        "…他{n}人": "…and {n} more",
        "👥 フレンド別 (ログイン回数順)": "👥 By friend (by logins)",
        "ゲーム内のログインのみ集計(Webのみは対象外)。集計開始後に登録したフレンドは登録後の分だけです。":
            "Only in-game logins are counted (web-only activity is excluded). Friends added after tracking began are counted from the time they were added.",
        # --- /friend remove・list の画面部品 ---
        "所有者のみ操作できます。": "Only the owner can use this.",
        "削除する": "Remove",
        "キャンセル": "Cancel",
        "すでに削除されています。": "Already removed.",
        "➖ メンバー削除": "➖ Member removed",
        "🗑️ **{name}** を削除しました (チャンネルは保持): <#{ch}>": "🗑️ Removed **{name}** (channel kept): <#{ch}>",
        "キャンセルしました: {name}": "Cancelled: {name}",
        "確認がタイムアウトしました。削除していません。": "Confirmation timed out. Nothing was removed.",
        "🚫(削除済み)": "🚫(removed)",
        "VRChat 登録フレンド ({n}人)": "VRChat registered friends ({n})",
        "ページ {p}/{n}": "Page {p}/{n}",
        # --- /friend ---
        "メインチャンネルで所有者のみ実行できます。": "Only the owner can run this, and only in the main channel.",
        "URLの形式が不正です。`https://vrchat.com/home/user/usr_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` を指定してください。":
            "Invalid URL. Please provide `https://vrchat.com/home/user/usr_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.",
        "❌ {msg}": "❌ {msg}",
        "すでに登録済みです: **{name}** <#{ch}>": "Already registered: **{name}** <#{ch}>",
        "❌ チャンネル作成に失敗しました (Botの権限を確認): {status}": "❌ Failed to create the channel (check the bot's permissions): {status}",
        "\n⚠️ このアカウントとフレンドではないため、通知は届きません。":
            "\n⚠️ The bot's VRChat account is not friends with this user, so notifications will not arrive.",
        "➕ メンバー追加": "➕ Member added",
        "(再登録)": " (re-added)",
        "✅ 追加しました: **{name}** → {ch}{warn}": "✅ Added: **{name}** → {ch}{warn}",
        "その登録は存在しません。": "That entry does not exist.",
        "同名のユーザーが複数います。候補一覧から選択してください。": "Multiple users share that name. Please pick one from the suggestions.",
        "その登録は存在しません。候補一覧から選択してください。": "That entry does not exist. Please pick one from the suggestions.",
        "このメンバーを削除しますか？": "Remove this member?",
        "**{name}**\n`{uid}`\nチャンネル: <#{ch}> (削除されません)": "**{name}**\n`{uid}`\nChannel: <#{ch}> (will not be deleted)",
        "登録なし": "No registrations",
        # --- /lang ---
        "言語を {name} に切り替えました。": "Language switched to {name}.",
        "未対応の言語です。使用できるコード: {codes}": "Unsupported language. Available codes: {codes}",
        # --- VRChat APIのエラー (vrc.explain_error) ---
        "VRChat APIの応答がタイムアウトしました。少し待って再試行してください。": "The VRChat API timed out. Please wait a moment and try again.",
        "VRChatの再認証(2FA)が必要です。サーバーで `python bot.py` を手動起動して認証してください。":
            "VRChat re-authentication (2FA) is required. Start `python bot.py` manually on the server to authenticate.",
        "そのユーザーはVRChat上に存在しません。URLを確認してください。": "That user does not exist on VRChat. Please check the URL.",
        "VRChat認証エラーです。サーバー側で再認証が必要な可能性があります。": "VRChat authentication error. Re-authentication may be needed on the server.",
        "VRChat APIのレート制限中です。しばらく待って再試行してください。": "The VRChat API is rate limiting. Please wait a while and try again.",
        "VRChat側のサーバーエラーです (HTTP {st})。": "VRChat server error (HTTP {st}).",
        "VRChat APIでエラーが発生しました。ログを確認してください。": "An error occurred with the VRChat API. Please check the logs.",
    },
}


def get_lang():
    return _lang


def set_lang(code):
    global _lang
    if code not in LANGS:
        raise ValueError(f"unsupported language: {code}")
    _lang = code


def tr(msg, **kw):
    """日本語の文を現在の言語に翻訳して .format する。表に無ければ日本語のまま。"""
    s = TABLES.get(_lang, {}).get(msg, msg)
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError, ValueError):
        log.exception("翻訳の書式エラー lang=%s msg=%r", _lang, msg)
        try:
            return msg.format(**kw) if kw else msg  # 翻訳側の書式ミスなら原文(日本語)で出す
        except (KeyError, IndexError, ValueError):
            return msg  # 呼び出し側の引数ミスでも例外にせず、通知は止めない


# ---------- 永続化 ----------
def _ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS bot_settings(k TEXT PRIMARY KEY, v TEXT)")
    conn.commit()


def load(conn):
    """DBから言語設定を読み込んで反映する(無ければ ja のまま)。"""
    _ensure(conn)
    r = conn.execute("SELECT v FROM bot_settings WHERE k='lang'").fetchone()
    set_lang(r[0] if r and r[0] in LANGS else "ja")
    return get_lang()


def save(conn, code):
    _ensure(conn)
    conn.execute("INSERT INTO bot_settings(k,v) VALUES('lang',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (code,))
    conn.commit()

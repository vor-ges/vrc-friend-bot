import os, re, json, time, asyncio, logging
from datetime import datetime
from typing import Optional
import discord, websockets
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from db import DB
from vrc import VRC, extract_uid, explain_error
from stats import Stats, make_tz
import i18n
from i18n import tr, LANGS

load_dotenv()
log = logging.getLogger("vrcbot")
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
MAIN_CH = int(os.environ["MAIN_CHANNEL_ID"])
OWNER = int(os.environ["OWNER_ID"])
UA = os.environ.get("VRC_USER_AGENT", "VRCFriendBot/1.0")
CATEGORY = "VRC-Friends"
STATUS = {"join me": ("🔵", 0x3498DB), "active": ("🟢", 0x2ECC71),
          "ask me": ("🟠", 0xE67E22), "busy": ("🔴", 0xE74C3C), "offline": ("⚫", 0x95A5A6)}

def parse_location(loc):
    """location文字列 -> (world_id, instance_id, type_label, region, owner) / 特殊値はNone
    owner = ("grp"|"usr", id) / Publicなどオーナーなしは None"""
    if not loc or loc in ("offline", "private", "traveling") or ":" not in loc:
        return None
    wid, rest = loc.split(":", 1)
    iid, *tags = rest.split("~")
    t = {x.split("(")[0]: (x.split("(", 1)[1].rstrip(")") if "(" in x else "") for x in tags}
    region = t.get("region", "us")
    if "group" in t:
        label = {"public": "Group Public", "plus": "Group+", "members": "Group"}.get(t.get("groupAccessType"), "Group")
    elif "hidden" in t: label = "Friends+"
    elif "friends" in t: label = "Friends"
    elif "private" in t: label = "Invite+" if "canRequestInvite" in t else "Invite"
    else: label = "Public"
    owner = None
    if t.get("group"): owner = ("grp", t["group"])
    else:
        for k in ("hidden", "friends", "private"):
            if t.get(k): owner = ("usr", t[k]); break
    return wid, rest, label, region, owner

def slug(name, uid):
    s = re.sub(r"[^\w\-]+", "-", name.lower()).strip("-")
    return (s or uid[-8:])[:90]

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db = DB()
        self.vrc = VRC(os.environ["VRC_USERNAME"], os.environ["VRC_PASSWORD"], UA)
        self.last_loc, self.last_status, self.world_cache = {}, {}, {}
        self.owner_cache = {}  # id -> (取得時刻, 名前 or None)
        self.ingame = set()    # 現在VRChat(ゲーム内)にログイン中と判断しているUID
        self.stats = Stats(self.db.c, make_tz(os.environ.get("STATS_TZ", "Asia/Tokyo")))
        i18n.load(self.db.c)  # 保存済みの表示言語を読み込む

    async def setup_hook(self):
        self.tree.add_command(FriendGroup(self), guild=discord.Object(GUILD_ID))
        self.tree.add_command(self.make_stats_command(), guild=discord.Object(GUILD_ID))
        self.tree.add_command(self.make_lang_command(), guild=discord.Object(GUILD_ID))
        await self.tree.sync(guild=discord.Object(GUILD_ID))
        await asyncio.to_thread(self.vrc.login)
        asyncio.create_task(self.heartbeat())
        asyncio.create_task(self.prime_cache())
        asyncio.create_task(self.ws_loop())

    async def prime_cache(self):
        for f in self.db.active():
            u = await self.snapshot(f["uid"])
            if u:  # 停止中に起きたログイン/ログアウトを統計履歴に反映
                self.stats.reconcile(f["uid"], f["uid"] in self.ingame, u["status"], close_at=self.stats.prev_alive)
            await asyncio.sleep(1.5)

    async def heartbeat(self):
        while True:
            self.stats.heartbeat()
            await asyncio.sleep(60)

    def seed(self, uid, u):
        """get_userの結果から、ステータスと「ゲーム内にいるか」を復元 (state: online=ゲーム内 / active=Webのみ)"""
        self.last_status[uid] = (u["status"], u["desc"])
        if u.get("state") == "online": self.ingame.add(uid)
        else: self.ingame.discard(uid)

    async def snapshot(self, uid):
        try:
            u = await asyncio.to_thread(self.vrc.get_user, uid)
            self.seed(uid, u)
            return u
        except Exception as e:
            log.warning("snapshot %s failed: %s", uid, e)

    # ---------- channels ----------
    async def friend_channel(self, uid, name):
        guild = self.get_guild(GUILD_ID)
        row = self.db.get(uid)
        if row and row["channel_id"]:
            ch = guild.get_channel(row["channel_id"])
            if ch: return ch  # 削除済みメンバーの再追加時も既存チャンネルを再利用
        cat = discord.utils.get(guild.categories, name=CATEGORY) or await guild.create_category(CATEGORY)
        return await guild.create_text_channel(slug(name, uid), category=cat, topic=uid)

    async def send_to(self, uid, **kw):
        row = self.db.get(uid)
        ch = row and self.get_channel(row["channel_id"])
        if ch: await ch.send(**kw)

    # ---------- world info ----------
    async def owner_name(self, kind, oid):
        """インスタンスオーナー名。ユーザー=表示名 / グループ=グループ名。1時間キャッシュ(失敗時は5分)。"""
        c = self.owner_cache.get(oid)
        if c and time.time() - c[0] < (3600 if c[1] else 300):
            return c[1] or tr("取得不可")
        name = None
        row = kind == "usr" and self.db.get(oid)
        if row: name = row["name"]  # 登録済みフレンドならAPI不要
        else:
            try:
                if kind == "grp": name = await asyncio.to_thread(self.vrc.get_group_name, oid)
                else: name = (await asyncio.to_thread(self.vrc.get_user, oid))["name"]
            except Exception as e:
                log.warning("owner lookup failed %s: %s", oid, e)
        self.owner_cache[oid] = (time.time(), name)
        return name or tr("取得不可")

    async def world_embed_fields(self, loc, embed):
        p = parse_location(loc)
        if not p:
            embed.add_field(name=tr("場所"), value=tr("Private / 取得不可") if loc in ("private", None, "") else loc)
            return
        wid, iid, label, region, owner = p
        w = self.world_cache.get(wid)
        if not w or time.time() - w[0] > 1800:
            try: w = (time.time(), await asyncio.to_thread(self.vrc.get_world, wid))
            except Exception: w = (time.time(), None)
            self.world_cache[wid] = w
        info = w[1]
        embed.add_field(name=tr("ワールド"), value=f"[{info['name']}](https://vrchat.com/home/world/{wid})" if info else wid, inline=False)
        embed.add_field(name=tr("インスタンス"), value=f"{label} ({region.upper()})")
        try:
            i = await asyncio.to_thread(self.vrc.get_instance, wid, iid)
            cap = i["capacity"] or (info and info["capacity"]) or "?"
            embed.add_field(name=tr("人数"), value=f"{i['n_users']}/{cap}")
        except Exception:
            embed.add_field(name=tr("人数"), value=tr("取得不可"))
        if owner:
            name = await self.owner_name(*owner)
            embed.add_field(name=tr("オーナー"), value=tr("{name} (グループ)", name=name) if owner[0] == "grp" else name)
        if info:
            if info["thumb"]: embed.set_thumbnail(url=info["thumb"])
            if info["desc"]: embed.add_field(name=tr("説明"), value=info["desc"], inline=False)

    # ---------- /stats ----------
    def make_stats_command(self):
        @app_commands.describe(days="直近何日分を集計するか (省略時は集計開始から全期間)")
        async def stats(i: discord.Interaction, days: Optional[app_commands.Range[int, 1, 365]] = None):
            if i.user.id != OWNER:
                return await i.response.send_message(tr("所有者のみ実行できます。"), ephemeral=True)
            now, since = time.time(), self.stats.since()
            start = max(since, now - days * 86400) if days else since
            if i.channel_id == MAIN_CH:  # メインチャンネル: 登録中の全フレンド
                names = {r["uid"]: r["name"] for r in self.db.active()}
                if not names:
                    return await i.response.send_message(tr("登録フレンドがいません。"))
                res = self.stats.summarize(list(names), start, now)
                e = stats_embed(tr("📊 ログイン統計 (登録フレンド全員)"), res, start, now, self.stats.tz, names)
            else:  # フレンド用チャンネル: そのフレンドだけ
                row = next((r for r in self.db.all() if r["channel_id"] == i.channel_id), None)
                if not row:
                    return await i.response.send_message(
                        tr("メインチャンネルか、フレンド用チャンネルで実行してください。"), ephemeral=True)
                res = self.stats.summarize([row["uid"]], start, now)
                title = tr("📊 {name} のログイン統計", name=row["name"]) + ("" if row["active"] else tr(" (削除済み)"))
                e = stats_embed(title, res, start, now, self.stats.tz)
            await i.response.send_message(embed=e)
        return app_commands.Command(name="stats", description="フレンドのログイン時間帯・ステータス使用割合の統計", callback=stats)

    # ---------- /lang ----------
    def make_lang_command(self):
        @app_commands.describe(language="切り替える言語 / Language (省略すると現在の言語を表示)")
        @app_commands.choices(language=[app_commands.Choice(name=n, value=c) for c, n in LANGS.items()])
        async def lang(i: discord.Interaction, language: Optional[str] = None):
            if i.user.id != OWNER:
                return await i.response.send_message(tr("所有者のみ実行できます。"), ephemeral=True)
            if language is None:
                return await i.response.send_message(tr("現在の言語: {name} ({code})", name=LANGS[i18n.get_lang()], code=i18n.get_lang()))
            if language not in LANGS:
                return await i.response.send_message(tr("未対応の言語です。"), ephemeral=True)
            i18n.set_lang(language)
            i18n.save(self.db.c, language)  # 再起動後も保持
            log.info("language switched by=%s lang=%s", i.user.id, language)
            await i.response.send_message(tr("言語を {name} に切り替えました。", name=LANGS[language]))
        return app_commands.Command(name="lang", description="表示言語の切り替え / Switch language", callback=lang)

    # ---------- WebSocket ----------
    async def ws_loop(self):
        backoff = 5
        while True:
            try:
                token = await asyncio.to_thread(self.vrc.get_token)
                async with websockets.connect(f"wss://pipeline.vrchat.cloud/?authToken={token}",
                                              additional_headers={"User-Agent": UA}) as ws:
                    log.info("pipeline connected"); backoff = 5
                    async for raw in ws:
                        try: await self.handle(json.loads(raw))
                        except Exception: log.exception("event error")
            except Exception as e:
                log.warning("ws error: %s (retry %ss)", e, backoff)
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 300)

    async def handle(self, msg):
        t, c = msg.get("type"), msg.get("content")
        if isinstance(c, str):
            try: c = json.loads(c)
            except Exception: return
        if not isinstance(c, dict): return
        uid = c.get("userId") or c.get("userid")  # friend-active だけキー名が小文字
        row = uid and self.db.get(uid)
        if not row or not row["active"]: return
        name = row["name"]
        user = c.get("user") or {}
        platform = c.get("platform", "")

        # VRChatは「ゲーム内ログイン=friend-online」「Web=friend-active」と別イベントで送る一方、
        # friend-offline はどちらの離脱でも届く。ゲームに入っていた人の離脱だけを通知する。
        if t == "friend-online":
            if platform == "web": return
            self.ingame.add(uid)
            self.stats.record(uid, "login", user.get("status") or (self.last_status.get(uid) or (None,))[0])
            e = discord.Embed(title=tr("🟢 {name} がオンライン", name=name), color=0x2ECC71)
            if platform: e.add_field(name=tr("プラットフォーム"), value=platform)
            loc = c.get("location") or (user.get("location"))
            self.last_loc[uid] = loc
            await self.world_embed_fields(loc, e)
            await self.send_to(uid, content=f"<@{OWNER}>", embed=e)  # メンションはオンラインのみ
        elif t in ("friend-offline", "friend-active"):
            # friend-active(Webのみ)は、ゲームを終了してWebだけ残った場合も含むので「ゲームから抜けた」扱い
            self.last_loc.pop(uid, None)
            if uid not in self.ingame: return  # Webの入退室など、ゲームに入っていない人の離脱は通知しない
            self.ingame.discard(uid)
            self.stats.record(uid, "logout")
            await self.send_to(uid, embed=discord.Embed(title=tr("⚫ {name} がオフライン", name=name), color=0x95A5A6))
        elif t == "friend-location":
            loc = c.get("location")
            if not loc or loc == "offline": return
            if uid not in self.ingame:  # 実在の場所を持つ=ゲーム内(オンライン通知を取りこぼしていても復元)
                self.ingame.add(uid)
                self.stats.record(uid, "resume", (self.last_status.get(uid) or (None,))[0])
            if loc == "traveling" or loc == self.last_loc.get(uid): return
            self.last_loc[uid] = loc
            e = discord.Embed(title=tr("🚪 {name} が移動", name=name), color=0x3498DB)
            await self.world_embed_fields(loc, e)
            await self.send_to(uid, embed=e)
        elif t == "friend-update":
            st, desc = user.get("status"), user.get("statusDescription", "")
            if st is None: return
            old = self.last_status.get(uid)
            self.last_status[uid] = (st, desc)
            if uid in self.ingame and self.stats.state(uid)[1] != st:
                self.stats.record(uid, "status", st)  # ゲーム内でのステータス変更だけ統計に使う(比較は統計履歴上の現ステータス)
            if old == (st, desc): return
            emoji, color = STATUS.get(st, ("❔", 0x95A5A6))
            e = discord.Embed(title=tr("{emoji} {name} のステータス変更", emoji=emoji, name=name), color=color)
            if old: e.add_field(name=tr("変更前"), value=f"{old[0]}\n{old[1] or '-'}")
            e.add_field(name=tr("変更後"), value=f"{st}\n{desc or '-'}")
            await self.send_to(uid, embed=e)

esc = lambda s: discord.utils.escape_markdown(discord.utils.escape_mentions(s or ""))


def stats_embed(title, res, start, end, tz, names=None):
    """Stats.summarize() の結果をEmbedにする。names={uid: 表示名} を渡すとフレンド別も出す。"""
    tot = res["total"]
    fmt = lambda ts: datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
    e = discord.Embed(title=title, color=0x9B59B6)
    e.description = tr("📅 **集計期間**: {start} 〜 {end} ({tz}) ・約{days:.1f}日間\n🔢 **ゲーム内ログイン**: {logins}回 ・ ゲーム内滞在 {hours:.1f}時間",
                       start=fmt(start), end=fmt(end), tz=datetime.fromtimestamp(end, tz).tzname(),
                       days=(end - start) / 86400, logins=tot["logins"], hours=tot["seconds"] / 3600)
    h, mx = tot["hours"], max(tot["hours"])
    if mx == 0:
        e.add_field(name=tr("⏰ ログイン頻度 (時間帯別)"), value=tr("まだ記録がありません"), inline=False)
    else:
        top = " / ".join(tr("{h}時台({c}回)", h=x, c=h[x]) for x in sorted(range(24), key=lambda x: (-h[x], x))[:3] if h[x])
        bars = [f"{tr('{h:02d}時', h=x)} {'█' * max(1, round(10 * c / mx)) if c else '':<10} {c}" for x, c in enumerate(h)]
        e.add_field(name=tr("⏰ ログイン頻度 (時間帯別)"), value=tr("最多: {top}", top=top) + "\n```\n" + "\n".join(bars) + "\n```", inline=False)
    ss, total = tot["status"], sum(tot["status"].values())
    if total <= 0:
        e.add_field(name=tr("🎭 ステータス使用割合"), value=tr("まだ記録がありません"), inline=False)
    else:
        lines = [tr("{emoji} {k} **{pct:.1f}%** ({hours:.1f}時間)", emoji=STATUS.get(k, ('❔',))[0],
                    k=k if k != 'unknown' else tr("不明"), pct=v / total * 100, hours=v / 3600)
                 for k, v in sorted(ss.items(), key=lambda kv: -kv[1])]
        e.add_field(name=tr("🎭 ステータス使用割合 (ゲーム内の滞在時間ベース)"), value="\n".join(lines), inline=False)
    if names:
        per = res["per"]
        order = sorted(names, key=lambda u: (-per[u]["logins"], (names[u] or "").lower()))
        lines = []
        for u in order[:10]:
            p, nm = per[u], esc(names[u])
            if p["logins"]:
                peak = max(range(24), key=lambda x: (p["hours"][x], -x))
                lines.append(tr("**{name}** — {logins}回 / 最多 {peak}時台 / {hours:.1f}h",
                                name=nm, logins=p["logins"], peak=peak, hours=p["seconds"] / 3600))
            elif p["seconds"]:
                lines.append(tr("**{name}** — {hours:.1f}h (ログイン記録なし)", name=nm, hours=p["seconds"] / 3600))
            else:
                lines.append(tr("**{name}** — 記録なし", name=nm))
        if len(order) > 10: lines.append(tr("…他{n}人", n=len(order) - 10))
        e.add_field(name=tr("👥 フレンド別 (ログイン回数順)"), value="\n".join(lines), inline=False)
    e.set_footer(text=tr("ゲーム内のログインのみ集計(Webのみは対象外)。集計開始後に登録したフレンドは登録後の分だけです。"))
    return e


class ConfirmRemove(discord.ui.View):
    """削除前の確認 (所有者のみ操作可・60秒でタイムアウト)"""
    def __init__(self, bot, row):
        super().__init__(timeout=60)
        self.yes.label, self.no.label = tr("削除する"), tr("キャンセル")  # ボタン名は生成時の言語で
        self.bot, self.uid, self.name = bot, row["uid"], row["name"]
        self.message = None

    async def interaction_check(self, i):
        if i.user.id != OWNER:
            await i.response.send_message(tr("所有者のみ操作できます。"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="削除する", style=discord.ButtonStyle.danger)
    async def yes(self, i: discord.Interaction, b: discord.ui.Button):
        row = self.bot.db.get(self.uid)
        if not row or not row["active"]:
            await i.response.edit_message(content=tr("すでに削除されています。"), embed=None, view=None)
            return self.stop()
        self.bot.db.deactivate(self.uid)
        self.bot.last_loc.pop(self.uid, None)
        self.bot.last_status.pop(self.uid, None)
        self.bot.stats.reconcile(self.uid, False, None)  # 削除時点でゲーム内区間を閉じる
        self.bot.ingame.discard(self.uid)
        log.info("friend removed by=%s uid=%s name=%s", i.user.id, self.uid, row["name"])
        e = discord.Embed(title=tr("➖ メンバー削除"), description=f"**{esc(row['name'])}**\n`{self.uid}`", color=0xE74C3C)
        try:
            await self.bot.send_to(self.uid, embed=e)  # メンバーチャンネルにも履歴を残す
        except discord.HTTPException:
            log.exception("failed to write removal log to member channel uid=%s", self.uid)
        await i.response.edit_message(
            content=tr("🗑️ **{name}** を削除しました (チャンネルは保持): <#{ch}>", name=esc(row["name"]), ch=row["channel_id"]),
            embed=e, view=None)
        self.stop()

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def no(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content=tr("キャンセルしました: {name}", name=esc(self.name)), embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        if self.message:
            try: await self.message.edit(content=tr("確認がタイムアウトしました。削除していません。"), embed=None, view=None)
            except discord.HTTPException: pass


class ListView(discord.ui.View):
    PER = 10

    def __init__(self, rows, show_uid):
        super().__init__(timeout=120)
        self.rows, self.show_uid, self.page, self.message = rows, show_uid, 0, None
        self.pages = max(1, -(-len(rows) // self.PER))
        self._sync()

    def _sync(self):
        self.prev.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def embed(self):
        chunk = self.rows[self.page * self.PER:(self.page + 1) * self.PER]
        lines = []
        for r in chunk:
            mark = "✅" if r["active"] else tr("🚫(削除済み)")
            line = f"{mark} **{esc(r['name'])}** <#{r['channel_id']}>"
            if self.show_uid: line += f"\n　`{r['uid']}`"
            lines.append(line)
        active = sum(1 for r in self.rows if r["active"])
        e = discord.Embed(title=tr("VRChat 登録フレンド ({n}人)", n=active), description="\n".join(lines), color=0x3498DB)
        e.set_footer(text=tr("ページ {p}/{n}", p=self.page + 1, n=self.pages))
        return e

    async def interaction_check(self, i):
        if i.user.id != OWNER:
            await i.response.send_message(tr("所有者のみ操作できます。"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, i: discord.Interaction, b: discord.ui.Button):
        self.page -= 1; self._sync()
        await i.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, i: discord.Interaction, b: discord.ui.Button):
        self.page += 1; self._sync()
        await i.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self):
        for c in self.children: c.disabled = True
        if self.message:
            try: await self.message.edit(view=self)
            except discord.HTTPException: pass


class FriendGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="friend", description="VRChatフレンド管理")
        self.bot = bot
        self.add_lock = asyncio.Lock()  # 同時追加でチャンネルが二重作成されるのを防ぐ

    async def interaction_check(self, i: discord.Interaction):
        if i.user.id != OWNER or i.channel_id != MAIN_CH:
            await i.response.send_message(tr("メインチャンネルで所有者のみ実行できます。"), ephemeral=True)
            return False
        return True

    async def vrc_call(self, fn, *args):
        """VRChat API呼び出し。タイムアウト付き。401なら1回だけ再ログインして再試行。"""
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), 20)
        except Exception as e:
            if getattr(e, "status", None) != 401:
                raise
            log.warning("VRChat 401 -> relogin once")
            await asyncio.wait_for(asyncio.to_thread(self.bot.vrc.login), 30)
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), 20)

    # ---------- /friend add ----------
    @app_commands.command(name="add", description="VRChatプロフィールURLからフレンドを追加")
    @app_commands.describe(url="https://vrchat.com/home/user/usr_... のURL (usr_...のIDも可)")
    async def add(self, i: discord.Interaction, url: str):
        uid = extract_uid(url)
        if not uid:
            return await i.response.send_message(
                tr("URLの形式が不正です。`https://vrchat.com/home/user/usr_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` を指定してください。"))
        await i.response.defer()
        try:
            u = await self.vrc_call(self.bot.vrc.get_user, uid)
        except Exception as e:
            log.warning("add: get_user failed uid=%s: %r", uid, e)
            return await i.followup.send(tr("❌ {msg}", msg=explain_error(e)))
        async with self.add_lock:
            existing = self.bot.db.get(uid)
            if existing and existing["active"]:
                return await i.followup.send(tr("すでに登録済みです: **{name}** <#{ch}>", name=esc(existing["name"]), ch=existing["channel_id"]))
            try:
                ch = await self.bot.friend_channel(uid, u["name"])
            except discord.HTTPException as e:
                log.exception("add: channel creation failed uid=%s", uid)
                return await i.followup.send(tr("❌ チャンネル作成に失敗しました (Botの権限を確認): {status}", status=e.status))
            self.bot.db.upsert(uid, u["name"], ch.id)
        self.bot.seed(uid, u)
        self.bot.stats.reconcile(uid, uid in self.bot.ingame, u["status"])
        log.info("friend added by=%s uid=%s name=%s rejoin=%s", i.user.id, uid, u["name"], bool(existing))
        warn = "" if u["is_friend"] else tr("\n⚠️ このアカウントとフレンドではないため、通知は届きません。")
        e = discord.Embed(title=tr("➕ メンバー追加") + (tr("(再登録)") if existing else ""),
                          description=f"**{esc(u['name'])}**\n`{uid}`", color=0x2ECC71)
        try: await ch.send(embed=e)
        except discord.HTTPException: log.exception("add: failed to write log to member channel")
        await i.followup.send(tr("✅ 追加しました: **{name}** → {ch}{warn}", name=esc(u["name"]), ch=ch.mention, warn=warn), embed=e)

    # ---------- /friend remove ----------
    def resolve(self, value):
        """オートコンプリート値(UID)から登録行を探す。手入力された名前も、一意なら許容。"""
        value = (value or "").strip()
        uid = extract_uid(value)
        if uid:
            row = self.bot.db.get(uid)
            return (row, None) if row and row["active"] else (None, tr("その登録は存在しません。"))
        hits = [r for r in self.bot.db.active() if (r["name"] or "").lower() == value.lower()]
        if len(hits) == 1: return hits[0], None
        if len(hits) > 1: return None, tr("同名のユーザーが複数います。候補一覧から選択してください。")
        return None, tr("その登録は存在しません。候補一覧から選択してください。")

    @app_commands.command(name="remove", description="登録済みフレンドを削除 (チャンネルは残ります)")
    @app_commands.describe(target="候補から選択 (表示名の末尾はUIDの下6桁)")
    async def remove(self, i: discord.Interaction, target: str):
        row, err = self.resolve(target)
        if err:
            return await i.response.send_message(err)
        e = discord.Embed(title=tr("このメンバーを削除しますか？"), color=0xE67E22,
                          description=tr("**{name}**\n`{uid}`\nチャンネル: <#{ch}> (削除されません)", name=esc(row["name"]), uid=row["uid"], ch=row["channel_id"]))
        view = ConfirmRemove(self.bot, row)
        await i.response.send_message(embed=e, view=view)
        view.message = await i.original_response()

    @remove.autocomplete("target")
    async def remove_ac(self, i: discord.Interaction, current: str):
        if i.user.id != OWNER:  # autocompleteにはinteraction_checkが効かないため明示的に制限
            return []
        cur = (current or "").strip().lower()
        out, seen = [], set()
        for r in self.bot.db.active():
            name = r["name"] or r["uid"]
            if cur and cur not in name.lower() and cur not in r["uid"]:
                continue
            # 同名・類似名でも区別できるようUID下6桁を付ける(衝突時は12桁→連番)。valueはUID。
            label = f"{name[:80]} (…{r['uid'][-6:]})"
            if label in seen: label = f"{name[:70]} (…{r['uid'][-12:]})"
            n = 1
            while label in seen:
                n += 1; label = f"{name[:70]} (…{r['uid'][-12:]}) #{n}"
            seen.add(label)
            out.append(app_commands.Choice(name=label[:100], value=r["uid"]))
            if len(out) >= 25:  # Discordの候補上限
                break
        return out

    # ---------- /friend list ----------
    @app_commands.command(name="list", description="登録一覧")
    @app_commands.describe(show_uid="UIDも表示する", include_removed="削除済みも表示する")
    async def list_(self, i: discord.Interaction, show_uid: bool = False, include_removed: bool = False):
        rows = self.bot.db.all() if include_removed else self.bot.db.active()
        if not rows:
            return await i.response.send_message(tr("登録なし"))
        view = ListView(rows, show_uid)
        if view.pages == 1:
            return await i.response.send_message(embed=view.embed())
        await i.response.send_message(embed=view.embed(), view=view)
        view.message = await i.original_response()


if __name__ == "__main__":
    Bot().run(TOKEN)

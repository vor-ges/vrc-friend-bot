"""オフライン単体テスト: python test_local.py (Discord/VRChatへ接続しません)"""
import os, re, sys, time, asyncio, tempfile, types
from vrc import extract_uid, explain_error

U = "usr_12345678-1234-1234-1234-123456789abc"
OK = [f"https://vrchat.com/home/user/{U}", f"https://www.vrchat.com/home/user/{U}/",
      f"http://vrchat.com/home/user/{U}?x=1#y", f"<https://vrchat.com/home/user/{U}>", f"  {U}  ", U.upper().replace("USR_", "usr_")]
BAD = ["", "abc", "usr_123", f"https://evil.com/home/user/{U}", f"https://vrchat.com.evil.com/home/user/{U}",
       f"https://vrchat.com@evil.com/home/user/{U}", f"https://evil.com@vrchat.com/home/user/{U}",
       f"https://vrchat.com:8080/home/user/{U}", f"https://vrchat.com/home/world/{U}",
       f"https://vrchat.com/home/user/{U}/extra", f"ftp://vrchat.com/home/user/{U}", "https://vrchat.com/home/user/usr_zzzz",
       "x" * 400, None]
for s in OK: assert extract_uid(s) == U, s
for s in BAD: assert extract_uid(s) is None, s
class E(Exception):
    def __init__(s, st): s.status = st
assert "存在しません" in explain_error(E(404)) and "認証" in explain_error(E(401)) and "レート" in explain_error(E(429))
assert "タイムアウト" in explain_error(asyncio.TimeoutError())

# --- DB + autocomplete / resolve (OWNER制限・25件上限・同名区別) ---
os.environ.update(DISCORD_TOKEN="x", GUILD_ID="1", MAIN_CHANNEL_ID="2", OWNER_ID="99", VRC_USERNAME="u", VRC_PASSWORD="p")
os.chdir(tempfile.mkdtemp())
import bot as B
from db import DB
db = DB(":memory:")
def uid(n): return f"usr_{n:08x}-0000-0000-0000-000000000000"
for n in range(40): db.upsert(uid(n), "Alice" if n < 3 else f"User{n}", 1000 + n)
db.upsert(uid(99), "Gone", 5); db.deactivate(uid(99))
g = B.FriendCommands(types.SimpleNamespace(db=db))
async def run():
    owner, other = types.SimpleNamespace(user=types.SimpleNamespace(id=99)), types.SimpleNamespace(user=types.SimpleNamespace(id=1))
    assert await g.remove_ac(other, "") == []
    c = await g.remove_ac(owner, "")
    assert len(c) == 25 and all(len(x.name) <= 100 and len(x.value) <= 100 for x in c)
    a = await g.remove_ac(owner, "alice")
    assert len(a) == 3 and len({x.name for x in a}) == 3 and all(x.value.startswith("usr_") for x in a), a  # 同名でも区別できる
    assert await g.remove_ac(owner, "gone") == []  # 削除済みは候補に出ない
asyncio.run(run())
assert g.resolve(uid(5))[0]["name"] == "User5"
assert g.resolve(uid(99))[0] is None and g.resolve(uid(500))[0] is None
assert "複数" in g.resolve("alice")[1] and g.resolve("user7")[0]["uid"] == uid(7)
lv = B.ListView(db.active(), True); assert lv.pages == 4 and len(lv.embed().description) < 4096
print("ALL TESTS PASSED")

# --- インスタンスオーナー表示 ---
W = "wrld_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
assert B.parse_location(f"{W}:123")[4] is None  # Public: オーナーなし
assert B.parse_location(f"{W}:123~hidden(usr_x)~region(jp)")[2:] == ("Friends+", "jp", ("usr", "usr_x"))
assert B.parse_location(f"{W}:123~friends(usr_x)~region(us)")[4] == ("usr", "usr_x")
assert B.parse_location(f"{W}:123~private(usr_x)~canRequestInvite~region(jp)")[2:4] == ("Invite+", "jp")
assert B.parse_location(f"{W}:123~group(grp_y)~groupAccessType(plus)~region(jp)")[2:] == ("Group+", "jp", ("grp", "grp_y"))

class FakeVRC:
    calls = 0
    def get_world(s, w): return {"name": "W", "author": "AUTHOR", "capacity": 32, "thumb": None, "desc": "d"}
    def get_instance(s, w, i): return {"n_users": 5, "capacity": 16}
    def get_user(s, u): s.calls += 1; return {"name": "OwnerUser"}
    def get_group_name(s, g): s.calls += 1; return "MyGroup"
import discord
async def embed_for(loc, bot):
    e = discord.Embed(); await bot.world_embed_fields(loc, e)
    return {f.name: f.value for f in e.fields}
async def run2():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:")
    f = await embed_for(f"{W}:1~group(grp_y)~groupAccessType(members)~region(jp)", bot)
    assert f["オーナー"] == "MyGroup (グループ)" and "作者" not in f, f
    f = await embed_for(f"{W}:1~hidden(usr_o)~region(jp)", bot)
    assert f["オーナー"] == "OwnerUser" and f["インスタンス"] == "Friends+ (JP)" and f["人数"] == "5/16", f
    await embed_for(f"{W}:1~hidden(usr_o)~region(jp)", bot)
    assert bot.vrc.calls == 2  # キャッシュでAPI再呼び出しなし
    bot.db.upsert("usr_known", "KnownFriend", 1)
    assert (await embed_for(f"{W}:1~friends(usr_known)", bot))["オーナー"] == "KnownFriend"  # 登録済みはAPI不要
    assert bot.vrc.calls == 2
    assert "オーナー" not in await embed_for(f"{W}:1", bot)  # Public
    bot.vrc.get_user = lambda u: (_ for _ in ()).throw(RuntimeError("x"))
    assert (await embed_for(f"{W}:1~private(usr_fail)", bot))["オーナー"] == "取得不可"
asyncio.run(run2())
print("OWNER TESTS PASSED")

# --- ゲーム内/Webの区別 (オフライン連続通知の防止) ---
async def run3():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:")
    bot.db.upsert("usr_a", "Alice", 1)
    sent = []
    async def fake_send(uid, **kw): sent.append(kw["embed"].title)
    bot.send_to = fake_send
    P = f"{W}:1~friends(usr_o)~region(jp)"
    ev = lambda t, **c: bot.handle({"type": t, "content": {"userId": "usr_a", **c}})
    async def case(label, steps, expect):
        sent.clear(); bot.ingame.clear(); bot.last_loc.clear()
        for s in steps: await s
        assert sent == expect, (label, sent)
    ON, OFF = "🟢 Alice がオンライン", "⚫ Alice がオフライン"
    await case("Webだけ(active→offline)", [ev("friend-active", platform="web"), ev("friend-offline")], [])
    await case("ゲーム→offline→offline", [ev("friend-online", platform="standalonewindows", location=P), ev("friend-offline"), ev("friend-offline")], [ON, OFF])
    await case("Web→ゲーム→offline→Web offline", [ev("friend-active", platform="web"), ev("friend-online", platform="android", location="private"),
               ev("friend-offline"), ev("friend-offline")], [ON, OFF])
    await case("ゲーム終了しWebだけ残る", [ev("friend-online", platform="standalonewindows", location="private"), ev("friend-active", platform="web"), ev("friend-offline")], [ON, OFF])
    await case("friend-onlineがweb", [ev("friend-online", platform="web"), ev("friend-offline")], [])
    await case("location offlineは無視", [ev("friend-location", location="offline"), ev("friend-offline")], [])
    # active のキーが小文字 userid でも処理できる
    sent.clear(); bot.ingame.add("usr_a")
    await bot.handle({"type": "friend-active", "content": json.dumps({"userid": "usr_a", "platform": "web"})})
    assert len(sent) == 1 and "usr_a" not in bot.ingame
    # 場所だけ届いた(online取りこぼし)場合もゲーム内として復元され、後のofflineが通知される
    sent.clear(); bot.ingame.clear(); bot.last_loc.clear()
    await ev("friend-location", location=P); await ev("friend-offline")
    assert sent == ["🚪 Alice が移動", "⚫ Alice がオフライン"], sent
    # 起動時のseed: state=online ならゲーム内、active/offline ならそうでない
    bot.ingame.clear(); bot.seed("usr_a", {"status": "active", "desc": "", "state": "online"}); assert "usr_a" in bot.ingame
    bot.seed("usr_a", {"status": "active", "desc": "", "state": "active"}); assert "usr_a" not in bot.ingame
    sent.clear(); bot.seed("usr_a", {"status": "active", "desc": "", "state": "online"}); await ev("friend-offline")
    assert len(sent) == 1
import json
asyncio.run(run3())
print("INGAME TESTS PASSED")

# ================= 統計 (/stats) =================
from datetime import datetime, timedelta, timezone
from stats import Stats
JST = timezone(timedelta(hours=9))
BASE = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=10)
T = lambda d, h=0, m=0: (BASE + timedelta(days=d - 1, hours=h, minutes=m)).timestamp()  # BASE=10日前の0:00(JST)
def mkstats():
    d = DB(":memory:"); s = Stats(d.c, JST)
    s.c.execute("UPDATE stats_meta SET v=? WHERE k='since'", (str(T(1)),)); s.c.commit()
    return s

# --- 集計ロジック ---
s = mkstats(); R = s.record
R("A", "login", "join me", T(1, 21)); R("A", "status", "busy", T(1, 22)); R("A", "logout", None, T(1, 23, 30))
R("B", "login", "active", T(1, 21, 30)); R("B", "logout", None, T(1, 22)); R("B", "login", "active", T(2, 3)); R("B", "logout", None, T(2, 4))
r = s.summarize(["A", "B"], T(1), T(3))
a, b, tot = r["per"]["A"], r["per"]["B"], r["total"]
assert a["status"]["join me"] == 3600 and a["status"]["busy"] == 5400 and a["logins"] == 1, dict(a["status"])
assert b["status"]["active"] == 5400 and b["logins"] == 2
assert tot["logins"] == 3 and tot["hours"][21] == 2 and tot["hours"][3] == 1 and sum(tot["hours"]) == 3  # 時間帯はJST
assert tot["seconds"] == 14400
# 期間の切り出し: 22:30以降だけ -> 21時のログインは数えず、滞在はbusyの1時間のみ
r = s.summarize(["A"], T(1, 22, 30), T(3)); assert r["total"]["logins"] == 0 and r["total"]["status"]["busy"] == 3600 and "join me" not in r["total"]["status"]
# resumeは頻度に数えないが滞在には数える / 継続中は終了時刻まで / 二重ログイン / ゲーム外のステータス変更は無視
R("C", "resume", "busy", T(1, 20)); R("C", "logout", None, T(1, 21))
R("D", "login", "ask me", T(1, 20))
R("E", "login", "busy", T(1, 20)); R("E", "login", "active", T(1, 21)); R("E", "logout", None, T(1, 22))
R("F", "status", "busy", T(1, 19)); R("F", "login", "active", T(1, 20)); R("F", "logout", None, T(1, 21)); R("F", "status", "busy", T(1, 22))
r = s.summarize(list("CDEF"), T(1), T(1, 22))["per"]
assert r["C"]["logins"] == 0 and r["C"]["status"]["busy"] == 3600
assert r["D"]["status"]["ask me"] == 7200
assert r["E"]["logins"] == 2 and r["E"]["status"]["busy"] == 3600 and r["E"]["status"]["active"] == 3600
assert r["F"]["status"]["active"] == 3600 and "busy" not in r["F"]["status"]
assert s.summarize([], T(1), T(2))["total"]["logins"] == 0
# reconcile: 停止中のズレ補正
s = mkstats()
s.reconcile("G", True, "busy"); assert s.state("G")[:2] == (True, "busy")            # 履歴なし+ゲーム内 -> resume
s.reconcile("G", True, "busy"); assert s.c.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 1  # 同状態は追記なし
s.reconcile("G", True, "active"); assert s.state("G")[:2] == (True, "active")        # ステータス変化を反映
s.record("H", "login", "active", T(1, 20)); s.reconcile("H", False, None, close_at=T(1, 21, 30))
assert s.state("H")[0] is False and s.summarize(["H"], T(1), T(2))["total"]["seconds"] == 5400  # 停止直前の時刻で閉じる
s.reconcile("I", False, None); assert s.state("I") == (False, None, None)            # 何もなければ何もしない

# --- イベント -> 記録 / コマンド ---
class FI:
    def __init__(s, uid, ch):
        s.user = types.SimpleNamespace(id=uid); s.channel_id = ch; s.out = None
        s.response = types.SimpleNamespace(send_message=s._send, edit_message=s._edit, defer=s._defer)
        s.followup = types.SimpleNamespace(send=s._send)
    async def _defer(s, **kw): pass
    async def _send(s, content=None, **kw): s.out = (content, kw)
    async def _edit(s, **kw): s.out = ("edit", kw)
def kinds(st, uid): return [(r["kind"], r["status"]) for r in st.c.execute("SELECT kind,status FROM activity WHERE uid=? ORDER BY ts,id", (uid,))]
async def run4():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST)
    bot.db.upsert("usr_a", "Alice", 111); bot.db.upsert("usr_b", "Bob*", 222)
    async def fake_send(uid, **kw): pass
    bot.send_to = fake_send
    ev = lambda t, uid="usr_a", **c: bot.handle({"type": t, "content": {"userId": uid, **c}})
    await ev("friend-active", platform="web"); await ev("friend-offline")                       # Webだけ -> 記録なし
    await ev("friend-update", user={"status": "busy"})                                          # ゲーム外のステータス変更 -> 記録なし
    assert kinds(bot.stats, "usr_a") == []
    await ev("friend-online", platform="standalonewindows", location="private", user={"status": "join me"})
    await ev("friend-update", user={"status": "busy"}); await ev("friend-update", user={"status": "busy", "statusDescription": "x"})  # 同ステータスは1回
    await ev("friend-offline"); await ev("friend-offline")
    assert kinds(bot.stats, "usr_a") == [("login", "join me"), ("status", "busy"), ("logout", None)], kinds(bot.stats, "usr_a")
    await ev("friend-location", location="private"); assert kinds(bot.stats, "usr_a")[-1][0] == "resume"   # online取りこぼし -> resume
    await ev("friend-online", platform="web"); assert len([k for k in kinds(bot.stats, "usr_a") if k[0] == "login"]) == 1
    # コマンド: 現実的なデータで表示を確認
    bot.stats.c.execute("DELETE FROM activity"); bot.stats.c.execute("UPDATE stats_meta SET v=? WHERE k='since'", (str(T(1)),)); bot.stats.c.commit()
    for d in range(1, 9):
        bot.stats.record("usr_a", "login", "join me", T(d, 21)); bot.stats.record("usr_a", "status", "busy", T(d, 22)); bot.stats.record("usr_a", "logout", None, T(d, 23, 30))
    bot.stats.record("usr_b", "login", "active", T(2, 9)); bot.stats.record("usr_b", "logout", None, T(2, 10))
    cb = bot.make_stats_command().callback
    i = FI(1, 2); await cb(i, None); assert i.out[1].get("ephemeral") and "所有者" in i.out[0]           # 他人は拒否
    i = FI(99, 999); await cb(i, None); assert i.out[1].get("ephemeral")                                 # 無関係チャンネルは拒否
    i = FI(99, 2); await cb(i, None); e = i.out[1]["embed"]
    f = {x.name: x.value for x in e.fields}
    assert "全員" in e.title and "集計期間" in e.description and "ゲーム内ログイン" in e.description and "9回" in e.description
    assert "21時台(8回)" in f["⏰ ログイン頻度 (時間帯別)"] and "09時台" not in f["⏰ ログイン頻度 (時間帯別)"] or "9時台(1回)" in f["⏰ ログイン頻度 (時間帯別)"]
    st = [v for k, v in f.items() if k.startswith("🎭")][0]
    assert "join me" in st and "busy" in st and "active" in st, st   # ステータス別の割合
    assert abs(sum(float(x) for x in re.findall(r"\*\*([\d.]+)%\*\*", st)) - 100) < 0.2
    fr = [v for k, v in f.items() if k.startswith("👥")][0]; assert "Alice" in fr and "最多 21時台" in fr and "Bob\\*" in fr  # 名前はエスケープ
    i = FI(99, 111); await cb(i, 3); e = i.out[1]["embed"]                                               # フレンドチャンネル+days
    exp = sum(1 for d in range(1, 9) if T(d, 21) >= time.time() - 3 * 86400)  # 実行時刻に依存するので期待値は計算で出す
    assert "Alice" in e.title and not any(x.name.startswith("👥") for x in e.fields) and f"{exp}回" in e.description and "約3.0日間" in e.description, e.description
    bot.db.deactivate("usr_b"); i = FI(99, 222); await cb(i, None); assert "削除済み" in i.out[1]["embed"].title  # 削除済みも履歴を見られる
    # 巨大データでもDiscord上限(フィールド1024/全体6000)に収まる
    for n in range(40):
        bot.db.upsert(f"usr_{n:02d}", "名前" * 12, 5000 + n)
        for h in range(24): bot.stats.record(f"usr_{n:02d}", "login", "active", T(3, h)); bot.stats.record(f"usr_{n:02d}", "logout", None, T(3, h, 30))
    i = FI(99, 2); await cb(i, None); e = i.out[1]["embed"]
    assert all(len(x.value) <= 1024 for x in e.fields) and len(e) <= 6000 and len(e.description) <= 4096, (len(e), [len(x.value) for x in e.fields])
    assert "…他" in [x.value for x in e.fields if x.name.startswith("👥")][0]
    # 削除(通知を止める)してもデータ収集は続く: ゲーム内状態は閉じない
    bot.stats.record("usr_a", "login", "active"); bot.ingame.add("usr_a")
    view = B.ConfirmRemove(bot, bot.db.get("usr_a")); await view.yes.callback(FI(99, 2))
    assert bot.db.get("usr_a")["active"] == 0 and bot.stats.state("usr_a")[0] is True and "usr_a" in bot.ingame
    # 起動時の最初の同期: 停止中にゲームを抜けていた人は、前回の生存時刻で閉じる
    bot.db.upsert("usr_a", "Alice", 111); bot.stats.c.execute("DELETE FROM activity WHERE uid='usr_a'"); bot.stats.c.commit()
    bot.stats.record("usr_a", "login", "busy", T(1, 20)); bot.stats.prev_alive = T(1, 21); bot.ingame.add("usr_a")
    bot.vrc.get_friends_all = lambda: [{"uid": "usr_a", "name": "Alice", "status": "active", "desc": "", "location": "offline", "ingame": False}]
    await bot.sync_friends()
    assert bot.stats.state("usr_a")[0] is False and bot.stats.state("usr_a")[2] == T(1, 21) and "usr_a" not in bot.ingame
asyncio.run(run4())

# --- スラッシュコマンド定義 ---
from discord import app_commands
_t = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
_c = B.Bot().make_stats_command(); _t.add_command(_c, guild=discord.Object(1))
_o = _c.to_dict(_t)["options"][0]; assert _o["name"] == "days" and not _o.get("required") and _o["min_value"] == 1 and _o["max_value"] == 365
print("STATS TESTS PASSED")

# ================= 言語切り替え (/lang) =================
import ast, inspect, i18n
JP = re.compile(r"[ぁ-んァ-ヶ一-龠]")
assert i18n.get_lang() == "ja"
assert i18n.tr("所有者のみ実行できます。") == "所有者のみ実行できます。"          # 既定のjaは従来表示と同一
assert "存在しません" in explain_error(E(404))

# --- 翻訳の網羅性: bot/vrcの tr("...") 全キーに英訳があり、{}プレースホルダが一致する ---
def tr_keys(path):
    ks = set()
    for n in ast.walk(ast.parse(open(path).read())):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args and isinstance(n.args[0], ast.Constant):
            ks.add(n.args[0].value)
    return ks
keys = tr_keys(B.__file__) | tr_keys(inspect.getsourcefile(explain_error))
EN = i18n.TABLES["en"]
ph = lambda s: sorted(re.findall(r"\{[^}]*\}", s))
assert len(keys) > 60 and not [k for k in keys if k not in EN], [k for k in keys if k not in EN]
assert not [k for k in keys if ph(k) != ph(EN[k])], [k for k in keys if ph(k) != ph(EN[k])]
assert not [k for k, v in EN.items() if JP.search(v)], [k for k, v in EN.items() if JP.search(v)]   # 英訳に日本語が残っていない
assert not [k for k in EN if k not in keys], [k for k in EN if k not in keys]                       # 使われない訳が溜まっていない

# --- 切り替え・フォールバック・永続化 ---
i18n.set_lang("en")
assert i18n.tr("{name} (グループ)", name="G") == "G (Group)" and i18n.tr("表に無い日本語") == "表に無い日本語"
assert i18n.tr("{name} (グループ)") == "{name} (Group)"      # 引数なしは未整形のまま返す(例外にしない)
assert i18n.tr("❌ {msg}", msg="boom") == "❌ boom"               # {msg} という名前の書式引数も渡せる(以前は例外になっていた)
assert i18n.tr("{name} (グループ)", wrong=1) == "{name} (グループ)"   # 引数名が違っても例外にせず原文で返す(通知を止めない)
try: i18n.set_lang("xx"); raise SystemExit("unsupported lang accepted")
except ValueError: pass
assert i18n.get_lang() == "en"
i18n.set_lang("ja")
for c, want in [("en", "en"), ("EN", "en"), (" eng ", "en"), ("en-US", "en"), ("en_GB", "en"), ("ja", "ja"), ("jpn", "ja"),
                ("JA", "ja"), ("ja-JP", "ja")]:
    assert i18n.resolve(c) == want, c                                     # ISO 639-1/2、大小文字・地域つき表記
for c in ["", " ", "e", "fr", "jp", "JP", "jpx", "english", "日本語", None, "-", "xx-en"]:   # jp はISO 639ではないので不可
    assert i18n.resolve(c) is None, c
_d = DB(":memory:"); assert i18n.load(_d.c) == "ja"                  # 設定が無い(旧DB)ならja
i18n.save(_d.c, "en"); i18n.set_lang("ja"); assert i18n.load(_d.c) == "en"   # 再起動後も保持
i18n.save(_d.c, "zz"); assert i18n.load(_d.c) == "ja"                # 壊れた値はjaに戻す
assert i18n.load(_d.c) == "ja"                                       # 再実行(冪等)
i18n.set_lang("ja")

# --- /lang コマンドと英語での実表示 ---
async def run5():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST)
    bot.db.upsert("usr_a", "Alice", 111)
    sent = []
    async def fake_send(uid, **kw): sent.append(kw["embed"])
    bot.send_to = fake_send
    lang = bot.make_lang_command().callback
    i = FI(1, 2); await lang(i, "en"); assert i.out[1].get("ephemeral") and i18n.get_lang() == "ja"   # 他人は変更不可
    i = FI(1, 2); await lang(i, "fr"); assert i.out[1].get("ephemeral") and "所有者" in i.out[0]         # 他人には対応コードも教えない
    i = FI(99, 2); await lang(i, "en"); assert i.out[0] == "Language switched to English." and i18n.get_lang() == "en"
    assert bot.db.c.execute("SELECT v FROM bot_settings WHERE k='lang'").fetchone()[0] == "en"          # DBに保存
    i = FI(99, 2); await lang(i, "fr"); assert i.out[1].get("ephemeral") and i.out[0] == "Unsupported language. Available codes: ja, en"
    assert i18n.get_lang() == "en"                                                                     # 失敗しても言語は変わらない
    i = FI(99, 2); await lang(i, "EN-us"); assert i.out[0] == "Language switched to English."          # 大小文字・地域つきでも可
    # 通知(オンライン/移動/ステータス/オフライン)が英語になる
    ev = lambda t, **c: bot.handle({"type": t, "content": {"userId": "usr_a", **c}})
    P = f"{W}:1~group(grp_y)~groupAccessType(plus)~region(jp)"
    await ev("friend-online", platform="standalonewindows", location=P, user={"status": "join me"})
    e = sent[-1]; assert e.title == "🟢 Alice is online", e.title
    f = {x.name: x.value for x in e.fields}
    assert {"Platform", "World", "Instance", "Players", "Owner"} <= set(f) and f["Owner"] == "MyGroup (Group)", f
    await ev("friend-location", location=f"{W}:2~region(jp)"); assert sent[-1].title == "🚪 Alice moved"
    await ev("friend-update", user={"status": "busy", "statusDescription": "x"}); e = sent[-1]
    assert e.title.endswith("Alice changed status") and [x.name for x in e.fields] == ["Before", "After"] or [x.name for x in e.fields] == ["After"], e.fields
    await ev("friend-offline"); assert sent[-1].title == "⚫ Alice went offline"
    assert "does not exist" in explain_error(E(404))
    # 統計(コマンド)も英語
    bot.stats.c.execute("UPDATE stats_meta SET v=? WHERE k='since'", (str(T(1)),)); bot.stats.c.commit()
    bot.stats.record("usr_a", "login", "busy", T(2, 21)); bot.stats.record("usr_a", "logout", None, T(2, 22))
    i = FI(99, 2); await bot.make_stats_command().callback(i, None); e = i.out[1]["embed"]
    assert "Login stats" in e.title and "Period" in e.description and "In-game logins" in e.description and not JP.search(e.title + e.description), e.description
    assert not any(JP.search(x.name + x.value) for x in e.fields), [(x.name, x.value) for x in e.fields if JP.search(x.name + x.value)]
    assert "Unknown" not in str([x.value for x in e.fields]) and "busy" in str([x.value for x in e.fields])
    # ボタン名・一覧も英語 / jaに戻すと日本語に戻る
    v = B.ConfirmRemove(bot, bot.db.get("usr_a")); assert (v.yes.label, v.no.label) == ("Remove", "Cancel")
    assert "registered friends" in B.ListView(bot.db.active(), False).embed().title
    i = FI(99, 2); await lang(i, "jp"); assert i.out[1].get("ephemeral") and i18n.get_lang() == "en"   # jpは未対応(ISO 639ではない)
    i = FI(99, 2); await lang(i, "jpn"); assert i18n.get_lang() == "ja" and "切り替えました" in i.out[0]   # 3文字コードで日本語へ
    assert bot.db.c.execute("SELECT v FROM bot_settings WHERE k='lang'").fetchone()[0] == "ja"          # 保存されるのは正規コード
    v = B.ConfirmRemove(bot, bot.db.get("usr_a")); assert (v.yes.label, v.no.label) == ("削除する", "キャンセル")
    await ev("friend-online", platform="android", location="private"); assert sent[-1].title == "🟢 Alice がオンライン"
asyncio.run(run5())
assert i18n.get_lang() == "ja"

# --- /lang の定義 (引数は省略可・選択肢はja/en) ---
_t2 = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
_c2 = B.Bot().make_lang_command(); _t2.add_command(_c2, guild=discord.Object(1))
_d2 = _c2.to_dict(_t2); _o2 = _d2["options"][0]
assert _d2["name"] == "lang" and len(_d2["options"]) == 1
assert _o2["name"] == "code" and _o2["type"] == 3 and _o2.get("required") is True and not _o2.get("choices") and _o2["min_length"] == 2
print("LANG TESTS PASSED")

# ================= メンション切り替え (/mention) =================
async def run6():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST)
    bot.db.upsert("usr_a", "Alice", 111)
    sent = []
    async def fake_send(uid, **kw): sent.append(kw)
    bot.send_to = fake_send
    ev = lambda t, **c: bot.handle({"type": t, "content": {"userId": "usr_a", **c}})
    online = lambda: ev("friend-online", platform="standalonewindows", location="private", user={"status": "active"})
    assert bot.mention_on is True                                              # 既定はオン(従来動作)
    await online(); assert sent[-1]["content"] == f"<@{B.OWNER}>" and sent[-1]["embed"].title.startswith("🟢")
    await ev("friend-offline"); assert sent[-1].get("content") is None          # オンライン以外はメンションしない
    cmd = bot.make_mention_command().callback
    i = FI(1, 2); await cmd(i, "off"); assert i.out[1].get("ephemeral") and bot.mention_on is True      # 他人は変更不可
    i = FI(99, 2); await cmd(i, "x"); assert i.out[1].get("ephemeral") and bot.mention_on is True       # 不正な値は無視
    i = FI(99, 2); await cmd(i, "off"); assert bot.mention_on is False and i.out[0].startswith("🔕") and "オフ" in i.out[0]
    assert bot.get_setting("mention") == "0"                                    # DBに保存
    n = len(sent); await online()                                               # オフでも通知自体は送る(メンションだけ外す)
    assert len(sent) == n + 1 and sent[-1]["content"] is None and sent[-1]["embed"].title.startswith("🟢")
    # /friend list に状態を表示(全体設定なので先頭に1行)
    g = B.FriendCommands(bot); i = FI(99, 2); await g.do_list(i, False, False)
    assert i.out[1]["embed"].description.startswith("🔕 オンライン通知のメンション(全体設定): オフ") and "Alice" in i.out[1]["embed"].description
    i = FI(99, 2); await cmd(i, "on"); assert bot.mention_on is True and i.out[0].startswith("🔔") and "オン" in i.out[0]
    await ev("friend-offline"); await online(); assert sent[-1]["content"] == f"<@{B.OWNER}>"
    i = FI(99, 2); await g.do_list(i, False, False); assert i.out[1]["embed"].description.startswith("🔔 オンライン通知のメンション(全体設定): オン")
    # 英語
    i18n.set_lang("en")
    i = FI(99, 2); await cmd(i, "off"); assert i.out[0] == "🔕 Online mention (global) turned OFF."
    i = FI(99, 2); await cmd(i, "x"); assert i.out[0] == "Please specify on, off or reset."
    i = FI(99, 2); await g.do_list(i, False, False); assert i.out[1]["embed"].description.startswith("🔕 Online mention (global): OFF")
    i = FI(99, 2); await cmd(i, "on"); assert i.out[0] == "🔔 Online mention (global) turned ON."
    i18n.set_lang("ja")
    assert "オンライン通知のメンション" not in B.ListView(bot.db.active(), False).embed().description   # 引数なしなら従来表示
asyncio.run(run6())

# ---- フレンド別のメンション ----
async def run7():
    bot = B.Bot(); bot.vrc = FakeVRC(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST)
    bot.db.upsert("usr_a", "Alice", 111); bot.db.upsert("usr_b", "Bob*", 222); bot.db.upsert("usr_c", "Gone", 333); bot.db.deactivate("usr_c")
    sent = []
    async def fake_send(uid, **kw): sent.append((uid, kw.get("content")))
    bot.send_to = fake_send
    async def online(uid):
        await bot.handle({"type": "friend-online", "content": {"userId": uid, "platform": "android", "location": "private", "user": {"status": "active"}}})
        n = sent[-1]; await bot.handle({"type": "friend-offline", "content": {"userId": uid}}); return n
    M = f"<@{B.OWNER}>"
    cmd = bot.make_mention_command().callback
    assert [await online(u) for u in ("usr_a", "usr_b")] == [("usr_a", M), ("usr_b", M)]          # 既定: 全員メンション
    i = FI(99, 111); await cmd(i, "off")                                                           # Aliceのチャンネルでoff -> Aliceだけ
    assert i.out[0].startswith("🔕") and "Alice" in i.out[0] and bot.mention_on is True
    assert bot.get_setting("mention:usr_a") == "0" and bot.get_setting("mention") is None or bot.get_setting("mention") == "1"
    assert [await online(u) for u in ("usr_a", "usr_b")] == [("usr_a", None), ("usr_b", M)]
    i = FI(99, 2); await cmd(i, "off")                                                             # メインでoff -> 全体(個別設定のないBobが対象)
    assert "全体設定" in i.out[0] and [await online(u) for u in ("usr_a", "usr_b")] == [("usr_a", None), ("usr_b", None)]
    i = FI(99, 111); await cmd(i, "on")                                                            # 個別onは全体offより優先
    assert i.out[0].startswith("🔔") and [await online(u) for u in ("usr_a", "usr_b")] == [("usr_a", M), ("usr_b", None)]
    i = FI(99, 111); await cmd(i, "reset")                                                         # reset -> 全体設定(off)に従う
    assert "全体設定に戻しました" in i.out[0] and "オフ" in i.out[0] and bot.get_setting("mention:usr_a") is None
    assert (await online("usr_a")) == ("usr_a", None)
    i = FI(99, 2); await cmd(i, "on"); assert (await online("usr_a")) == ("usr_a", M)               # 全体onに戻せば個別なしのAliceも追従
    i = FI(99, 2); await cmd(i, "reset"); assert i.out[1].get("ephemeral") and "フレンド用チャンネル" in i.out[0]  # メインでresetは不可
    i = FI(99, 999); await cmd(i, "off"); assert i.out[1].get("ephemeral") and "メインチャンネルか" in i.out[0]   # 無関係チャンネルは不可
    i = FI(1, 111); await cmd(i, "off"); assert i.out[1].get("ephemeral") and bot.get_setting("mention:usr_a") is None  # 他人は不可
    i = FI(99, 333); await cmd(i, "off"); assert "Gone" in i.out[0]                                # 削除済みフレンドのチャンネルでも設定可
    i = FI(99, 222); await cmd(i, "off"); assert "Bob\\*" in i.out[0]                                # 名前はエスケープ
    # 一覧: 左の印=メンション状態、個別設定には(個別)
    bot.del_setting("mention:usr_c"); bot.mention_on = True
    i = FI(99, 111); await cmd(i, "off")                                                           # Alice=個別off / Bob=個別off(上で設定)
    i = FI(99, 222); await cmd(i, "reset")                                                         # Bobを全体(on)に戻す
    g = B.FriendCommands(bot); i = FI(99, 2); await g.do_list(i, False, True)               # 削除済みも表示
    d = i.out[1]["embed"].description
    row = lambda n: next(l for l in d.split("\n") if n in l)       # 名前を含む行(名前はMarkdownエスケープされる)
    assert row("Alice").startswith("🔕") and "(個別)" in row("Alice")
    assert row("Bob").startswith("🔔") and "(個別)" not in row("Bob")
    assert row("Gone").startswith("🚫") and "✅" not in d and "(個別)=フレンド別の設定" in d
    i18n.set_lang("en")
    i = FI(99, 111); await cmd(i, "on"); assert i.out[0] == "🔔 Online mention for Alice turned ON."
    i = FI(99, 111); await cmd(i, "reset"); assert i.out[0] == "↩️ Alice now follows the global setting (ON)."
    i = FI(99, 111); await cmd(i, "off"); i = FI(99, 2); await g.do_list(i, False, False)
    assert "(custom)" in i.out[1]["embed"].description and "per-friend setting" in i.out[1]["embed"].description
    i = FI(99, 2); await cmd(i, "reset"); assert i.out[0] == "Use reset in a friend's channel."
    i18n.set_lang("ja")
    assert "✅" in B.ListView(bot.db.active(), False).embed().description                          # 設定情報なしなら従来の✅
asyncio.run(run7())

# 再起動しても設定が残る (ファイルDBで確認)
_b1 = B.Bot(); assert _b1.mention_on is True
_b1.set_setting("mention", "0"); _b2 = B.Bot(); assert _b2.mention_on is False
_b2.set_setting("mention", "1"); assert B.Bot().mention_on is True
_b2.set_setting("mention:usr_z", "0"); _b3 = B.Bot(); assert _b3.mention_for("usr_z") is False and _b3.mention_overrides() == {"usr_z": False}
_b3.del_setting("mention:usr_z"); assert B.Bot().mention_overrides() == {} and B.Bot().mention_for("usr_z") is True

# スラッシュコマンド定義 (state: on/off の選択肢・必須)
_t3 = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
_c3 = B.Bot().make_mention_command(); _t3.add_command(_c3, guild=discord.Object(1))
_d3 = _c3.to_dict(_t3); _o3 = _d3["options"][0]
assert _d3["name"] == "mention" and _o3["name"] == "state" and _o3.get("required") is True and [c["value"] for c in _o3["choices"]] == ["on", "off", "reset"]
assert len(_d3["description"]) <= 100
print("MENTION TESTS PASSED")

# ================= コマンド体系: すべてトップレベルの1語コマンド (グループ/サブコマンドなし) =================
async def run8():
    bot = B.Bot(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST)
    bot.db.upsert("usr_a", "Alice", 111)
    fc = B.FriendCommands(bot)
    cmds = fc.commands() + [bot.make_stats_command(), bot.make_lang_command(), bot.make_mention_command()]
    assert sorted(c.name for c in cmds) == ["add", "lang", "list", "mention", "remove", "stats"]
    assert all(isinstance(c, app_commands.Command) and re.fullmatch(r"[a-z]+", c.name) for c in cmds)   # 1語・グループではない
    tree = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
    for c in cmds: tree.add_command(c, guild=discord.Object(1))
    d = {x.name: x.to_dict(tree) for x in tree.get_commands(guild=discord.Object(1))}
    assert all(x["type"] == 1 and len(x["description"]) <= 100 for x in d.values())
    assert not any(o["type"] in (1, 2) for x in d.values() for o in x.get("options", []))            # サブコマンド/サブコマンドグループなし
    assert [o["name"] for o in d["add"]["options"]] == ["target"] and d["add"]["options"][0]["required"] is True and d["add"]["options"][0]["autocomplete"] is True
    assert [(o["name"], o["type"]) for o in d["list"]["options"]] == [("show_uid", 5), ("include_removed", 5)]
    assert d["remove"]["options"][0]["name"] == "target" and d["remove"]["options"][0]["autocomplete"] is True
    # setup_hook が全部登録している / グループ方式に戻っていない
    hook = inspect.getsource(B.Bot.setup_hook)
    assert all(x in hook for x in ("FriendCommands(self).commands()", "make_stats_command", "make_lang_command", "make_mention_command"))
    assert "app_commands.Group" not in open(B.__file__).read() and "friend" not in str(sorted(d))
    # removeのオートコンプリートがコマンド経由で動く(所有者のみ・UIDが値)
    remove_cmd = next(c for c in cmds if c.name == "remove")
    ac = remove_cmd._params["target"].autocomplete
    r = await ac(FI(99, 2), "ali"); assert [(x.name.split(" ")[0], x.value) for x in r] == [("Alice", "usr_a")]
    assert await ac(FI(1, 2), "ali") == []
    # 権限: メインチャンネル以外・他人はどのコマンドも拒否(以前のグループ全体のチェックと同じ)
    for call in (lambda i: fc.do_add(i, "usr_x"), lambda i: fc.do_remove(i, "usr_a"), lambda i: fc.do_list(i)):
        for who, ch in ((99, 999), (1, 2)):
            i = FI(who, ch); await call(i); assert i.out[1].get("ephemeral") and "メインチャンネルで所有者のみ" in i.out[0], (who, ch)
    i = FI(99, 2); await fc.do_list(i); assert "Alice" in i.out[1]["embed"].description         # 正規の場所なら動く
    i = FI(99, 2); await fc.do_add(i, "not-a-url"); assert "該当するフレンドが見つかりません" in i.out[0]
asyncio.run(run8())
print("COMMAND TESTS PASSED")

# ================= 全フレンドの収集 (vrc_friends) =================
UU = lambda n: f"usr_{n:08x}-1111-1111-1111-111111111111"
def fr(uid_, name, ingame=False, status="active", loc=None, desc=""):
    return {"uid": uid_, "name": name, "status": status, "desc": desc, "location": loc or ("wrld_x:1~region(jp)" if ingame else "offline"), "ingame": ingame}
class FakeVRC3:
    def __init__(s): s.list, s.fail, s.users, s.calls = [], False, {}, {"world": 0, "instance": 0, "user": 0}
    def get_friends_all(s):
        if s.fail: raise RuntimeError("boom")
        return list(s.list)
    def get_world(s, w): s.calls["world"] += 1; return {"name": "W", "author": "a", "capacity": 32, "thumb": None, "desc": ""}
    def get_instance(s, w, i): s.calls["instance"] += 1; return {"n_users": 3, "capacity": 16}
    def get_user(s, u):
        s.calls["user"] += 1
        if isinstance(s.users[u], Exception): raise s.users[u]
        return s.users[u]
    def get_group_name(s, g): return "G"
def newbot():
    bot = B.Bot(); bot.db = DB(":memory:"); bot.stats = Stats(bot.db.c, JST); bot.vrc = FakeVRC3()
    bot.stats.c.execute("UPDATE stats_meta SET v=? WHERE k='since'", (str(T(1)),)); bot.stats.c.commit()
    return bot

# --- 名簿と収集開始日時 ---
s = mkstats()
assert s.upsert_friend("n1", "New") is True and abs(s.friend("n1")["tracked_since"] - time.time()) < 5   # 新規は今から
assert s.upsert_friend("n1", "New2") is False and s.friend("n1")["name"] == "New2"
assert s.upsert_friend("n1", None) is False and s.friend("n1")["name"] == "New2"                         # Noneでは名前を消さない
s.record("h1", "login", "active", T(3, 10)); s.upsert_friend("h1", "Hist"); assert s.friend("h1")["tracked_since"] == T(3, 10)   # 既存の履歴まで遡る
s.upsert_friend("h2", "A", hint=T(1) - 86400); assert s.friend("h2")["tracked_since"] == T(1)           # 登録日時が統計開始より前なら統計開始
s.upsert_friend("h3", "B", hint=T(4)); assert s.friend("h3")["tracked_since"] == T(4)                    # 後なら登録日時
s.record("h4", "login", "busy", T(3)); s.upsert_friend("h4", "C", hint=T(5)); assert s.friend("h4")["tracked_since"] == T(3)  # 履歴と登録日時は早いほう
assert s.tracked_since(["h3", "h2"]) == T(1) and s.tracked_since(["h3"]) == T(4) and s.tracked_since(["zz"]) == T(1) and s.tracked_since([]) == T(1)
s.mark_unfriended("h3"); assert s.friend("h3")["is_friend"] == 0 and "h3" in [r["uid"] for r in s.friends()]   # 解除しても名簿(履歴)は残る
assert sorted(s.missing(["n1"])) == ["h1", "h2", "h4"]
assert s.upsert_friend("h3", "B") is False and s.friend("h3")["is_friend"] == 1                           # 再びフレンドに

# --- 一覧の取得(ページ送り・重複除去・ゲーム内判定) ---
class FakeFriendsApi:
    def __init__(s): s.calls = []
    def get_friends(s, offset=0, n=100, offline=False):
        s.calls.append((offset, n, offline))
        mk = lambda i, loc: types.SimpleNamespace(id=f"usr_{i}", display_name=f"N{i}", status="join me", status_description="d", location=loc)
        allf = [mk(i, "wrld_a:1" if i % 2 else "private") for i in range(120)] if not offline else [mk(1000 + i, "offline") for i in range(100)] + [mk(5, "offline")]
        return allf[offset:offset + n]
_v = B.VRC("u", "p", "ua"); _v.friends = FakeFriendsApi()
_sm = sys.modules[explain_error.__module__]; _old_sleep = _sm.time.sleep; _sm.time.sleep = lambda x: None
try: _out = _v.get_friends_all()
finally: _sm.time.sleep = _old_sleep
assert _v.friends.calls == [(0, 100, False), (100, 100, False), (0, 100, True), (100, 100, True)], _v.friends.calls
assert len(_out) == 220 and len({f["uid"] for f in _out}) == 220 and sum(f["ingame"] for f in _out) == 120   # 重複(usr_5)は除く
assert next(f for f in _out if f["uid"] == "usr_5")["ingame"] is True and _out[0]["status"] == "join me" and _out[0]["desc"] == "d"

# --- 同期とイベント: 全員を記録し、通知は登録者だけ ---
async def run9():
    bot = newbot(); sent = []
    async def fake_send(uid_, **kw): sent.append((uid_, kw["embed"].title, kw.get("content")))
    bot.send_to = fake_send
    bot.db.upsert("usr_a", "OldA", 111)                                           # 登録済み(名前が古い)
    bot.vrc.list = [fr("usr_a", "Alice", True, "join me", "wrld_x:1~region(jp)"), fr("usr_b", "Bob", True, "busy", "private"),
                    fr("usr_c", "Carol"), fr("usr_t", "Trav", True, loc="traveling")]
    await bot.sync_friends()
    assert {r["uid"] for r in bot.stats.friends()} == {"usr_a", "usr_b", "usr_c", "usr_t"}
    assert bot.db.get("usr_a")["name"] == "Alice"                                 # 登録済みの表示名も同期
    assert bot.ingame == {"usr_a", "usr_b", "usr_t"} and bot.last_status["usr_b"] == ("busy", "")
    assert bot.last_loc["usr_a"] == "wrld_x:1~region(jp)" and "usr_t" not in bot.last_loc
    assert kinds(bot.stats, "usr_a") == [("resume", "join me")] and kinds(bot.stats, "usr_c") == []
    assert sent == [] and bot.vrc.calls == {"world": 0, "instance": 0, "user": 0}   # 同期は通知もワールドAPIもなし
    assert bot.first_sync is False and bot.ws_down_at is None
    ev = lambda t, u, **c: bot.handle({"type": t, "content": {"userId": u, **c}})
    # 未登録のBob: 統計は記録するが、通知もワールドAPIもなし
    await ev("friend-offline", "usr_b"); await ev("friend-online", "usr_b", platform="android", location="wrld_x:2", user={"status": "join me"})
    await ev("friend-update", "usr_b", user={"status": "ask me", "statusDescription": ""}); await ev("friend-location", "usr_b", location="wrld_y:3")
    assert kinds(bot.stats, "usr_b") == [("resume", "busy"), ("logout", None), ("login", "join me"), ("status", "ask me")], kinds(bot.stats, "usr_b")
    assert sent == [] and bot.vrc.calls == {"world": 0, "instance": 0, "user": 0}
    # 登録済みのAliceは従来どおり通知(オンラインはメンション付き)
    await ev("friend-offline", "usr_a"); assert sent[-1][1] == "⚫ Alice がオフライン"
    await ev("friend-online", "usr_a", platform="android", location="private", user={"status": "active"})
    assert sent[-1][1] == "🟢 Alice がオンライン" and sent[-1][2] == f"<@{B.OWNER}>"
    # 削除(通知停止)後も記録は続き、通知は出ない
    bot.db.deactivate("usr_a"); n = len(sent)
    await ev("friend-offline", "usr_a"); await ev("friend-online", "usr_a", platform="android", location="private", user={"status": "busy"})
    assert len(sent) == n and kinds(bot.stats, "usr_a")[-2:] == [("logout", None), ("login", "busy")]
    # フレンド追加/解除/改名
    await ev("friend-add", "usr_e", user={"displayName": "Eve"}); assert bot.stats.friend("usr_e")["name"] == "Eve" and bot.stats.friend("usr_e")["is_friend"] == 1
    await ev("friend-online", "usr_e", platform="windows", location="private", user={"displayName": "Eve", "status": "active"}); assert "usr_e" in bot.ingame
    await ev("friend-delete", "usr_e"); assert bot.stats.friend("usr_e")["is_friend"] == 0 and "usr_e" not in bot.ingame and kinds(bot.stats, "usr_e")[-1][0] == "logout"
    await ev("friend-update", "usr_b", user={"displayName": "Bobby", "status": "ask me", "statusDescription": ""}); assert bot.stats.friend("usr_b")["name"] == "Bobby"
    await ev("friend-update", "usr_a", user={"displayName": "Alicia", "status": "busy"}); assert bot.db.get("usr_a")["name"] == "Alicia"   # 登録側の表示名にも反映
    await ev("friend-add", "usr_f", user={}); assert bot.stats.friend("usr_f")["name"] is None                                          # 名前不明でも名簿に載る
asyncio.run(run9())

# --- 再同期: 見えていなかった間の離脱・解除・安全弁・排他 ---
async def run10():
    bot = newbot()
    for n in range(10): bot.stats.upsert_friend(UU(n), f"F{n}")
    bot.stats.record(UU(1), "login", "active", T(1, 20)); bot.ingame.add(UU(1))
    bot.stats.record(UU(2), "login", "busy", T(1, 20)); bot.ingame.add(UU(2))
    base = [fr(UU(n), f"F{n}") for n in range(10)]
    # 同期が失敗しても first_sync / ws_down_at を持ち越し、成功した最初の同期は前回の生存時刻で閉じる
    bot.first_sync, bot.stats.prev_alive, bot.ws_down_at = True, T(1, 21), T(1, 23)
    bot.vrc.fail = True; await bot.sync_friends(); assert bot.first_sync is True and bot.ws_down_at == T(1, 23)
    bot.vrc.fail = False; bot.vrc.list = base; await bot.sync_friends()
    assert bot.stats.state(UU(1))[2] == T(1, 21) and bot.stats.state(UU(1))[0] is False and bot.first_sync is False and bot.ws_down_at is None
    # 2回目以降は WebSocket が切れた時刻で閉じる
    assert bot.stats.state(UU(2))[2] == T(1, 21)                                                  # (1回目で閉じ済み)
    bot.stats.record(UU(4), "login", "active", T(1, 20)); bot.ingame.add(UU(4)); bot.ws_down_at = T(1, 22); await bot.sync_friends()
    assert bot.stats.state(UU(4))[0] is False and bot.stats.state(UU(4))[2] == T(1, 22) and bot.ws_down_at is None
    # 一覧から消えた人(少数)はフレンド解除として扱い、ゲーム内なら閉じる
    bot.stats.record(UU(3), "login", "active", T(1, 20)); bot.ingame.add(UU(3))
    bot.vrc.list = [f for f in base if f["uid"] != UU(3)]; await bot.sync_friends()
    assert bot.stats.friend(UU(3))["is_friend"] == 0 and UU(3) not in bot.ingame and bot.stats.state(UU(3))[0] is False
    # 取得不全で大量に消えたように見えたら解除扱いにしない(安全弁)
    for n in range(10, 30): bot.stats.upsert_friend(UU(n), f"F{n}")
    bot.vrc.list = base[:10]; await bot.sync_friends()
    assert all(bot.stats.friend(UU(n))["is_friend"] == 1 for n in range(10, 30))
    # 同期中の二重実行は無視
    await bot.sync_lock.acquire(); calls = []; bot.vrc.get_friends_all = lambda: calls.append(1) or []
    await bot.sync_friends(); bot.sync_lock.release(); assert calls == []
asyncio.run(run10())

# --- /add: 名簿から選ぶ / URL ---
async def run11():
    bot = newbot(); created = []
    async def ch_send(**kw): pass
    async def fake_channel(u, name): created.append((u, name)); return types.SimpleNamespace(id=900 + len(created), mention=f"<#{900 + len(created)}>", send=ch_send)
    bot.friend_channel = fake_channel; fc = B.FriendCommands(bot)
    for n, name in ((1, "Alice"), (2, "Bob"), (3, "Zed"), (4, "Gone"), (5, "Reg")): bot.stats.upsert_friend(UU(n), name)
    bot.stats.mark_unfriended(UU(4)); bot.db.upsert(UU(5), "Reg", 555)
    assert {r["uid"] for r in fc.add_candidates()} == {UU(1), UU(2), UU(3)}                      # 解除済み・登録済みは候補に出ない
    r = await fc.add_ac(FI(99, 2), "ali"); assert [(x.name.split(" ")[0], x.value) for x in r] == [("Alice", UU(1))]
    assert len(await fc.add_ac(FI(99, 2), "")) == 3 and await fc.add_ac(FI(1, 2), "") == []
    i = FI(99, 2); await fc.do_add(i, UU(1))                                                     # 名簿の人はAPI不要
    assert bot.vrc.calls["user"] == 0 and created == [(UU(1), "Alice")] and bot.db.get(UU(1))["active"] == 1
    assert "追加しました" in i.out[0] and "Alice" in i.out[0] and "⚠️" not in i.out[0]
    assert UU(1) not in [r["uid"] for r in fc.add_candidates()]
    i = FI(99, 2); await fc.do_add(i, UU(1)); assert "すでに登録済み" in i.out[0]
    i = FI(99, 2); await fc.do_add(i, " bob "); assert bot.db.get(UU(2)) and bot.vrc.calls["user"] == 0   # 名前の完全一致(一意)
    bot.stats.upsert_friend(UU(8), "Dup"); bot.stats.upsert_friend(UU(9), "dup")
    i = FI(99, 2); await fc.do_add(i, "DUP"); assert "同名" in i.out[0] and bot.db.get(UU(8)) is None
    i = FI(99, 2); await fc.do_add(i, "nobody"); assert "該当するフレンドが見つかりません" in i.out[0]
    i = FI(99, 2); await fc.do_add(i, f"https://vrchat.com/home/user/{UU(3)}"); assert bot.db.get(UU(3)) and bot.vrc.calls["user"] == 0   # URLでも名簿の人はAPI不要
    # 名簿にいない人(URL): APIで確認 -> フレンドなら名簿に載せる / フレンドでなければ警告 / 存在しなければエラー
    bot.vrc.users[UU(20)] = {"name": "Zoe", "status": "active", "desc": "", "is_friend": True, "state": "offline"}
    bot.vrc.users[UU(21)] = {"name": "Stranger", "status": "active", "desc": "", "is_friend": False, "state": "offline"}
    bot.vrc.users[UU(22)] = E(404)
    i = FI(99, 2); await fc.do_add(i, f"https://vrchat.com/home/user/{UU(20)}")
    assert bot.vrc.calls["user"] == 1 and bot.db.get(UU(20))["name"] == "Zoe" and bot.stats.friend(UU(20))["is_friend"] == 1 and "⚠️" not in i.out[0]
    i = FI(99, 2); await fc.do_add(i, UU(21)); assert "⚠️" in i.out[0] and bot.stats.friend(UU(21)) is None and bot.db.get(UU(21))["active"] == 1
    i = FI(99, 2); await fc.do_add(i, UU(22)); assert "存在しません" in i.out[0] and bot.db.get(UU(22)) is None
    # 削除した人は再登録できる(候補に戻り、チャンネルは再利用)
    bot.db.deactivate(UU(1)); assert UU(1) in [r["uid"] for r in fc.add_candidates()]
    i = FI(99, 2); await fc.do_add(i, UU(1)); assert "(再登録)" in i.out[1]["embed"].title
asyncio.run(run11())

# --- /stats who: 登録の有無に関係なく収集済みのデータで分析 ---
async def run12():
    bot = newbot(); R_, A_, B_, U_, L_ = UU(1), UU(2), UU(3), UU(4), UU(5)   # 削除済み/登録中/未登録/解除済み/名簿に無い登録済み
    bot.db.upsert(A_, "Alice", 111); bot.db.upsert(R_, "Removed", 222); bot.db.deactivate(R_); bot.db.upsert(L_, "Legacy", 555)
    for u, n in ((A_, "Alice"), (R_, "Removed"), (B_, "Bob"), (U_, "Unfr")): bot.stats.upsert_friend(u, n)
    bot.stats.mark_unfriended(U_)
    bot.stats.c.execute("UPDATE vrc_friends SET tracked_since=?", (T(4),)); bot.stats.c.commit()   # 収集開始は全員4日目(履歴はその後)
    for u, k in ((A_, 2), (R_, 3), (B_, 5), (U_, 7)):
        for d in range(k): bot.stats.record(u, "login", "active", T(5 + d // 4, 8 + 3 * (d % 4))); bot.stats.record(u, "logout", None, T(5 + d // 4, 9 + 3 * (d % 4)))   # 5〜6日目(過去)に収める
    cmd = bot.make_stats_command(); cb = cmd.callback
    fmt = lambda ts: datetime.fromtimestamp(ts, JST).strftime("%Y-%m-%d %H:%M")
    i = FI(99, 2); await cb(i, None, None); e = i.out[1]["embed"]
    assert "**ゲーム内ログイン**: 2回" in e.description and "全員" in e.title                       # 省略時は登録中の全員(未登録・削除済みは含めない)
    for who, n, tags in ((B_, 5, [" (未登録)"]), (R_, 3, [" (削除済み)"]), (U_, 7, [" (未登録)", " (フレンド解除済み)"]), (A_, 2, [])):
        i = FI(99, 2); await cb(i, None, who); e = i.out[1]["embed"]
        assert f"**ゲーム内ログイン**: {n}回" in e.description and all(t in e.title for t in tags), (who, e.title, e.description)
        assert not any(x.name.startswith("👥") for x in e.fields)
    i = FI(99, 2); await cb(i, None, B_); assert fmt(T(4)) in i.out[1]["embed"].description         # 期間の開始はそのフレンドの収集開始日時
    i = FI(99, 2); await cb(i, 1, B_); d = i.out[1]["embed"].description; assert "約1.0日間" in d and "**ゲーム内ログイン**: 0回" in d   # days併用
    i = FI(99, 2); await cb(i, None, "bob"); assert "Bob" in i.out[1]["embed"].title               # 名前でも指定できる
    i = FI(99, 111); await cb(i, None, B_); assert "Bob" in i.out[1]["embed"].title                # フレンド用チャンネルでもwho優先
    i = FI(99, 111); await cb(i, None, None); assert "Alice" in i.out[1]["embed"].title            # whoなしは従来どおりそのチャンネルのフレンド
    i = FI(99, 222); await cb(i, None, None); assert "(削除済み)" in i.out[1]["embed"].title
    i = FI(99, 2); await cb(i, None, L_); assert "Legacy" in i.out[1]["embed"].title                # 名簿に無い登録済みの人も指定できる
    i = FI(99, 2); await cb(i, None, "nobody"); assert i.out[1].get("ephemeral") and "該当するフレンドが見つかりません" in i.out[0]
    i = FI(99, 2); await cb(i, None, UU(99)); assert i.out[1].get("ephemeral")
    bot.stats.upsert_friend(UU(8), "Same"); bot.stats.upsert_friend(UU(9), "same")
    i = FI(99, 2); await cb(i, None, "SAME"); assert "同名" in i.out[0]
    i = FI(1, 2); await cb(i, None, B_); assert i.out[1].get("ephemeral") and "所有者" in i.out[0]   # 他人は不可
    ac = cmd._params["who"].autocomplete                                                            # 候補: 登録中/削除済み/未登録/解除済み/名簿外の登録済み
    r = await ac(FI(99, 2), ""); assert {x.value for x in r} >= {A_, R_, B_, U_, L_} and await ac(FI(1, 2), "") == []
    r = await ac(FI(99, 2), "unf"); assert [(x.name.split(" ")[0], x.value) for x in r] == [("Unfr", U_)]
    # スラッシュコマンド定義
    tree = app_commands.CommandTree(discord.Client(intents=discord.Intents.default())); tree.add_command(cmd, guild=discord.Object(1))
    o = {x["name"]: x for x in cmd.to_dict(tree)["options"]}
    assert o["days"]["type"] == 4 and not o["days"].get("required") and o["days"]["min_value"] == 1
    assert o["who"]["type"] == 3 and not o["who"].get("required") and o["who"]["autocomplete"] is True and list(o) == ["days", "who"]
asyncio.run(run12())
assert i18n.get_lang() == "ja"
print("COLLECT TESTS PASSED")

# --- WebSocketの配線: 接続のたびに同期 / 切断時刻の記録 / 再接続 (偽の接続で確認) ---
async def run13():
    bot = newbot(); syncs, handled, conns = [], [], []
    async def fake_sync(): syncs.append(1)
    async def fake_handle(m): handled.append(m["type"])
    bot.sync_friends, bot.handle = fake_sync, fake_handle
    bot.vrc.get_token = lambda: "tok"
    class WS:
        def __init__(s, n): s.n, s.k = n, 0
        async def __aenter__(s): return s
        async def __aexit__(s, *a): return False
        def __aiter__(s): return s
        async def __anext__(s):
            s.k += 1
            if s.k == 1: return json.dumps({"type": "friend-offline", "content": {"userId": "usr_a"}})
            if s.n == 1: raise ConnectionError("drop")      # 1回目の接続は途中で切れる
            await real_sleep(3600)                           # 2回目は維持
    def fake_connect(url, additional_headers=None): conns.append(url); return WS(len(conns))
    real_connect, real_sleep = B.websockets.connect, asyncio.sleep
    async def fast_sleep(x): await real_sleep(0 if x < 100 else x)   # 再接続の待ちだけ短縮
    B.websockets.connect, asyncio.sleep = fake_connect, fast_sleep
    try:
        assert bot.ws_down_at is None
        task = asyncio.create_task(bot.ws_loop())
        for _ in range(100):
            await real_sleep(0.01)
            if len(conns) >= 2 and len(syncs) >= 2: break
        task.cancel()
    finally:
        B.websockets.connect, asyncio.sleep = real_connect, real_sleep
    assert conns == ["wss://pipeline.vrchat.cloud/?authToken=tok"] * 2                  # 切断後に再接続した
    assert len(syncs) == 2 and handled == ["friend-offline", "friend-offline"]          # 接続のたびに同期 / イベントは処理
    assert bot.ws_down_at is not None and time.time() - bot.ws_down_at < 30             # 切断時刻を記録(次の同期で使う)
asyncio.run(run13())
print("WS TESTS PASSED")

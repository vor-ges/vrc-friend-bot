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
g = B.FriendGroup(types.SimpleNamespace(db=db))
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
    def __init__(s, uid, ch): s.user = types.SimpleNamespace(id=uid); s.channel_id = ch; s.out = None; s.response = types.SimpleNamespace(send_message=s._send, edit_message=s._edit)
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
    # 削除: ゲーム内区間を閉じる / 起動時の照合
    bot.stats.record("usr_a", "login", "active"); bot.ingame.add("usr_a")
    view = B.ConfirmRemove(bot, bot.db.get("usr_a")); await view.yes.callback(FI(99, 2))
    assert bot.stats.state("usr_a")[0] is False and "usr_a" not in bot.ingame
    bot.db.upsert("usr_a", "Alice", 111); bot.stats.c.execute("DELETE FROM activity WHERE uid='usr_a'"); bot.stats.c.commit()
    bot.stats.record("usr_a", "login", "busy", T(1, 20)); bot.stats.prev_alive = T(1, 21)
    bot.vrc.get_user = lambda u: {"name": "x", "status": "active", "desc": "", "is_friend": True, "state": "active"}
    for n in range(40): bot.db.deactivate(f"usr_{n:02d}")
    bot.db.deactivate("usr_b"); await bot.prime_cache()                                                 # 停止中にゲームを抜けていた
    assert bot.stats.state("usr_a")[0] is False and bot.stats.state("usr_a")[2] == T(1, 21)
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
assert i18n.tr("{name} (グループ)", wrong=1) == "{name} (グループ)"   # 引数名が違っても例外にせず原文で返す(通知を止めない)
try: i18n.set_lang("xx"); raise SystemExit("unsupported lang accepted")
except ValueError: pass
assert i18n.get_lang() == "en"
i18n.set_lang("ja")
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
    i = FI(99, 2); await lang(i, None); assert "日本語" in i.out[0] and "ja" in i.out[0]                 # 引数なしは現在の言語
    i = FI(99, 2); await lang(i, "en"); assert i.out[0] == "Language switched to English." and i18n.get_lang() == "en"
    assert bot.db.c.execute("SELECT v FROM bot_settings WHERE k='lang'").fetchone()[0] == "en"          # DBに保存
    i = FI(99, 2); await lang(i, None); assert "English" in i.out[0] and i.out[0].startswith("Current language")
    i = FI(99, 2); await lang(i, "fr"); assert i.out[1].get("ephemeral") and i.out[0] == "Unsupported language."
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
    i = FI(99, 2); await lang(i, "ja"); assert i18n.get_lang() == "ja" and "切り替えました" in i.out[0]
    v = B.ConfirmRemove(bot, bot.db.get("usr_a")); assert (v.yes.label, v.no.label) == ("削除する", "キャンセル")
    await ev("friend-online", platform="android", location="private"); assert sent[-1].title == "🟢 Alice がオンライン"
asyncio.run(run5())
assert i18n.get_lang() == "ja"

# --- /lang の定義 (引数は省略可・選択肢はja/en) ---
_t2 = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
_c2 = B.Bot().make_lang_command(); _t2.add_command(_c2, guild=discord.Object(1))
_d2 = _c2.to_dict(_t2); _o2 = _d2["options"][0]
assert _d2["name"] == "lang" and _o2["name"] == "language" and not _o2.get("required") and [c["value"] for c in _o2["choices"]] == ["ja", "en"]
print("LANG TESTS PASSED")

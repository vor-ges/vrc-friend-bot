"""オフライン単体テスト: python test_local.py (Discord/VRChatへ接続しません)"""
import os, sys, asyncio, tempfile, types
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

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

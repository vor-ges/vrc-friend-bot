import os, re, asyncio, vrchatapi
from urllib.parse import urlparse
from vrchatapi.api import authentication_api, users_api, worlds_api, instances_api
from vrchatapi.exceptions import UnauthorizedException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode

TOKEN_FILE = ".vrc_auth"

UID_RE = re.compile(r"usr_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
PROFILE_PATH_RE = re.compile(r"/home/user/(usr_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?", re.I)
PROFILE_HOSTS = {"vrchat.com", "www.vrchat.com"}


def extract_uid(text):
    """プロフィールURL (https://vrchat.com/home/user/usr_...) または usr_... からUIDを取り出す。
    不正なら None。ホストは完全一致(userinfo/ポート付きは拒否)、クエリ/フラグメントは無視。"""
    s = (text or "").strip().strip("<>").strip()
    if not s or len(s) > 300:
        return None
    if UID_RE.fullmatch(s):
        return s.lower()
    try:
        p = urlparse(s)
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or p.netloc.lower() not in PROFILE_HOSTS:
        return None
    m = PROFILE_PATH_RE.fullmatch(p.path)
    return m.group(1).lower() if m else None


def explain_error(e):
    """例外 -> ユーザー向けメッセージ(内部情報や秘密は含めない)"""
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return "VRChat APIの応答がタイムアウトしました。少し待って再試行してください。"
    if isinstance(e, EOFError):
        return "VRChatの再認証(2FA)が必要です。サーバーで `python bot.py` を手動起動して認証してください。"
    st = getattr(e, "status", None)
    if st == 404:
        return "そのユーザーはVRChat上に存在しません。URLを確認してください。"
    if st in (401, 403):
        return "VRChat認証エラーです。サーバー側で再認証が必要な可能性があります。"
    if st == 429:
        return "VRChat APIのレート制限中です。しばらく待って再試行してください。"
    if isinstance(st, int) and st >= 500:
        return f"VRChat側のサーバーエラーです (HTTP {st})。"
    return "VRChat APIでエラーが発生しました。ログを確認してください。"

class VRC:
    """vrchatapi の同期呼び出しをまとめたラッパー（Bot側からは to_thread で呼ぶ）"""
    def __init__(self, username, password, user_agent):
        self.ua = user_agent
        self.username, self.password = username, password
        self.api = vrchatapi.ApiClient(vrchatapi.Configuration(username=username, password=password))
        self.api.user_agent = user_agent
        self.auth = authentication_api.AuthenticationApi(self.api)
        self.users = users_api.UsersApi(self.api)
        self.worlds = worlds_api.WorldsApi(self.api)
        self.instances = instances_api.InstancesApi(self.api)
        self.token = None

    def login(self):
        # 保存済みトークンがあれば再利用
        if os.path.exists(TOKEN_FILE):
            saved = open(TOKEN_FILE).read().strip()
            self.api.set_default_header("Cookie", f"auth={saved}")
            try:
                self.auth.get_current_user()
                self.token = saved
                return
            except Exception:
                self.api.default_headers.pop("Cookie", None)
        try:
            self.auth.get_current_user()
        except UnauthorizedException as e:
            if e.status == 200:
                if "Email 2 Factor Authentication" in e.reason:
                    self.auth.verify2_fa_email_code(TwoFactorEmailCode(input("メール2FAコード: ").strip()))
                elif "2 Factor Authentication" in e.reason:
                    self.auth.verify2_fa(TwoFactorAuthCode(input("認証アプリの2FAコード: ").strip()))
                self.auth.get_current_user()
            else:
                raise
        self.refresh_token()

    def refresh_token(self):
        self.token = self.auth.verify_auth_token().token
        open(TOKEN_FILE, "w").write(self.token)
        return self.token

    def get_token(self):
        try:
            self.auth.verify_auth_token()
            return self.token or self.refresh_token()
        except Exception:
            self.login()
            return self.token

    def get_user(self, uid):
        u = self.users.get_user(uid)
        return {"name": u.display_name, "status": str(u.status),
                "desc": u.status_description or "", "is_friend": bool(u.is_friend)}

    def get_world(self, wid):
        w = self.worlds.get_world(wid)
        return {"name": w.name, "author": w.author_name, "capacity": w.capacity,
                "thumb": w.thumbnail_image_url, "desc": (w.description or "")[:200]}

    def get_instance(self, wid, iid):
        i = self.instances.get_instance(wid, iid)
        return {"n_users": getattr(i, "n_users", None), "capacity": getattr(i, "capacity", None)}

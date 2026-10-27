"""ログイン統計: ゲーム内ログイン/ログアウト/ステータス変更を履歴として保存し、集計する。

既存の friends テーブルには触れず、専用テーブル(activity / stats_meta)を IF NOT EXISTS で追加するだけ。
kind: login=ゲーム内ログイン(頻度に数える) / resume=ログイン時刻不明の復元(滞在時間のみ数える)
      status=ステータス変更 / logout=ゲームから離脱
"""
import time, logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

log = logging.getLogger("vrcbot")


def make_tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        log.warning("timezone %r を読み込めないため UTC+9 を使います", name)
        return timezone(timedelta(hours=9))


def _blank():
    return {"logins": 0, "hours": [0] * 24, "status": defaultdict(float), "seconds": 0.0}


class Stats:
    def __init__(self, conn, tz):
        self.c, self.tz = conn, tz
        self.c.executescript("""
            CREATE TABLE IF NOT EXISTS activity(
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL,
                ts REAL NOT NULL, kind TEXT NOT NULL, status TEXT);
            CREATE INDEX IF NOT EXISTS idx_activity_uid_ts ON activity(uid, ts);
            CREATE TABLE IF NOT EXISTS stats_meta(k TEXT PRIMARY KEY, v TEXT);""")
        self.c.execute("INSERT OR IGNORE INTO stats_meta(k,v) VALUES('since', ?)", (str(time.time()),))
        self.c.commit()
        self.prev_alive = self._meta("alive")  # 前回プロセスが最後に生きていた時刻 (起動時の照合用)

    # ---------- meta ----------
    def _meta(self, k):
        r = self.c.execute("SELECT v FROM stats_meta WHERE k=?", (k,)).fetchone()
        return float(r["v"]) if r else None

    def since(self):
        return self._meta("since")

    def heartbeat(self):
        try:
            self.c.execute("INSERT INTO stats_meta(k,v) VALUES('alive',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                           (str(time.time()),))
            self.c.commit()
        except Exception:
            log.exception("stats heartbeat failed")

    # ---------- 記録 ----------
    def record(self, uid, kind, status=None, ts=None):
        try:
            self.c.execute("INSERT INTO activity(uid,ts,kind,status) VALUES(?,?,?,?)",
                           (uid, ts if ts is not None else time.time(), kind, status))
            self.c.commit()
        except Exception:
            log.exception("stats record failed uid=%s kind=%s", uid, kind)  # 通知処理は止めない

    def state(self, uid):
        """(履歴上ゲーム内か, 直近のステータス, 最終イベント時刻)"""
        r = self.c.execute("SELECT kind,status,ts FROM activity WHERE uid=? ORDER BY ts DESC, id DESC LIMIT 1",
                           (uid,)).fetchone()
        if not r:
            return False, None, None
        return r["kind"] != "logout", r["status"], r["ts"]

    def reconcile(self, uid, online_now, status, close_at=None):
        """履歴と現在の実状態(online_now)を突き合わせて、停止中などで生じたズレを補正する。"""
        logged, last_status, last_ts = self.state(uid)
        if online_now and not logged:
            self.record(uid, "resume", status)
        elif not online_now and logged:
            ts = time.time() if close_at is None else min(time.time(), max(last_ts, close_at))
            self.record(uid, "logout", ts=ts)
        elif online_now and logged and status and status != last_status:
            self.record(uid, "status", status)

    # ---------- 集計 ----------
    def summarize(self, uids, start, end):
        """uids の [start, end] を集計。返り値: {"per": {uid: stat}, "total": stat}
        stat = {logins, hours[24](ログイン時間帯別回数), status{名前: 秒}, seconds(ゲーム内滞在秒)}"""
        per = {u: _blank() for u in uids}
        if uids:
            q = ",".join("?" * len(uids))
            rows = self.c.execute(
                f"SELECT uid,ts,kind,status FROM activity WHERE uid IN ({q}) AND ts<=? ORDER BY uid, ts, id",
                (*uids, end)).fetchall()
            state = {}  # uid -> [ゲーム内か, 現ステータス, 区間開始]

            def close(uid, t1):
                ing, cur, t0 = state[uid]
                a, b = max(t0, start), min(t1, end)
                if ing and b > a:
                    per[uid]["status"][cur] += b - a
                    per[uid]["seconds"] += b - a

            for r in rows:
                uid, ts, kind, st = r["uid"], r["ts"], r["kind"], r["status"] or "unknown"
                s = state.setdefault(uid, [False, None, ts])
                if kind in ("login", "resume"):
                    if s[0]: close(uid, ts)  # 二重ログイン: 前の区間をここで閉じる
                    state[uid] = [True, st, ts]
                    if kind == "login" and start <= ts <= end:
                        per[uid]["logins"] += 1
                        per[uid]["hours"][datetime.fromtimestamp(ts, self.tz).hour] += 1
                elif kind == "status":
                    if s[0]:
                        close(uid, ts); state[uid] = [True, st, ts]
                elif kind == "logout":
                    if s[0]:
                        close(uid, ts); state[uid] = [False, None, ts]
            for uid, s in state.items():
                if s[0]: close(uid, end)  # まだゲーム内なら現在まで
        total = _blank()
        for p in per.values():
            total["logins"] += p["logins"]; total["seconds"] += p["seconds"]
            for h in range(24): total["hours"][h] += p["hours"][h]
            for k, v in p["status"].items(): total["status"][k] += v
        return {"per": per, "total": total}

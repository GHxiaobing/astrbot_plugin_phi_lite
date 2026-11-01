# phi_lite —— AstrBot 用的 Phigros 查分插件（轻量版）
# 数据：r0semi.xtower.site 开放接口；曲绘：somnia.xtower.site。
# 出图交给同目录的 render_cli.py 独立进程画：主进程里 PIL 画日文假名会缺字，独立进程正常。

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

API_BASE = "https://r0semi.xtower.site/api/v1/open"


class PhiLite:
    def __init__(self, plugin_dir: Path, api_token: str):
        self.dir = plugin_dir
        self.api_token = api_token
        self.users_file = plugin_dir / "data" / "users.json"
        self.cache_dir = plugin_dir / "data" / "illus"
        self.out_dir = plugin_dir / "data" / "out"
        for d in (self.users_file.parent, self.cache_dir, self.out_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---------- 存储 ----------
    def _load(self):
        try:
            return json.loads(self.users_file.read_text("utf-8"))
        except Exception:
            return {}

    def _save(self, d):
        self.users_file.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")

    def bind(self, uid, session_token):
        d = self._load()
        d[str(uid)] = {"session": session_token.strip(), "at": int(time.time())}
        self._save(d)

    def unbind(self, uid):
        d = self._load()
        d.pop(str(uid), None)
        self._save(d)

    def session_of(self, uid):
        return (self._load().get(str(uid)) or {}).get("session")

    # ---------- 接口 ----------
    def _post(self, path, body, timeout=25):
        req = urllib.request.Request(
            API_BASE + path,
            data=json.dumps(body).encode(),
            headers={"X-OpenApi-Token": self.api_token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def fetch_save(self, session):
        return self._post("/save?calculate_rks=true", {"sessionToken": session})

    # ---------- 渲染（独立进程） ----------
    def render_b30(self, data) -> Path:
        script = self.dir / "render_cli.py"
        payload = json.dumps(
            {"data": data, "out_dir": str(self.out_dir), "cache_dir": str(self.cache_dir)},
            ensure_ascii=False,
        )
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=payload.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            cwd=str(self.dir),
        )
        out = proc.stdout.decode(errors="replace").strip()
        if proc.returncode != 0 or not out:
            err = proc.stderr.decode(errors="replace").strip()[-400:]
            raise RuntimeError(f"渲染进程退出码 {proc.returncode}：{err or '无输出'}")
        res = json.loads(out.splitlines()[-1])
        if not res.get("ok"):
            raise RuntimeError(res.get("error", "渲染失败"))
        return Path(res["path"])


@register("phi_lite", "琥珀雪绒", "Phigros 查分（轻量）", "0.1.0")
class PhiLitePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        cfg = config or {}
        self.plugin_dir = Path(__file__).parent
        token = str(cfg.get("api_token", "")).strip()
        if not token:
            f = self.plugin_dir / "api_token.txt"
            if f.exists():
                token = f.read_text("utf-8").strip()
        self.phi = PhiLite(self.plugin_dir, token)

    @filter.command("phi_bind")
    async def phi_bind(self, event: AstrMessageEvent, token: str = ""):
        """绑定 Phigros sessionToken：/phi_bind <sessionToken>"""
        if not token:
            yield event.plain_result("用法：/phi_bind <sessionToken>")
            return
        self.phi.bind(event.get_sender_id(), token)
        yield event.plain_result("绑定好了喵，试试 /phi_b30")

    @filter.command("phi_unbind")
    async def phi_unbind(self, event: AstrMessageEvent):
        """解绑：/phi_unbind"""
        self.phi.unbind(event.get_sender_id())
        yield event.plain_result("解绑了喵")

    @filter.command("phi_b30")
    async def phi_b30(self, event: AstrMessageEvent):
        """出 Best30 图：/phi_b30"""
        sess = self.phi.session_of(event.get_sender_id())
        if not sess:
            yield event.plain_result("先 /phi_bind <sessionToken> 绑一下喵")
            return
        yield event.plain_result("正在查…喵")
        try:
            data = self.phi.fetch_save(sess)
            path = self.phi.render_b30(data)
        except Exception as e:
            logger.error(f"phi_lite b30 失败: {e}")
            yield event.plain_result(f"出图失败：{e}")
            return
        yield event.chain_result([Comp.Image.fromFileSystem(str(path))])

# phi_lite —— AstrBot 用的 Phigros 查分插件（轻量版）
# 数据：r0semi.xtower.site 开放接口；曲绘：somnia.xtower.site。
# 出图交给同目录的 render_cli.py 独立进程画：主进程里 PIL 画日文假名会缺字，独立进程正常。

import json
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

import qrcode
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

    def fetch_history(self, session, limit=200):
        return self._post("/rks/history", {"auth": {"sessionToken": session}, "limit": limit, "offset": 0})

    # ---------- TapTap 扫码 ----------
    def qr_create(self):
        return self._post("/auth/qrcode", {})

    def qr_status(self, qr_id):
        url = API_BASE + "/auth/qrcode/" + urllib.parse.quote(qr_id) + "/status"
        req = urllib.request.Request(
            url, headers={"X-OpenApi-Token": self.api_token}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def qr_png(self, url) -> Path:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr_dir = self.out_dir.parent / "qr"
        qr_dir.mkdir(parents=True, exist_ok=True)
        out = qr_dir / "taptap_qr.png"
        qr.make_image(fill_color="black", back_color="white").save(out)
        return out

    # ---------- 渲染（独立进程） ----------
    def render_b30(self, data) -> Path:
        return self._render({"data": data})

    def render_song(self, data, song) -> Path:
        return self._render({"data": data, "mode": "song", "song": song})

    def _render(self, extra) -> Path:
        script = self.dir / "render_cli.py"
        payload = json.dumps(
            {"out_dir": str(self.out_dir), "cache_dir": str(self.cache_dir), **extra},
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

    async def _send_qr(self, event: AstrMessageEvent, path):
        """直接发二维码并记住消息 id，方便之后撤回；失败返回 None。"""
        try:
            file = "file://" + str(path)
            gid = event.get_group_id()
            if gid:
                res = await event.bot.api.call_action(
                    "send_group_msg", group_id=int(gid),
                    message=[{"type": "image", "data": {"file": file}}],
                )
            else:
                res = await event.bot.api.call_action(
                    "send_private_msg", user_id=int(event.get_sender_id()),
                    message=[{"type": "image", "data": {"file": file}}],
                )
            return (res or {}).get("message_id")
        except Exception as e:
            logger.warning(f"phi_lite 发二维码失败: {e}")
            return None

    async def _recall(self, event: AstrMessageEvent, msg_id):
        if not msg_id:
            return
        try:
            await event.bot.api.call_action("delete_msg", message_id=msg_id)
        except Exception as e:
            logger.warning(f"phi_lite 撤回二维码失败: {e}")

    @filter.command("phi_qrlogin")
    async def phi_qrlogin(self, event: AstrMessageEvent):
        """扫码绑定 TapTap：/phi_qrlogin"""
        import asyncio

        yield event.plain_result("我去要个码喵，稍等")
        try:
            info = await asyncio.to_thread(self.phi.qr_create)
            qr_id, vurl = info["qrId"], info["verificationUrl"]
        except Exception as e:
            yield event.plain_result(f"拿二维码失败：{e}")
            return
        qr_img = self.phi.qr_png(vurl)
        msg_id = await self._send_qr(event, qr_img)
        if msg_id is None:
            yield event.chain_result([Comp.Image.fromFileSystem(str(qr_img))])

        scanned = False
        deadline = __import__("time").time() + 180
        while __import__("time").time() < deadline:
            await asyncio.sleep(2)
            try:
                st = await asyncio.to_thread(self.phi.qr_status, qr_id)
            except Exception:
                continue
            status = (st.get("status") or "").lower()
            if status in ("pending", ""):
                continue
            if status in ("scanned", "scanning"):
                if not scanned:
                    scanned = True
                    await self._recall(event, msg_id)
                    yield event.plain_result("扫到啦，手机上点一下确认喵")
                continue
            if status in ("success", "confirmed"):
                await self._recall(event, msg_id)
                token = st.get("sessionToken")
                if not token:
                    yield event.plain_result("确认了，但没拿到 token，回头我看日志喵")
                    return
                self.phi.bind(event.get_sender_id(), token)
                yield event.plain_result("登好啦，已经帮你绑上，发 /phi_b30 看看喵")
                return
            if status in ("expired", "timeout", "canceled", "cancelled"):
                await self._recall(event, msg_id)
                yield event.plain_result("码过期了喵，再发一次 /phi_qrlogin")
                return
            await self._recall(event, msg_id)
            yield event.plain_result(f"登录没成，状态是 {status} 喵")
            return
        await self._recall(event, msg_id)
        yield event.plain_result("等太久啦，码先撤了，要不再来一次喵")

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

    @filter.command("phi_song")
    async def phi_song(self, event: AstrMessageEvent, name: str = ""):
        """查单曲成绩：/phi_song <曲名>"""
        if not name.strip():
            yield event.plain_result("用法：/phi_song <曲名>，比如 /phi_song 望影の方舟")
            return
        sess = self.phi.session_of(event.get_sender_id())
        if not sess:
            yield event.plain_result("先 /phi_bind <sessionToken> 绑一下喵")
            return
        try:
            data = self.phi.fetch_save(sess)
            path = self.phi.render_song(data, name.strip())
        except Exception as e:
            logger.error(f"phi_lite song 失败: {e}")
            yield event.plain_result(f"出图失败：{e}")
            return
        yield event.chain_result([Comp.Image.fromFileSystem(str(path))])

    @filter.command("phi_rks")
    async def phi_rks(self, event: AstrMessageEvent):
        """看 rks 变化曲线：/phi_rks"""
        sess = self.phi.session_of(event.get_sender_id())
        if not sess:
            yield event.plain_result("先 /phi_bind <sessionToken> 绑一下喵")
            return
        try:
            data = self.phi.fetch_save(sess)
            hist = self.phi.fetch_history(sess)
            path = self.phi._render({"data": data, "mode": "rks", "items": hist.get("items", [])})
        except Exception as e:
            logger.error(f"phi_lite rks 失败: {e}")
            yield event.plain_result(f"出图失败：{e}")
            return
        yield event.chain_result([Comp.Image.fromFileSystem(str(path))])

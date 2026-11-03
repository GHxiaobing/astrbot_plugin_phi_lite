# astrbot_plugin_phi_lite

AstrBot 用的 Phigros 查分插件，轻量自绘，不依赖浏览器截图。

## 指令

| 指令 | 作用 |
| --- | --- |
| `/phi_bind <sessionToken>` | 绑定 Phigros 存档 |
| `/phi_unbind` | 解绑 |
| `/phi_qrlogin` | TapTap 扫码登录，成功后自动绑定；检测到已扫码就撤回二维码 |
| `/phi_b30` | 出 Best30 成绩图 |
| `/phi_song <曲名>` | 查单曲成绩卡（各难度分数、Acc、定数、FC/AP） |
| `/phi_rks` | 出 rks 变化曲线 |
| `/phi_random [难度]` | 随机抽一首歌，可限定 IN / AT / HD / EZ |
| `/phi_guess` | 出一道猜曲题（给难度、定数、字数、首字） |
| `/phi_answer <曲名>` | 回答猜曲题 |

## 特点

- 数据来自 r0semi.xtower.site 开放接口，曲绘来自 somnia.xtower.site
- 自带两套字体（phi_cn.ttf 全字符覆盖 + NotoSansJP），日文假名与生僻字都不会出方块
- 渲染放在独立进程 `render_cli.py` 里跑，避开某些宿主进程里 Pillow 画字缺字的问题
- 渲染进程支持三种模式：`b30`（默认）、`song`、`rks`

## 安装

1. 把本目录放进 AstrBot 的 `data/plugins/`，重载插件。
2. 首次使用前，把开放平台 token 写进插件目录的 `api_token.txt`，或在插件配置里填 `api_token`。
3. 发 `/phi_bind <sessionToken>` 或 `/phi_qrlogin` 绑定存档。

## 目录

- `main.py` 指令与数据请求
- `render_cli.py` 独立渲染进程，接收 stdin 的 JSON，输出图片路径
- `resources/font/` 随插件分发的字体

## 已知限制

- 扫码的「撤回二维码」依赖 OneBot 的 `delete_msg`；撤不掉时会补一句「上面那张码作废了」兜底
- 存档很旧时 rks 曲线会是一条直线，这是数据本身如此

## 猜曲说明

`/phi_guess` 出的题存在内存里，同一会话一份，三分钟过期；`/phi_answer` 只要答案被包含在输入里就算对，不区分大小写和空格。

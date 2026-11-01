# astrbot_plugin_phi_lite

AstrBot 用的 Phigros 查分插件，轻量自绘，不依赖浏览器截图。

## 功能

- `/phi_bind <sessionToken>` 绑定 Phigros 存档
- `/phi_unbind` 解绑
- `/phi_b30` 生成 Best30 成绩图

## 特点

- 数据来自 r0semi.xtower.site 开放接口，曲绘来自 somnia.xtower.site
- 自带两套字体（phi_cn.ttf 全字符覆盖 + NotoSansJP），日文假名与生僻字都不会出方块
- 渲染放在独立进程 `render_cli.py` 里跑，避开某些宿主进程里 Pillow 画字缺字的问题

## 安装

把本目录放进 AstrBot 的 `data/plugins/`，重载插件即可。首次使用前把开放平台 token 写进插件目录的 `api_token.txt`，或在插件配置里填 `api_token`。

## 目录

- `main.py` 指令与数据请求
- `render_cli.py` 独立渲染进程，接收 stdin 的 JSON 输出图片路径
- `resources/font/` 随插件分发的字体

# baka图床 / bakaimg

baka图床是一个本地优先、可自托管的Flask图片站点：上传、整理、分享、收藏与后台治理一站完成，全部数据保存在你自己的机器上。

## 主要功能

- **安全上传**：支持JPEG、PNG、WebP和GIF；上传内容会真实解码校验、重新编码清除附带元数据，再以随机存储键原子写入，并自动生成WebP缩略图与SHA-256校验和。
- **灵活可见性**：每张图片可选私有、不公开（随机链接）或公开；公开且审核通过的图片才进入发现页。
- **发现与分享**：公开发现页支持搜索与排序；独立分享页展示作者、尺寸、浏览次数与原图链接。
- **相册编排**：勾选图片创建相册，保存后可调整顺序；支持三种访问方式，删除相册不会删除图片。
- **仪表盘**：登录后的个人首页，汇总图片、相册、收藏和空间用量，集中放置上传、图库、相册、收藏、应用钥匙等入口；首页本身只保留登录与创建账号。
- **收藏**：登录用户可以在原页面收藏或移除公开且审核通过的图片。
- **图片加载**：选图后确认上传，显示实际进度；图库分批续载，图片加载失败可原地重试，不反复刷新页面。
- **应用钥匙**：勾选所需用途，设置有效天数，随时收回；完整钥匙只显示一次，数据库只保存摘要，接口使用Bearer认证。
- **管理后台**：用户与角色、图片审核、相册治理、收藏清理、令牌治理、存储配额、审计日志与主题外观。
- **运维与备份**：一致性诊断、维护模式、SQLite在线快照备份（附逐文件SHA-256清单）、创建即预检的恢复流程。
- **账号与登录**：默认使用本地登录与注册，首个账号获得超级管理员权限；可选接入OpenID Connect身份服务，本机一次性恢复入口用于故障恢复。
- **操作反馈**：密码可切换显示，主题设置支持预览与取消；重要操作使用确认弹窗，右下角提示自动收起。

## 快速开始

### Windows

要求Windows 10/11与Python 3.12至3.14（含`py`启动器）。依赖全部来自仓库自带的`wheelhouse`目录，无需联网下载。

1. 初始化并启动（自动创建虚拟环境、安装离线依赖、执行迁移和系统预检）：

```bat
start.bat
```

默认地址：`http://127.0.0.1:5200`。

2. 第一次打开站点会直接进入初始化页面：填写站点名称、后台路径（默认`bakaadmin`，可以换成只有你知道的名字）和管理员账号，提交后自动登录并进入后台。后台路径之后也可以在后台“系统管理 → 后台路径”里修改；忘记时可在服务器上运行`flask --app wsgi:app admin-path`查看，加`--reset`恢复默认。也可以用命令行创建首个管理员（按提示输入用户名、邮箱、显示名和密码）：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app create-admin
```

3. 也可以生成本机一次性恢复链接（五分钟有效），在浏览器中完成首位管理员创建或临时管理会话：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app local-recovery-link
```

4. 本地登录和注册无需配置外部服务；如需要外部登录，可在后台`/bakaadmin/gateway/`填入OpenID Connect发行者地址、Client ID与Client Secret，保留本地账号入口。

日常备份与校验：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app backup-create
.venv\Scripts\python.exe -m flask --app wsgi:app backup-list
.venv\Scripts\python.exe -m flask --app wsgi:app backup-verify 备份文件名.zip
```

### macOS

自己的Mac上，双击根目录的`bakaimg.command`，或在项目目录运行：

```bash
sh bakaimg-macos
```

打开数字管理面板：输入编号即可启动、停止、重新启动、开启/关闭开机自启，面板顶部实时显示是否已运行、运行端口和开机自启状态。无需sudo、域名或证书，首次启动前选择“13 安装/修复运行环境”即可从本地离线依赖一键装好。

服务器正式部署（Homebrew、Nginx与HTTPS域名）：

```bash
sudo sh deploy-macos.sh img.example.com /完整路径/origin.pem /完整路径/origin.key
```

兼容Apple芯片和Intel Mac，详细步骤见[`docs/MACOS.md`](docs/MACOS.md)。

### Linux

运行`sudo sh deploy-linux.sh`，默认从`https://github.com/saubaka/bakaimg.git`安装；也可以直接使用根目录的Linux x64单文件`bakaimg`管理器。详细步骤见[`docs/DEBIAN12.md`](docs/DEBIAN12.md)。

## 界面

界面使用BakaMail Admin设计系统（浅色纯色版v5），文件在`app/static/design/bakamail-admin-v5/`：页面先引入`tokens.css`，再引入`components/bundle.css`，组件类名以`ba-`开头；颜色、圆角、阴影、间距都取自令牌变量。页面没有边框、分隔线和渐变，动效只做透明度和位移，并遵守“减少动态效果”。设计系统没有的部分（空状态插画、开关、复选框、手机导航、上传区等）用同一套令牌自行搭建，样式在`app/static/styles/`。

## 技术要点

- Python、Flask、Jinja2、SQLAlchemy、Flask-Migrate与本地SQLite（WAL）。
- Pillow安全重编码：限制单张20MiB、每批10张、总像素4000万、最长边12000、GIF最多100帧。
- 图片二进制存于随机分层路径，数据库只存元数据、校验和与相对存储键；`media-check`可核对双向一致性。
- 会话与令牌最小化存储：浏览器会话只存随机令牌，数据库只存SHA-256摘要；OAuth令牌加密保存。
- 后台操作全部写入审计日志；日志不保存原始IP。
- 备份使用SQLite在线备份API生成一致性快照，只收录数据库已跟踪的媒体，创建后立即执行完整恢复预检。
- 生产入口使用Waitress；Linux和macOS只监听动态选择的`127.0.0.1`端口，分别由systemd和launchd持续托管。

## 部署概述

- 开发/本地：`start.bat`使用Flask内置服务器，默认`127.0.0.1:5200`。
- Windows生产：设置独立密钥与HTTPS站点地址后运行`run-production.bat`。
- Debian 12及常见systemd Linux：运行`sudo sh deploy-linux.sh`，或执行`sudo ./bakaimg install 域名 源站证书 私钥`。管理器会配置systemd、自动避让冲突的本地端口、Nginx唯一域名、Cloudflare Origin CA源站证书与日志轮转；不检测Cloudflare IP网段。
- macOS 13及更高版本：本机使用`sh bakaimg-macos`（或双击`bakaimg.command`）打开数字管理面板；正式部署运行`sudo sh deploy-macos.sh 域名 源站证书 私钥`，配置launchd常驻运行、可独立开关的开机自启、动态本地端口、Homebrew Nginx、Origin CA源站证书和定时日志清理。
- 恢复只允许停服后在本机命令行执行：`restore-backup 备份文件名.zip --offline --confirm RESTORE`，并会自动生成回滚备份。

## 目录结构

```text
app/                    应用源码（工厂、蓝图、服务、模板、静态资源）
migrations/             Flask-Migrate数据库迁移
wheelhouse/             离线Python依赖
wheelhouse-linux-x64/   Debian 12 / Python 3.11离线依赖
wheelhouse-macos-arm64/ Apple芯片 / Python 3.14离线依赖
wheelhouse-macos-x64/   Intel Mac / Python 3.14离线依赖
instance/               运行数据（数据库、上传、备份、日志，不入库）
deploy-linux.sh         Debian 12及常见Linux部署脚本
bakaimg                 Linux x64单文件管理器
deploy-macos.sh         macOS部署脚本
bakaimg-macos           macOS数字管理面板（本机直接运行；部署后可用sudo bakaimg）
bakaimg.command         macOS双击入口，在终端中打开管理面板
start.bat               本地初始化与启动入口
run-production.bat      生产启动入口
serve.py                Waitress生产服务入口
wsgi.py                 WSGI入口
requirements*.txt       各平台依赖清单
.env.example            环境变量样例
pyproject.toml          包配置与工具设置
```

## API v1

所有API请求使用请求头：

```text
Authorization: Bearer cn_完整令牌
```

主要接口：

- `GET /api/v1/me`：令牌、账号与配额状态
- `GET /api/v1/images/`：列出自己的图片
- `POST /api/v1/images/`：使用multipart的`image`字段安全上传单张图片
- `GET /api/v1/images/<id>/`：读取自己的图片元数据
- `GET /api/v1/images/<id>/content/original/`：读取自己的清理后原图
- `GET /api/v1/images/<id>/content/thumbnail/`：读取缩略图
- `DELETE /api/v1/images/<id>/`：将图片移入回收站

上传时可同时提供`visibility=private|unlisted|public`、`title`和`alt_text`。API错误统一返回JSON，不接受Cookie会话代替Bearer令牌。

# baka图床 / bakaimg

baka图床是一个本地优先、可自托管的Flask图片站点：上传、整理、分享、收藏与后台治理一站完成，全部数据保存在你自己的机器上。

> 这是全新未初始化副本：不含数据库、管理员账号、业务内容或任何凭据；按下方“快速开始”执行`start.bat`完成初始化，再用`create-admin`创建首个管理员即可使用。

## 主要功能

- **安全上传**：支持JPEG、PNG、WebP和GIF；上传内容会真实解码校验、重新编码清除附带元数据，再以随机存储键原子写入，并自动生成WebP缩略图与SHA-256校验和。
- **灵活可见性**：每张图片可选私有、不公开（随机链接）或公开；公开且审核通过的图片才进入发现页。
- **发现与分享**：公开发现页支持搜索与排序；独立分享页展示作者、尺寸、浏览次数与原图链接。
- **相册编排**：相册支持三种访问方式，可自由挑选图片、调整顺序；删除相册不会删除图片。
- **收藏**：登录用户可以收藏公开且审核通过的图片。
- **API令牌**：有期限、有作用域、可随时撤销的Bearer令牌；完整令牌只显示一次，数据库只保存摘要。
- **管理后台**：用户与角色、图片审核、相册治理、收藏清理、令牌治理、存储配额、审计日志与主题外观。
- **运维与备份**：一致性诊断、维护模式、SQLite在线快照备份（附逐文件SHA-256清单）、创建即预检的恢复流程。
- **统一身份**：登录接入OpenID Connect发行者（Authorization Code + PKCE），不提供本地公开注册；本机一次性恢复入口用于首位管理员接入与故障恢复。

## 快速开始

要求Windows 10/11与Python 3.12至3.14（含`py`启动器）。依赖全部来自仓库自带的`wheelhouse`目录，无需联网下载。

1. 初始化并启动（自动创建虚拟环境、安装离线依赖、执行迁移和系统预检）：

```bat
start.bat
```

默认地址：`http://127.0.0.1:5200`。

2. 创建首个管理员（按提示输入用户名、邮箱、显示名和密码）：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app create-admin
```

3. 也可以生成本机一次性恢复链接（五分钟有效），在浏览器中完成首位管理员创建或临时管理会话：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app local-recovery-link
```

4. 在后台`/admin/gateway/`填入OpenID Connect发行者地址、Client ID与Client Secret完成统一身份连接；此后前台用户与管理后台都通过该身份服务登录。

日常备份与校验：

```bat
.venv\Scripts\python.exe -m flask --app wsgi:app backup-create
.venv\Scripts\python.exe -m flask --app wsgi:app backup-list
.venv\Scripts\python.exe -m flask --app wsgi:app backup-verify 备份文件名.zip
```

## 技术要点

- Python、Flask、Jinja2、SQLAlchemy、Flask-Migrate与本地SQLite（WAL）。
- Pillow安全重编码：限制单张20MiB、每批10张、总像素4000万、最长边12000、GIF最多100帧。
- 图片二进制存于随机分层路径，数据库只存元数据、校验和与相对存储键；`media-check`可核对双向一致性。
- 会话与令牌最小化存储：浏览器会话只存随机令牌，数据库只存SHA-256摘要；OAuth令牌加密保存。
- 后台操作全部写入审计日志；日志不保存原始IP。
- 备份使用SQLite在线备份API生成一致性快照，只收录数据库已跟踪的媒体，创建后立即执行完整恢复预检。
- 生产入口使用Waitress；生产模式强制独立密钥与HTTPS站点地址，信任代理头时必须监听回环地址。

## 部署概述

- 开发/本地：`start.bat`使用Flask内置服务器，默认`127.0.0.1:5200`。
- 生产：设置`CLOUDNEST_SECRET_KEY`（高熵随机值）与`CLOUDNEST_SITE_URL`（HTTPS地址）后运行`run-production.bat`。
- 对外发布建议由反向代理终止HTTPS再转发到回环地址；仅在可信代理后方才设置`CLOUDNEST_TRUST_PROXY_HOPS=1`。
- 恢复只允许停服后在本机命令行执行：`restore-backup 备份文件名.zip --offline --confirm RESTORE`，并会自动生成回滚备份。

## 目录结构

```text
app/                    应用源码（工厂、蓝图、服务、模板、静态资源）
migrations/             Flask-Migrate数据库迁移
wheelhouse/             离线Python依赖
instance/               运行数据（数据库、上传、备份、日志，不入库）
start.bat               本地初始化与启动入口
run-production.bat      生产启动入口
serve.py                Waitress生产服务入口
wsgi.py                 WSGI入口
requirements*.txt       依赖清单（配合wheelhouse离线安装）
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

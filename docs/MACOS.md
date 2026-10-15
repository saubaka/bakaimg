# macOS部署与管理

支持macOS 13及更高版本，兼容Apple芯片和Intel Mac。macOS使用独立的`deploy-macos.sh`和`bakaimg-macos`，Windows和Linux入口保持不变。

`bakaimg-macos`是同一个数字管理面板，会自动识别两种使用方式：

| 方式 | 适用场景 | 权限 | 服务由谁托管 |
| --- | --- | --- | --- |
| 本机运行 | 自己的Mac，本地使用 | 不需要sudo、域名或证书 | 面板直接管理后台进程，开机自启使用当前用户的LaunchAgent |
| 正式部署 | 服务器，HTTPS域名对外 | `sudo`（面板会自动提权） | launchd托管应用和Nginx，应用只监听`127.0.0.1`本地端口 |

## 零、本机一键管理面板

在项目目录执行，或在Finder中双击`bakaimg.command`（会在“终端”中打开）：

```bash
sh bakaimg-macos
```

面板顶部实时显示：

- 运行状态：已运行（PID、已运行多久、手动启动或开机自启托管）/ 未运行；
- 访问地址与运行端口（首选端口被占用时自动换到下一个可用端口，并显示实际端口）；
- 健康检查结果与应用版本；
- 开机自启：已开启 / 已关闭；
- 运行环境是否就绪、项目目录与日志文件位置。

输入编号选择操作，直接回车刷新状态：

| 编号 | 功能 |
| --- | --- |
| 1 / 2 / 3 | 启动 / 停止 / 重新启动 |
| 4 / 5 | 开启 / 关闭开机自启（不影响当前是否在运行） |
| 6 | 修改首选端口（运行中会自动重启生效） |
| 7 | 在浏览器中打开网站 |
| 8 / 9 | 查看最近日志 / 实时日志（Ctrl+C 返回） |
| 10 | 创建并校验数据备份 |
| 11 | 整理日志（超过32MiB压缩归档，保留14天） |
| 12 | 运行检查（项目文件、依赖、数据目录、健康与就绪） |
| 13 | 安装/修复运行环境（本地离线依赖，缺少Python 3.14时可选用Homebrew安装） |
| 14 | 生成本机管理员恢复链接（5分钟有效，仅一次） |
| 0 | 退出（不会停止网站） |

首次使用先选`13`：面板会创建独立的`.venv-macos`，从`wheelhouse-macos-arm64`或`wheelhouse-macos-x64`离线安装依赖，不会改动Windows用的`.venv`。如果机器上只有Python 3.12或3.13，离线包不适用，面板会询问是否联网安装同版本依赖。

所有功能也可以直接用命令执行，便于脚本调用：

```bash
sh bakaimg-macos start
sh bakaimg-macos stop
sh bakaimg-macos restart
sh bakaimg-macos enable        # 开启开机自启
sh bakaimg-macos disable       # 关闭开机自启
sh bakaimg-macos status
sh bakaimg-macos --status-json # 机器可读状态
sh bakaimg-macos port 5300
```

### 关于开机自启和“桌面/文稿/下载”目录

macOS的隐私保护不允许后台任务（launchd）读取`~/Desktop`、`~/Documents`、`~/Downloads`中的文件。因此：

- **手动启动、停止不受影响**，面板直接在“终端”权限下运行服务；
- **开启开机自启时**，面板会先实际检测能否读取项目目录；如果会被拦截，会明确提示并拒绝开启，而不是装一个登录后必然失败的自启任务；
- 解决办法：把整个项目文件夹移到不受保护的位置（例如`~/bakaimg`，推荐），或在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中添加`/bin/sh`和`.venv-macos/bin/python`。

开机自启的含义是“用户登录后自动运行，异常退出自动重启”。关闭自启不会停止正在运行的服务，停止服务也不会关闭自启。

### 自定义

| 环境变量 | 作用 |
| --- | --- |
| `BAKAIMG_PYTHON` | 指定创建运行环境所用的Python（3.12–3.14，优先3.14） |
| `BAKAIMG_VENV_DIR` | 指定运行环境目录，默认项目下的`.venv-macos` |
| `BAKAIMG_MODE` | 强制使用`local`或`production`方式 |
| `NO_COLOR=1` | 关闭彩色输出 |

本机运行的首选端口保存在`instance/runtime/macos-local.conf`，日志在`instance/logs/bakaimg-macos.log`。

以下章节说明服务器上的正式部署。

## 一、准备环境

macOS部署使用Homebrew安装Python 3.14、Nginx、OpenSSL 3和Git。先从[Homebrew官网](https://brew.sh/)完成安装，然后确认：

```bash
brew --version
```

部署脚本不会运行来路不明的远程安装命令。Apple芯片默认识别`/opt/homebrew`，Intel Mac默认识别`/usr/local`。

## 二、准备Origin CA源站证书

1. 在Cloudflare中为图床域名创建Origin CA源站证书。
2. 主机名填写实际访问域名，例如`img.example.com`。
3. 将证书和无密码私钥分别保存为`origin.pem`和`origin.key`。
4. Cloudflare的SSL/TLS模式选择“完全（严格）”。

管理器只校验证书签发者、域名、有效期、私钥格式和公私钥匹配，不检测访问IP网段，也不启用客户端证书验证。

## 三、运行部署脚本

```bash
git clone https://github.com/saubaka/bakaimg.git /tmp/bakaimg-bootstrap
sudo sh /tmp/bakaimg-bootstrap/deploy-macos.sh \
  img.example.com \
  /Users/你的账号/Documents/baka-cert/origin.pem \
  /Users/你的账号/Documents/baka-cert/origin.key
```

默认安装目录为`/opt/bakaimg/current`。脚本会：

- 保留并更新Git工作目录，不覆盖未提交修改；
- 安装macOS所需组件、创建独立Python环境并从仓库自带目录离线安装运行依赖；
- 保存证书、生成Nginx配置并校验；
- 安装`launchd`常驻任务与每日日志整理任务；
- 安装`bakaimg`和`bakaimg-macos`两个等价的管理命令。

如果暂时没有证书，也可以先部署运行环境：

```bash
sudo sh /tmp/bakaimg-bootstrap/deploy-macos.sh
sudo bakaimg configure img.example.com /完整路径/origin.pem /完整路径/origin.key
```

自定义仓库、分支或目录：

```bash
sudo sh deploy-macos.sh \
  --repo https://github.com/saubaka/bakaimg.git \
  --branch main \
  --dir /opt/bakaimg/current
```

## 四、管理菜单和命令

在任意目录打开管理面板（会自动请求管理员权限）：

```bash
sudo bakaimg
```

面板与本机方式相同：顶部显示应用和Nginx是否运行（含PID）、访问域名、本地端口、开机自启、证书有效期与日志规则；编号`1`–`12`同上，`13`为“更新域名与证书”，`14`为“修改日志规则”。

常用命令：

```bash
sudo bakaimg status
sudo bakaimg --status-json
sudo bakaimg start
sudo bakaimg stop
sudo bakaimg restart
sudo bakaimg enable
sudo bakaimg disable
sudo bakaimg port 5200
sudo bakaimg logs 200
sudo bakaimg backup
sudo bakaimg retention 14 32
sudo bakaimg maintenance
sudo bakaimg doctor
```

`enable`和`disable`只开关开机自动运行，不会启动或停止当前服务；`start`和`stop`也不会改变自启设置。首次部署默认开启自启，之后以面板中的选择为准，重新运行部署脚本更新时不会改回。退出管理面板不会停止网站；应用和Nginx异常退出后，`launchd`会自动重新启动。

状态JSON包含`mode`、`running`、`healthy`、`pid`、`autostart_enabled`、`local_port`等字段，便于监控脚本读取。

## 五、本地端口自动避让

默认首选端口是`5200`。每次应用启动前，管理器会检查端口：

1. 当前端口可用时继续使用；
2. 被占用时自动选择下一个可用端口；
3. 更新运行环境与Nginx代理地址；
4. 将当前端口写入`/Library/Application Support/bakaimg/active-port`并显示在管理面板。

应用始终只绑定`127.0.0.1`，不会直接监听公网地址。

## 六、域名和访问边界

```bash
sudo bakaimg configure img.example.com /完整路径/origin.pem /完整路径/origin.key
```

域名必须是一个完整主机名，不接受IP、端口、路径、通配符或多个域名。Nginx的80端口直接断开，443端口只接受设置的域名，其他SNI拒绝握手。Flask会再次校验相同域名。

域名变化后，需要同步修改统一身份服务中的主页和回调地址，例如`https://img.example.com/auth/callback/`。

## 七、日志保存与清理

日志保存在`/Library/Logs/bakaimg/`。默认单文件达到32MiB时保存压缩副本并清空当前日志，超过14天的旧副本会由每日任务清除。整理过程中不需要停止网站。

```bash
sudo bakaimg retention 30 64
sudo bakaimg maintenance
```

上例表示保留30天、单文件达到64MiB时保存压缩副本。定时整理由`launchd`完成，不需要额外日志服务。

## 八、更新与检查

```bash
sudo sh /opt/bakaimg/current/deploy-macos.sh
sudo bakaimg doctor
sudo bakaimg status
```

只更新管理命令：

```bash
sudo sh /opt/bakaimg/current/deploy-macos.sh --manager-only
```

更新不会删除`instance/`中的数据库、图片或备份。排查运行状态时可使用：

```bash
sudo launchctl print system/com.saubaka.bakaimg
sudo launchctl print system/com.saubaka.bakaimg.nginx
sudo "$(brew --prefix nginx)/bin/nginx" -t -c "/Library/Application Support/bakaimg/nginx.conf"
sudo cat "/Library/Application Support/bakaimg/active-port"
```

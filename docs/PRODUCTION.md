# baka图床生产运行

Linux正式部署优先使用`deploy-linux.sh`、单文件`bakaimg`管理器、systemd、本地动态端口、Nginx与Cloudflare Origin CA源站证书，完整步骤见[DEBIAN12.md](DEBIAN12.md)。macOS使用`deploy-macos.sh`、launchd与独立管理脚本，完整步骤见[MACOS.md](MACOS.md)。本页后续内容保留Windows生产运行方式。

## 安全边界

Windows生产入口使用本地wheelhouse中的Waitress，不使用Flask开发服务器，默认只监听`127.0.0.1:5200`。Linux和macOS管理器同样只监听回环地址；端口冲突时会自动切换并同步Nginx。

生产模式强制要求：

- 独立且不可预测的`CLOUDNEST_SECRET_KEY`；
- `CLOUDNEST_SITE_URL`必须是最终的`https://`地址；
- 正式SQLite和媒体继续位于独立`instance`目录；
- 不把密钥写入仓库、README、日志或会话记录。

## 启动前设置

在仅当前CMD窗口有效的环境变量中设置值：

```bat
set CLOUDNEST_SECRET_KEY=请替换为高熵随机值
set CLOUDNEST_SITE_URL=https://images.example.com
set CLOUDNEST_HOST=127.0.0.1
set CLOUDNEST_PORT=5200
set CLOUDNEST_THREADS=8
```

可以在可信本机生成随机值：

```bat
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

不要把输出保存进项目文件。先执行生产预检：

```bat
run-production.bat --check-only
```

通过后启动：

```bat
run-production.bat
```

## 反向代理

- 反向代理必须覆盖客户端提供的`X-Forwarded-*`头，只传递自己生成的可信值。
- 只有应用确实位于可信反向代理后方时，才设置`CLOUDNEST_TRUST_PROXY_HOPS=1`；直连运行保持默认`0`。
- 应用只信任显式配置的代理层数。错误设置会影响外部URL、HTTPS判断和来源审计。
- HTTPS响应会发送HSTS、安全内容策略、拒绝嵌入、MIME嗅探防护、最小权限策略和严格来源策略。
- 反向代理应配置上传体积上限不低于应用请求上限，并保留合理超时；不要缓存登录、后台、API或维护响应。

## 发布流程

1. 停止旧进程或开启维护窗口。
2. 运行`backup-create`并保管返回的文件名和SHA-256。
3. 更新代码和本地wheelhouse。
4. 设置生产环境变量并运行`run-production.bat --check-only`；该步骤会升级迁移、同步内置权限和执行一致性检查。
5. 启动生产服务，确认`/healthz`为200、`/readyz`为200。
6. 以普通账号检查登录、上传、缩略图、分享和API；以管理员检查运维中心。

生产脚本不会联网下载依赖，不会提权，也不会修改系统执行策略、注册表或安全软件设置。

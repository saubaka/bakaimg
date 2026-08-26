# Debian 12与Linux部署管理

推荐使用Debian 12 x86_64。部署后，baka图床由systemd持续运行，应用只监听`127.0.0.1`本地端口，Nginx负责唯一域名的HTTPS访问。

管理器也支持使用systemd与glibc的其他x86_64 Linux，并可识别APT、DNF、Pacman或Zypper。离线依赖固定用于Python 3.11；其他发行版必须先具备Python 3.11。

## 一、准备Cloudflare Origin CA证书

1. 在Cloudflare DNS中添加图床域名，例如`img.example.com`。
2. 在“SSL/TLS → 概述”选择“完全（严格）”。
3. 在“SSL/TLS → 源服务器”创建Origin CA源站证书：
   - 主机名填写图床实际域名；
   - 密钥类型可用ECC或RSA；
   - 把证书和私钥分别保存为`origin.pem`、`origin.key`；
   - 私钥只显示一次，不要放入Git仓库或聊天记录。

本部署只校验并使用Origin CA源站证书，不下载或检测Cloudflare IP网段，也不启用Authenticated Origin Pulls客户端证书验证。

## 二、使用仓库部署脚本

默认仓库是`https://github.com/saubaka/bakaimg.git`。在全新的Debian 12服务器上执行：

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates
git clone https://github.com/saubaka/bakaimg.git /tmp/bakaimg-bootstrap
sudo sh /tmp/bakaimg-bootstrap/deploy-linux.sh
```

脚本默认安装到`/opt/bakaimg/current`，管理命令安装到`/usr/local/bin/bakaimg`。如果证书已经在服务器上，可以一次完成：

```bash
sudo sh /tmp/bakaimg-bootstrap/deploy-linux.sh \
  img.example.com \
  /root/baka-cert/origin.pem \
  /root/baka-cert/origin.key
```

自定义仓库、分支或目录：

```bash
sudo sh deploy-linux.sh \
  --repo https://github.com/saubaka/bakaimg.git \
  --branch main \
  --dir /opt/bakaimg/current
```

脚本更新现有仓库时只执行fast-forward；目录存在未提交修改时会停止，不使用`reset --hard`覆盖文件。

## 三、直接使用管理器

已经完整上传发布目录时，也可以直接运行：

```bash
cd /opt/bakaimg/current
chmod +x ./bakaimg
sudo ./bakaimg install img.example.com /root/baka-cert/origin.pem /root/baka-cert/origin.key
```

安装器会完成Linux组件、独立用户、Python 3.11离线环境、systemd、Nginx、日志轮转、数据库迁移和图片一致性检查；同时校验证书签发者、域名、有效期、私钥及公私钥匹配。

证书保存到`/etc/bakaimg/tls/`，私钥仅root可读。确认网站正常后，可以删除临时证书副本。

## 四、管理菜单与命令

安装后在任意目录运行：

```bash
sudo bakaimg
```

管理面板显示服务、Nginx、自启、日志任务、唯一域名，以及当前`127.0.0.1`端口和端口占用状态。

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
sudo bakaimg retention 14 32
sudo bakaimg maintenance
sudo bakaimg doctor
```

退出管理器不会停止网站。systemd使用`Restart=always`，程序异常结束时会自动重新启动。

## 五、本地端口自动切换

默认首选端口为`5200`。每次启动或自动重启前，systemd都会调用管理器：

1. 当前端口可用时继续使用；
2. 端口被占用时寻找下一个可用端口；
3. 把结果写入`/etc/bakaimg/manager.json`、`/etc/bakaimg/bakaimg.env`和`/run/bakaimg/port`；
4. 同步Nginx代理地址，通过`nginx -t`后再启动应用。

设置新的首选端口：

```bash
sudo bakaimg port 5300
```

`sudo bakaimg --status-json`会返回`local_host`、`local_port`和`port_state`，方便监控读取。

## 六、域名与证书更新

```bash
sudo bakaimg configure img.example.com /root/baka-cert/origin.pem /root/baka-cert/origin.key
```

域名只允许纯主机名，不接受IP、端口、路径、通配符或多个域名。管理器不检查域名解析IP属于哪个网络，只检查上传证书是否为Cloudflare Origin CA证书、是否覆盖域名、是否有效及是否与私钥匹配。

域名变化后，还要在统一身份服务中同步主页和回调，例如`https://img.example.com/auth/callback/`。

## 七、Nginx访问边界

- 应用只绑定`127.0.0.1:<当前端口>`，不监听公网地址；
- Nginx的80端口直接断开；
- 443端口只接受配置的唯一域名，其他SNI拒绝握手；
- Nginx使用上传的Cloudflare Origin CA证书和私钥；
- Nginx固定转发Host，Flask再次执行同一域名白名单；
- 不包含Cloudflare IP allowlist、DNS网段判断或客户端mTLS校验。

Origin CA是源站服务器证书，不是访问者身份证明。只使用Origin CA时，知道源站IP的客户端仍可能在忽略证书信任错误后直接连接正确域名；这是本方案明确保留的边界。

## 八、日志保存与清理

日志保存在`/var/log/bakaimg/`，包含`app.log`、`error.log`、`access.log`和`nginx-error.log`。默认每天检查，单文件达到32MiB时轮转，压缩后最多保留14天。systemd timer使用`Persistent=true`，关机期间错过的整理会在下次启动补做。

```bash
sudo bakaimg retention 30 64
```

上例表示最多保留30天，单文件达到64MiB时轮转。

## 九、更新与检查

完整更新：

```bash
sudo sh /opt/bakaimg/current/deploy-linux.sh
sudo bakaimg doctor
```

只更新管理文件：

```bash
sudo sh /opt/bakaimg/current/deploy-linux.sh --manager-only
```

更新不会删除`instance/`中的数据库、图片或备份。完成后检查：

```bash
sudo bakaimg doctor
sudo bakaimg status
systemctl status bakaimg --no-pager
systemctl status nginx --no-pager
sudo nginx -t
sudo cat /run/bakaimg/port
sudo ss -lntp
```

正常情况下，Python只监听管理面板显示的`127.0.0.1`端口。出现502时，比较管理面板端口、`/run/bakaimg/port`和Nginx配置，再查看应用日志。

## 十、其他Linux说明

脚本支持APT、DNF、Pacman和Zypper。共同要求是x86_64、systemd、glibc与Python 3.11。Debian 12是完整验证平台；其他发行版默认Python不是3.11时，应先通过官方软件源安装Python 3.11。

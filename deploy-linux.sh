#!/bin/sh
set -eu

REPO_URL="${BAKAIMG_REPO_URL:-https://github.com/saubaka/bakaimg.git}"
BRANCH="${BAKAIMG_BRANCH:-main}"
INSTALL_DIR="${BAKAIMG_INSTALL_DIR:-/opt/bakaimg/current}"
MANAGER_ONLY=0

usage() {
    printf '%s\n' \
        'bakaimg Linux 部署脚本' \
        '' \
        '用法：' \
        '  sudo sh deploy-linux.sh [选项] [域名 源站证书PEM 私钥PEM]' \
        '' \
        '选项：' \
        '  --repo URL       Git仓库，默认 https://github.com/saubaka/bakaimg.git' \
        '  --branch NAME    分支，默认 main' \
        '  --dir PATH       安装目录，默认 /opt/bakaimg/current' \
        '  --manager-only   只安装/更新 /usr/local/bin/bakaimg' \
        '  -h, --help       显示帮助'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo)
            [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --repo 参数。' >&2; exit 2; }
            REPO_URL=$2
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --branch 参数。' >&2; exit 2; }
            BRANCH=$2
            shift 2
            ;;
        --dir)
            [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --dir 参数。' >&2; exit 2; }
            INSTALL_DIR=$2
            shift 2
            ;;
        --manager-only)
            MANAGER_ONLY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            printf '未知选项：%s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { printf '%s\n' '请使用 sudo 运行此脚本。' >&2; exit 1; }
[ "$(uname -m)" = "x86_64" ] || { printf '%s\n' '当前发布文件仅支持 Linux x86_64。' >&2; exit 1; }
[ -d /run/systemd/system ] || { printf '%s\n' '此脚本需要使用 systemd 的 Linux。' >&2; exit 1; }
case "$INSTALL_DIR" in
    /*) ;;
    *) printf '%s\n' '安装目录必须是绝对路径。' >&2; exit 1 ;;
esac
[ "$INSTALL_DIR" != "/" ] || { printf '%s\n' '安装目录不能是根目录。' >&2; exit 1; }

if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git ca-certificates
elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --needed --noconfirm git ca-certificates
elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive install git ca-certificates
else
    printf '%s\n' '未找到APT、DNF、Pacman或Zypper。' >&2
    exit 1
fi

if [ -d "$INSTALL_DIR/.git" ]; then
    [ -z "$(git -C "$INSTALL_DIR" status --porcelain)" ] || {
        printf '%s\n' '安装目录存在未提交修改，为避免覆盖已停止更新。' >&2
        exit 1
    }
    git -C "$INSTALL_DIR" fetch --prune origin "$BRANCH"
    git -C "$INSTALL_DIR" merge --ff-only "origin/$BRANCH"
elif [ -e "$INSTALL_DIR" ]; then
    printf '%s\n' "安装目录已存在但不是Git仓库：$INSTALL_DIR" >&2
    exit 1
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
fi

MANAGER="$INSTALL_DIR/bakaimg"
[ -f "$MANAGER" ] || { printf '%s\n' "仓库中缺少bakaimg管理文件：$MANAGER" >&2; exit 1; }
chmod 0755 "$MANAGER"

if [ "$MANAGER_ONLY" -eq 1 ]; then
    install -m 0755 "$MANAGER" /usr/local/bin/bakaimg
    printf '%s\n' 'bakaimg管理文件已更新。运行 sudo bakaimg 打开管理菜单。'
    exit 0
fi

cd "$INSTALL_DIR"
exec "$MANAGER" install "$@"

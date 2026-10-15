#!/bin/sh
set -eu

REPO_URL="${BAKAIMG_REPO_URL:-https://github.com/saubaka/bakaimg.git}"
BRANCH="${BAKAIMG_BRANCH:-main}"
INSTALL_DIR="${BAKAIMG_INSTALL_DIR:-/opt/bakaimg/current}"
MANAGER_ONLY=0

usage() {
    cat <<'EOF'
bakaimg macOS 部署脚本

用法：
  sudo sh deploy-macos.sh [选项] [域名 源站证书PEM 私钥PEM]

选项：
  --repo URL       Git仓库，默认 https://github.com/saubaka/bakaimg.git
  --branch NAME    分支，默认 main
  --dir PATH       安装目录，默认 /opt/bakaimg/current
  --manager-only   只更新系统管理命令
  -h, --help       显示帮助
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo) [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --repo 参数。' >&2; exit 2; }; REPO_URL=$2; shift 2 ;;
        --branch) [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --branch 参数。' >&2; exit 2; }; BRANCH=$2; shift 2 ;;
        --dir) [ "$#" -ge 2 ] || { printf '%s\n' '缺少 --dir 参数。' >&2; exit 2; }; INSTALL_DIR=$2; shift 2 ;;
        --manager-only) MANAGER_ONLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) printf '未知选项：%s\n' "$1" >&2; usage >&2; exit 2 ;;
        *) break ;;
    esac
done

[ "$(uname -s)" = "Darwin" ] || { printf '%s\n' '此脚本只适用于macOS。' >&2; exit 1; }
case "$(uname -m)" in arm64|x86_64) ;; *) printf '%s\n' '仅支持Apple芯片或Intel Mac。' >&2; exit 1 ;; esac
[ "$(id -u)" -eq 0 ] || { printf '%s\n' '请使用 sudo 运行此脚本。' >&2; exit 1; }
case "$INSTALL_DIR" in /*) ;; *) printf '%s\n' '安装目录必须是绝对路径。' >&2; exit 1 ;; esac
[ "$INSTALL_DIR" != "/" ] || { printf '%s\n' '安装目录不能是根目录。' >&2; exit 1; }

RUN_USER="${BAKAIMG_RUN_USER:-${SUDO_USER:-}}"
[ -n "$RUN_USER" ] && [ "$RUN_USER" != root ] || { printf '%s\n' '请从普通管理员账号使用 sudo 运行。' >&2; exit 1; }

if [ -x /opt/homebrew/bin/brew ]; then BREW=/opt/homebrew/bin/brew
elif [ -x /usr/local/bin/brew ]; then BREW=/usr/local/bin/brew
else
    printf '%s\n' '未找到Homebrew。请先从 https://brew.sh 安装Homebrew，再重新运行。' >&2
    exit 1
fi

/usr/bin/sudo -H -u "$RUN_USER" "$BREW" list git >/dev/null 2>&1 || /usr/bin/sudo -H -u "$RUN_USER" "$BREW" install git
GIT="$(/usr/bin/sudo -H -u "$RUN_USER" "$BREW" --prefix git)/bin/git"
[ -x "$GIT" ] || GIT=/usr/bin/git

if [ -d "$INSTALL_DIR/.git" ]; then
    [ -z "$(/usr/bin/sudo -H -u "$RUN_USER" "$GIT" -C "$INSTALL_DIR" status --porcelain)" ] || {
        printf '%s\n' '安装目录存在未提交修改，为避免覆盖已停止更新。' >&2
        exit 1
    }
    /usr/bin/sudo -H -u "$RUN_USER" "$GIT" -C "$INSTALL_DIR" fetch --prune origin "$BRANCH"
    /usr/bin/sudo -H -u "$RUN_USER" "$GIT" -C "$INSTALL_DIR" merge --ff-only "origin/$BRANCH"
elif [ -e "$INSTALL_DIR" ]; then
    printf '安装目录已存在但不是Git仓库：%s\n' "$INSTALL_DIR" >&2
    exit 1
else
    /bin/mkdir -p "$(/usr/bin/dirname "$INSTALL_DIR")"
    /usr/sbin/chown "$RUN_USER":staff "$(/usr/bin/dirname "$INSTALL_DIR")"
    /usr/bin/sudo -H -u "$RUN_USER" "$GIT" clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
fi

MANAGER="$INSTALL_DIR/bakaimg-macos"
[ -f "$MANAGER" ] || { printf '仓库中缺少macOS管理脚本：%s\n' "$MANAGER" >&2; exit 1; }
/bin/chmod 0755 "$MANAGER"
/bin/mkdir -p /usr/local/bin
/usr/bin/install -m 0755 "$MANAGER" /usr/local/bin/bakaimg
/usr/bin/install -m 0755 "$MANAGER" /usr/local/bin/bakaimg-macos

if [ "$MANAGER_ONLY" -eq 1 ]; then
    printf '%s\n' 'macOS管理命令已更新。运行 sudo bakaimg 打开管理菜单。'
    exit 0
fi

BAKAIMG_PROJECT_ROOT="$INSTALL_DIR" BAKAIMG_RUN_USER="$RUN_USER" exec /usr/local/bin/bakaimg install "$@"

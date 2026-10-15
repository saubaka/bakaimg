#!/bin/sh
# 双击即可在“终端”中打开 baka图床 管理面板。
cd "$(dirname "$0")" || exit 1
exec /bin/sh ./bakaimg-macos "$@"

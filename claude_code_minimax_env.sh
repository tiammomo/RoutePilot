#!/bin/bash

set -euo pipefail

# ========================
#       基础配置
# ========================
SCRIPT_NAME=$(basename "$0")
NODE_MIN_VERSION=20
NODE_INSTALL_VERSION=22
NVM_VERSION="v0.40.3"
CLAUDE_PACKAGE="@anthropic-ai/claude-code"
CONFIG_DIR="$HOME/.claude"
CONFIG_FILE="$CONFIG_DIR/settings.json"
API_BASE_URL="https://api.minimaxi.com/anthropic"
MODEL_NAME="MiniMax-M2.7"
API_TIMEOUT_MS=3000000

# ========================
#       通用函数
# ========================

log_info() {
    echo "🔹 $*"
}

log_success() {
    echo "✅ $*"
}

log_error() {
    echo "❌ $*" >&2
}

ensure_dir_exists() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" || {
            log_error "创建目录失败：$dir"
            exit 1
        }
    fi
}

# ========================
#     Node.js 安装
# ========================

install_nodejs() {
    local platform=$(uname -s)

    case "$platform" in
        Linux|Darwin)
            log_info "正在为 $platform 安装 Node.js..."

            log_info "正在安装 nvm ($NVM_VERSION)..."
            curl -s https://raw.githubusercontent.com/nvm-sh/nvm/"$NVM_VERSION"/install.sh | bash

            log_info "正在加载 nvm 环境..."
            \. "$HOME/.nvm/nvm.sh"

            log_info "正在安装 Node.js $NODE_INSTALL_VERSION..."
            nvm install "$NODE_INSTALL_VERSION"

            node -v &>/dev/null || {
                log_error "Node.js 安装失败"
                exit 1
            }
            log_success "Node.js 已安装：$(node -v)"
            log_success "npm 版本：$(npm -v)"
            ;;
        *)
            log_error "暂不支持的平台：$platform"
            exit 1
            ;;
    esac
}

# ========================
#     Node.js 检查
# ========================

check_nodejs() {
    if command -v node &>/dev/null; then
        current_version=$(node -v | sed 's/v//')
        major_version=$(echo "$current_version" | cut -d. -f1)

        if [ "$major_version" -ge "$NODE_MIN_VERSION" ]; then
            log_success "Node.js 已安装：v$current_version"
            return 0
        else
            log_info "当前 Node.js v$current_version 低于 $NODE_MIN_VERSION，准备升级..."
            install_nodejs
        fi
    else
        log_info "未检测到 Node.js，准备安装..."
        install_nodejs
    fi
}

# ========================
#     Claude Code 安装
# ========================

install_claude_code() {
    if command -v claude &>/dev/null; then
        log_success "Claude Code 已安装：$(claude --version)"
    else
        log_info "正在安装 Claude Code..."
        npm install -g "$CLAUDE_PACKAGE" || {
            log_error "Claude Code 安装失败"
            exit 1
        }
        log_success "Claude Code 安装完成"
    fi
}

configure_claude_json(){
  node --eval '
      const os = require("os");
      const fs = require("fs");
      const path = require("path");

      const homeDir = os.homedir();
      const filePath = path.join(homeDir, ".claude.json");
      if (fs.existsSync(filePath)) {
          const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
          fs.writeFileSync(filePath, JSON.stringify({ ...content, hasCompletedOnboarding: true }, null, 2), "utf-8");
      } else {
          fs.writeFileSync(filePath, JSON.stringify({ hasCompletedOnboarding: true }, null, 2), "utf-8");
      }'
}

# ========================
#     MiniMax 配置
# ========================

configure_claude() {
    log_info "正在配置 Claude Code 直连 MiniMax..."
    read -s -p "🔑 请输入 MiniMax API Token: " api_key
    echo

    if [ -z "$api_key" ]; then
        log_error "API Token 不能为空，请重新运行脚本。"
        exit 1
    fi

    ensure_dir_exists "$CONFIG_DIR"

    # 写入 Claude Code 本机设置
    node --eval '
        const os = require("os");
        const fs = require("fs");
        const path = require("path");

        const homeDir = os.homedir();
        const filePath = path.join(homeDir, ".claude", "settings.json");
        const apiKey = "'"$api_key"'";

        const content = fs.existsSync(filePath)
            ? JSON.parse(fs.readFileSync(filePath, "utf-8"))
            : {};

        fs.writeFileSync(filePath, JSON.stringify({
            ...content,
            env: {
                ANTHROPIC_AUTH_TOKEN: apiKey,
                ANTHROPIC_BASE_URL: "'"$API_BASE_URL"'",
                API_TIMEOUT_MS: "'"$API_TIMEOUT_MS"'",
                CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
                ANTHROPIC_MODEL: "'"$MODEL_NAME"'",
                ANTHROPIC_SMALL_FAST_MODEL: "'"$MODEL_NAME"'",
                ANTHROPIC_DEFAULT_SONNET_MODEL: "'"$MODEL_NAME"'",
                ANTHROPIC_DEFAULT_OPUS_MODEL: "'"$MODEL_NAME"'",
                ANTHROPIC_DEFAULT_HAIKU_MODEL: "'"$MODEL_NAME"'"
            }
        }, null, 2), "utf-8");
    ' || {
        log_error "写入 settings.json 失败"
        exit 1
    }

    log_success "Claude Code 已配置为 MiniMax Anthropic-compatible 接口"
}

# ========================
#        Main
# ========================

main() {
    echo "🚀 开始执行 $SCRIPT_NAME"

    check_nodejs
    install_claude_code
    configure_claude_json
    configure_claude

    echo ""
    log_success "🎉 安装与配置完成"
    echo ""
    echo "🚀 现在可以通过以下命令验证 Claude Code："
    echo "   claude"
}

main "$@"

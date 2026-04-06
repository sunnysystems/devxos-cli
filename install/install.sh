#!/bin/sh
# DevXOS Installer — macOS, Linux, WSL
#
# Usage:
#   curl -fsSL https://devxos.ai/install.sh | sh
#   wget -qO- https://devxos.ai/install.sh | sh
#
# What it does:
#   1. Checks for Python 3.11+
#   2. Installs DevXOS via pipx (preferred) or pip
#   3. Verifies the `devxos` command is available
#
# Environment variables:
#   DEVXOS_INSTALL_METHOD=pip    Force pip instead of pipx
#   DEVXOS_BRANCH=main          Git branch to install from

set -e

REPO_HTTPS="https://github.com/sunnysystems/devxos-cli.git"

REPO_URL="git+${REPO_HTTPS}"
BRANCH="${DEVXOS_BRANCH:-main}"
MIN_PYTHON="3.11"

# --- Colors (disabled if not a terminal) ---
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BOLD='' NC=''
fi

info()  { printf "${GREEN}>>>${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}>>>${NC} %s\n" "$1"; }
error() { printf "${RED}>>>${NC} %s\n" "$1"; }
bold()  { printf "${BOLD}%s${NC}\n" "$1"; }

# --- Detect Python ---
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            if [ -n "$version" ]; then
                major=$(echo "$version" | cut -d. -f1)
                minor=$(echo "$version" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                    echo "$cmd"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# --- Detect OS ---
detect_os() {
    case "$(uname -s)" in
        Darwin*)  echo "macos" ;;
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        *)        echo "unknown" ;;
    esac
}

# --- Main ---
main() {
    bold "DevXOS Installer"
    echo ""

    OS=$(detect_os)
    info "Detected OS: $OS"

    # Check Python
    PYTHON=$(find_python) || {
        error "Python $MIN_PYTHON or later is required but not found."
        echo ""
        case "$OS" in
            macos) echo "  Install: brew install python@3.13" ;;
            linux|wsl) echo "  Install: sudo apt install python3 python3-pip python3-venv" ;;
        esac
        echo ""
        exit 1
    }

    PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    info "Python: $PYTHON ($PYTHON_VERSION)"

    # Check git
    if ! command -v git >/dev/null 2>&1; then
        error "Git is required but not found."
        exit 1
    fi
    info "Git: $(git --version | head -1)"

    # Choose install method
    METHOD="${DEVXOS_INSTALL_METHOD:-auto}"

    if [ "$METHOD" = "auto" ]; then
        if command -v pipx >/dev/null 2>&1; then
            METHOD="pipx"
        else
            METHOD="pip"
        fi
    fi

    echo ""

    case "$METHOD" in
        pipx)
            info "Installing via pipx (isolated environment)..."
            pipx install "${REPO_URL}@${BRANCH}" --python "$PYTHON" 2>&1 || {
                # If already installed, upgrade
                warn "Attempting upgrade..."
                pipx upgrade devxos 2>&1 || pipx install --force "${REPO_URL}@${BRANCH}" --python "$PYTHON" 2>&1
            }
            ;;
        pip)
            INSTALL_DIR="${DEVXOS_HOME:-$HOME/.devxos}"
            VENV_DIR="$INSTALL_DIR/venv"
            BIN_DIR="$INSTALL_DIR/bin"

            info "Installing to $INSTALL_DIR..."

            # Create dedicated venv
            mkdir -p "$INSTALL_DIR"
            "$PYTHON" -m venv "$VENV_DIR" 2>&1

            # Install into venv
            "$VENV_DIR/bin/pip" install "${REPO_URL}@${BRANCH}" 2>&1

            # Create bin wrapper
            mkdir -p "$BIN_DIR"
            cat > "$BIN_DIR/devxos" <<WRAPPER
#!/bin/sh
exec "$VENV_DIR/bin/devxos" "\$@"
WRAPPER
            chmod +x "$BIN_DIR/devxos"

            # Add to PATH if needed
            case ":$PATH:" in
                *":$BIN_DIR:"*) ;;
                *)
                    SHELL_RC=""
                    case "$SHELL" in
                        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
                        */bash) SHELL_RC="$HOME/.bashrc" ;;
                    esac

                    EXPORT_LINE="export PATH=\"$BIN_DIR:\$PATH\""

                    if [ -n "$SHELL_RC" ]; then
                        if ! grep -q "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
                            echo "" >> "$SHELL_RC"
                            echo "# DevXOS" >> "$SHELL_RC"
                            echo "$EXPORT_LINE" >> "$SHELL_RC"
                            info "Added to $SHELL_RC"
                        fi
                    else
                        warn "Add to your shell profile:"
                        echo ""
                        echo "  $EXPORT_LINE"
                        echo ""
                    fi

                    export PATH="$BIN_DIR:$PATH"
                    ;;
            esac
            ;;
    esac

    echo ""

    # Verify
    if command -v devxos >/dev/null 2>&1; then
        info "Installation successful!"
        echo ""
        bold "$(devxos --help 2>&1 | head -1 || echo 'DevXOS installed')"
        echo ""
        echo "  Analyze a repo:     devxos /path/to/repo"
        echo "  Analyze an org:     devxos --org /path/to/org"
        echo "  Install AI hook:    devxos hook install /path/to/repo"
        echo "  With trend:         devxos /path/to/repo --trend"
        echo ""
    else
        warn "devxos was installed but is not on PATH."
        warn "You may need to restart your shell or add the install location to PATH."
    fi

    # Optional: check for gh CLI
    if command -v gh >/dev/null 2>&1; then
        info "GitHub CLI detected — PR analysis will be available."
    else
        warn "GitHub CLI (gh) not found — PR analysis will be skipped."
        echo "  Install: https://cli.github.com/"
    fi
}

main "$@"

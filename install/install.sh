#!/bin/sh
# DevXOS Installer — macOS, Linux, WSL
#
# Usage:
#   curl -fsSL https://devxos.ai/install.sh | sh
#   wget -qO- https://devxos.ai/install.sh | sh
#
# Environment variables:
#   DEVXOS_HOME=~/.devxos           Install location (default: ~/.devxos)
#   DEVXOS_INSTALL_METHOD=pip       Force pip instead of pipx
#   DEVXOS_BRANCH=main              Git branch to install from
#   DEVXOS_YES=1                    Skip confirmation prompt

set -e

REPO_URL="git+https://github.com/sunnysystems/devxos-cli.git"
BRANCH="${DEVXOS_BRANCH:-main}"
MIN_PYTHON="3.11"
INSTALL_DIR="${DEVXOS_HOME:-$HOME/.devxos}"

# --- Colors (disabled if not a terminal) ---
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    RED='\033[0;31m'
    DIM='\033[2m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' DIM='' BOLD='' NC=''
fi

info()  { printf "${GREEN}>>>${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}>>>${NC} %s\n" "$1"; }
error() { printf "${RED}>>>${NC} %s\n" "$1"; }
bold()  { printf "${BOLD}%s${NC}\n" "$1"; }
dim()   { printf "${DIM}%s${NC}\n" "$1"; }

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

# --- Detect shell rc file ---
detect_shell_rc() {
    # Prefer the user's current shell, fall back to common files
    case "$SHELL" in
        */zsh)  echo "$HOME/.zshrc" ;;
        */bash)
            # macOS uses login shells (.bash_profile), Linux uses .bashrc
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        *)
            # Check which files exist, in priority order
            if [ -f "$HOME/.zshrc" ]; then
                echo "$HOME/.zshrc"
            elif [ -f "$HOME/.bash_profile" ]; then
                echo "$HOME/.bash_profile"
            elif [ -f "$HOME/.bashrc" ]; then
                echo "$HOME/.bashrc"
            elif [ -f "$HOME/.profile" ]; then
                echo "$HOME/.profile"
            else
                echo ""
            fi
            ;;
    esac
}

# --- Add to PATH ---
ensure_path() {
    BIN_DIR="$1"

    # Already on PATH?
    case ":$PATH:" in
        *":$BIN_DIR:"*) return 0 ;;
    esac

    SHELL_RC=$(detect_shell_rc)
    EXPORT_LINE="export PATH=\"$BIN_DIR:\$PATH\""

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
            printf "\n# DevXOS\n%s\n" "$EXPORT_LINE" >> "$SHELL_RC"
            info "Added to PATH via $SHELL_RC"
        else
            dim "  PATH already configured in $SHELL_RC"
        fi
    else
        warn "Could not detect shell profile. Add this to your shell config:"
        echo ""
        echo "  $EXPORT_LINE"
        echo ""
    fi

    # Make available in current session
    export PATH="$BIN_DIR:$PATH"
}

# --- Main ---
main() {
    bold "DevXOS Installer"
    echo ""

    OS=$(detect_os)

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

    # Check git
    if ! command -v git >/dev/null 2>&1; then
        error "Git is required but not found."
        exit 1
    fi

    # Choose install method
    METHOD="${DEVXOS_INSTALL_METHOD:-auto}"
    if [ "$METHOD" = "auto" ]; then
        if command -v pipx >/dev/null 2>&1; then
            METHOD="pipx"
        else
            METHOD="pip"
        fi
    fi

    # --- Show plan and ask for confirmation ---
    echo "  This will install DevXOS CLI on your machine."
    echo ""
    echo "  ${BOLD}What will happen:${NC}"
    echo ""
    if [ "$METHOD" = "pipx" ]; then
        echo "    1. Install DevXOS via pipx (isolated environment)"
        echo "       Location: managed by pipx (~/.local/pipx/venvs/devxos)"
        echo "       Binary:   ~/.local/bin/devxos"
    else
        echo "    1. Create a Python virtual environment"
        echo "       Location: ${INSTALL_DIR}/venv"
        echo ""
        echo "    2. Install DevXOS into that venv"
        echo "       Binary:   ${INSTALL_DIR}/bin/devxos"
        echo ""
        echo "    3. Add ${INSTALL_DIR}/bin to your PATH"
        SHELL_RC=$(detect_shell_rc)
        if [ -n "$SHELL_RC" ]; then
            echo "       Via:      $SHELL_RC"
        fi
    fi
    echo ""
    dim "  Python: $PYTHON ($PYTHON_VERSION) | Git: $(git --version | cut -d' ' -f3) | OS: $OS"
    echo ""

    # Ask for confirmation (skip with DEVXOS_YES=1 or -y flag)
    if [ "${DEVXOS_YES}" != "1" ] && [ "$1" != "-y" ] && [ "$1" != "--yes" ]; then
        printf "  Proceed with installation? [Y/n] "
        # Read from /dev/tty so it works even when piped (curl | sh)
        read -r REPLY < /dev/tty
        case "$REPLY" in
            [nN]*) echo "  Installation cancelled."; exit 0 ;;
        esac
    fi

    echo ""

    # --- Install ---
    case "$METHOD" in
        pipx)
            info "Installing via pipx..."
            pipx install "${REPO_URL}@${BRANCH}" --python "$PYTHON" 2>&1 || {
                warn "Attempting upgrade..."
                pipx upgrade devxos 2>&1 || pipx install --force "${REPO_URL}@${BRANCH}" --python "$PYTHON" 2>&1
            }
            ensure_path "$HOME/.local/bin"
            ;;
        pip)
            VENV_DIR="$INSTALL_DIR/venv"
            BIN_DIR="$INSTALL_DIR/bin"

            info "Creating virtual environment..."
            mkdir -p "$INSTALL_DIR"
            "$PYTHON" -m venv "$VENV_DIR" 2>&1

            info "Installing DevXOS..."
            "$VENV_DIR/bin/pip" install --quiet "${REPO_URL}@${BRANCH}" 2>&1

            # Create bin wrapper
            mkdir -p "$BIN_DIR"
            cat > "$BIN_DIR/devxos" <<WRAPPER
#!/bin/sh
exec "$VENV_DIR/bin/devxos" "\$@"
WRAPPER
            chmod +x "$BIN_DIR/devxos"

            ensure_path "$BIN_DIR"
            ;;
    esac

    echo ""

    # --- Verify ---
    if command -v devxos >/dev/null 2>&1; then
        info "Installation successful!"
        echo ""
        echo "  Get started:"
        echo ""
        echo "    devxos login                          Connect to DevXOS platform"
        echo "    devxos /path/to/repo                  Analyze a repository"
        echo "    devxos /path/to/repo --push           Analyze and push to platform"
        echo "    devxos hook install /path/to/repo     Install AI commit tracking"
        echo "    devxos uninstall                      Remove DevXOS from your machine"
        echo ""
        dim "  Restart your terminal or run: source $(detect_shell_rc)"
        echo ""
    else
        warn "DevXOS was installed but is not yet on PATH in this session."
        warn "Restart your terminal, then run: devxos --help"
    fi

    # Optional: check for gh CLI
    if ! command -v gh >/dev/null 2>&1; then
        dim "  Tip: Install GitHub CLI (gh) for PR analysis — https://cli.github.com/"
    fi
}

main "$@"

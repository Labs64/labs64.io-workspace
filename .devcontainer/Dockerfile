FROM mcr.microsoft.com/devcontainers/base:jammy

# Pre-create persistent tool directories with the correct owner. Docker's
# initial volume copy-up then preserves ownership, while the named volumes keep
# VS Code remote state and tool logins across container rebuilds.
RUN mkdir -p /home/vscode/.vscode-server /home/vscode/.vscode-server-insiders \
        /home/vscode/.claude /home/vscode/.codex \
    && chown -R vscode:vscode /home/vscode/.vscode-server \
        /home/vscode/.vscode-server-insiders /home/vscode/.claude /home/vscode/.codex

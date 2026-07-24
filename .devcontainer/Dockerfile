FROM mcr.microsoft.com/devcontainers/base:jammy

# Pre-create the VS Code Server directory owned by vscode so that when the
# named volume mount (see devcontainer.json "mounts") is first attached,
# Docker's volume copy-up preserves this ownership instead of defaulting to
# root — otherwise the VS Code Server install fails with "Permission denied"
# before postCreateCommand ever runs.
RUN mkdir -p /home/vscode/.vscode-server /home/vscode/.vscode-server-insiders \
    && chown -R vscode:vscode /home/vscode/.vscode-server /home/vscode/.vscode-server-insiders

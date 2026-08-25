FROM maven:3.9-eclipse-temurin-25

# Install Docker CLI for Docker-outside-of-Docker (DooD)
RUN apt-get update && apt-get install -y docker.io curl bash && rm -rf /var/lib/apt/lists/*

ARG USER_ID=1000
ARG GROUP_ID=1000

# Match the invoking developer so bind-mounted build artifacts remain writable
# from the devcontainer. The Maven cache directory is created in the image so a
# new named volume inherits the same ownership on first use.
RUN existing_user="$(getent passwd "${USER_ID}" | cut -d: -f1 || true)" \
    && existing_group="$(getent group "${GROUP_ID}" | cut -d: -f1 || true)" \
    && if [ -z "${existing_group}" ]; then \
        groupadd --gid "${GROUP_ID}" builder; \
    elif [ "${existing_group}" != builder ]; then \
        groupmod --new-name builder "${existing_group}"; \
    fi \
    && if [ -n "${existing_user}" ]; then \
        usermod --login builder --home /home/builder --move-home --shell /bin/bash "${existing_user}"; \
    else \
        useradd --uid "${USER_ID}" --gid "${GROUP_ID}" --create-home --shell /bin/bash builder; \
    fi \
    && usermod --gid "${GROUP_ID}" builder \
    && mkdir -p /home/builder/.m2 /workspaces \
    && chown -R "${USER_ID}:${GROUP_ID}" /home/builder /workspaces

ENV HOME=/home/builder
ENV MAVEN_CONFIG=/home/builder/.m2

USER builder

FROM maven:3.9-eclipse-temurin-25

# Install Docker CLI for Docker-outside-of-Docker (DooD)
RUN apt-get update && apt-get install -y docker.io curl bash && rm -rf /var/lib/apt/lists/*

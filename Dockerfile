FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Installa strumenti per la build dei pacchetti Python .deb
RUN apt-get update && apt-get install -y \
    build-essential \
    devscripts \
    debhelper \
    dh-python \
    python3 \
    python3-all \
    python3-setuptools \
    python3-yaml \
    python3-pip \
    fakeroot \
    lintian \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

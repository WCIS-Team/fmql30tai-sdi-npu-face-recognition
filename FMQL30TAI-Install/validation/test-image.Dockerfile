FROM scratch
ADD ubuntu-base.tar.gz /
ENV DEBIAN_FRONTEND=noninteractive
RUN printf 'deb http://repo.huaweicloud.com/ubuntu focal main universe\ndeb http://repo.huaweicloud.com/ubuntu focal-updates main universe\ndeb http://repo.huaweicloud.com/ubuntu focal-security main universe\n' > /etc/apt/sources.list && apt-get update && apt-get install -y --no-install-recommends ca-certificates cmake make ninja-build gcc-aarch64-linux-gnu g++-aarch64-linux-gnu python3 python3-distutils file && rm -rf /var/lib/apt/lists/*
COPY sdk/ /tmp/wcis-sdk/
RUN for p in /tmp/wcis-sdk/*.deb; do dpkg-deb -x "$p" /; done && rm -rf /tmp/wcis-sdk
RUN dpkg --add-architecture arm64 && printf 'deb [arch=amd64] http://repo.huaweicloud.com/ubuntu focal main universe\ndeb [arch=amd64] http://repo.huaweicloud.com/ubuntu focal-updates main universe\ndeb [arch=amd64] http://repo.huaweicloud.com/ubuntu focal-security main universe\ndeb [arch=arm64] http://repo.huaweicloud.com/ubuntu-ports focal main universe\ndeb [arch=arm64] http://repo.huaweicloud.com/ubuntu-ports focal-updates main universe\ndeb [arch=arm64] http://repo.huaweicloud.com/ubuntu-ports focal-security main universe\n' > /etc/apt/sources.list && apt-get update && apt-get install -y --no-install-recommends zlib1g-dev:arm64 && rm -rf /var/lib/apt/lists/*
WORKDIR /work

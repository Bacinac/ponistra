# Android APK builder: JDK, Android SDK and Gradle, used only by android/build.sh.
# Never a compose service: an installation would otherwise pull a multi-gigabyte
# toolchain it never needs.
FROM eclipse-temurin:25-jdk-noble@sha256:95e350ad1eb738f943e141640f7e3d797e483359a3b33c3864255bfd1ad71f8a

ENV ANDROID_HOME=/opt/android-sdk \
    PATH=/opt/gradle/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends unzip wget git \
    && rm -rf /var/lib/apt/lists/*

# Gradle baked in rather than a wrapper, which would download it again into every
# fresh container.
ARG GRADLE_VERSION=9.7.1
RUN wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt && mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle \
    && rm /tmp/gradle.zip

ARG CMDLINE_TOOLS=16111833
ARG PLATFORM
ARG BUILD_TOOLS
RUN mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && wget -q "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" -O /tmp/ct.zip \
    && unzip -q /tmp/ct.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/ct.zip \
    && yes | sdkmanager --licenses >/dev/null \
    && sdkmanager "platform-tools" "platforms;${PLATFORM}" "build-tools;${BUILD_TOOLS}" >/dev/null \
    && chmod -R a+rX "$ANDROID_HOME"

WORKDIR /project

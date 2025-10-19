FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN rm -rf /var/lib/apt/lists/*

RUN apt update && apt install -y \
    python3-pip python3-setuptools python3-dev \
    build-essential git zip unzip openjdk-11-jdk \
    libncurses5 libffi-dev libssl-dev libsqlite3-dev \
    libjpeg-dev libfreetype6-dev libgl1-mesa-dev \
    libgles2-mesa-dev libpng-dev libz-dev \
    libavcodec-dev libavformat-dev libswscale-dev \
    libbz2-dev libreadline-dev libgdbm-dev \
    liblzma-dev libxml2-dev libxslt1-dev \
    libegl1-mesa libmtdev-dev libudev-dev \
    libusb-1.0-0 libffi-dev libsdl2-dev \
    libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libtiff-dev libx11-dev \
    libxext-dev libxrender-dev libxrandr-dev \
    libxcursor-dev libxfixes-dev libxinerama-dev \
    libxi-dev libsm-dev libexpat1-dev \
    && apt clean

RUN pip3 install --upgrade pip
RUN pip3 install buildozer cython

WORKDIR /app
COPY . /app

RUN buildozer init
CMD ["buildozer", "android", "debug"]
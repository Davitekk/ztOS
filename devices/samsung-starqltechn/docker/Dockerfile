# A Linux build host for the Galaxy S9 (Snapdragon) port, for computers that
# are not Arch Linux (Windows with Docker Desktop, macOS, other distributions).
# Run it privileged: the installer needs user namespaces, and aarch64 programs
# run through the host kernel's qemu-user binfmt handler (registered once per
# boot of Docker's VM by devices/samsung-starqltechn/docker/run.sh).
FROM archlinux:latest

# (qt6-base: its uic compiles the SDK apps' .ui files on this side;
# ccache: kernel rebuilds in minutes, kernel/build-kernel.sh)
RUN pacman -Syu --noconfirm --needed \
	base-devel git python python-pip bc bison flex cpio kmod openssl pahole perl \
	clang llvm lld dtc uboot-tools android-tools e2fsprogs dosfstools mtools \
	libarchive util-linux zstd gzip xz curl wget rsync \
	qemu-user-static qemu-user-static-binfmt \
	aarch64-linux-gnu-gcc swig python-setuptools qt6-base ccache \
	&& pacman -Scc --noconfirm

# the installer runs as an ordinary user with a subordinate ID range
RUN useradd -m -u 1000 builder && echo 'builder:100000:65536' >> /etc/subuid \
	&& echo 'builder:100000:65536' >> /etc/subgid \
	&& echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder

WORKDIR /build

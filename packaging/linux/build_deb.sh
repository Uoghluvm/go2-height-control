#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-amd64}"
BUILD_DIR="$ROOT/build/deb"
PKG_DIR="$BUILD_DIR/go2-height-control_${VERSION}_${ARCH}"
DIST_DIR="$ROOT/dist/go2-height-control"
OUT_DIR="$ROOT/dist/packages"

cd "$ROOT"

mkdir -p "$BUILD_DIR"
python3 -m venv "$BUILD_DIR/venv"
"$BUILD_DIR/venv/bin/python" -m pip install --upgrade pip
"$BUILD_DIR/venv/bin/python" -m pip install -r "$ROOT/packaging/requirements-package.txt"
"$BUILD_DIR/venv/bin/pyinstaller" --clean --noconfirm "$ROOT/packaging/pyinstaller/go2_height_control.spec"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/go2-height-control"
mkdir -p "$PKG_DIR/usr/bin"

cp -a "$DIST_DIR/." "$PKG_DIR/opt/go2-height-control/"

cat > "$PKG_DIR/usr/bin/go2-height-control" <<'LAUNCHER'
#!/usr/bin/env bash
exec /opt/go2-height-control/go2-height-control "$@"
LAUNCHER
chmod 0755 "$PKG_DIR/usr/bin/go2-height-control"

cat > "$PKG_DIR/DEBIAN/control" <<CONTROL
Package: go2-height-control
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Go2 Height Control <noreply@example.com>
Depends: libc6
Description: Unitree Go2 height control web console
 Local web console for Unitree Go2 height control, keyboard remote control,
 front jump action, and WebRTC camera preview.
CONTROL

mkdir -p "$OUT_DIR"
dpkg-deb --build "$PKG_DIR" "$OUT_DIR/go2-height-control_${VERSION}_${ARCH}.deb"
echo "Built: $OUT_DIR/go2-height-control_${VERSION}_${ARCH}.deb"

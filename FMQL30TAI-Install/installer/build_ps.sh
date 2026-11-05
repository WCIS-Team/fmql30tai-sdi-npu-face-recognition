#!/bin/sh
set -eu
export TMPDIR=/work/tmp XDG_CACHE_HOME=/work/cache
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" /work/bin
command -v cmake
/usr/bin/aarch64-linux-gnu-g++ --version
test -f /usr/cmake/icraft-zg330backend-config.cmake
test -d /ModelzooDeps/aarch64/Static
cmake -S /source/ps_app -B /work/build-owner \
  -DCMAKE_TOOLCHAIN_FILE=/scripts/aarch64.cmake \
  -DCMAKE_PREFIX_PATH=/usr/cmake \
  -DMODELZOO_STATIC=/ModelzooDeps/aarch64/Static \
  -DMODELZOO_DYNAMIC=/ModelzooDeps/aarch64/Dynamic \
  -DWCIS_BUILD_REFERENCE=OFF -DWCIS_BUILD_CAMERA_OWNER=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /work/build-owner --target wcis_camera_owner -- -j2
cmake -S /source/npu_photo -B /work/build-npu \
  -DCMAKE_TOOLCHAIN_FILE=/scripts/aarch64.cmake \
  -DCMAKE_PREFIX_PATH=/usr/cmake -DCMAKE_BUILD_TYPE=Release
cmake --build /work/build-npu --target wcis_face_cached wcis_face_pl_retained wcis_face_pad wcis_face_npu -- -j2
cp /work/build-owner/wcis_camera_owner /work/bin/
for name in wcis_face_cached wcis_face_pl_retained wcis_face_pad wcis_face_npu; do
  cp "/work/build-npu/$name" /work/bin/
done
sha256sum /work/bin/wcis_*

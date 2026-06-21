#!/bin/bash
# Build ParaSCIP -- the MPI-parallel SCIP (UG framework) -- from SCIPOptSuite,
# for the 2-node distributed solve. conda's scip/pyscipopt are single-node only;
# this is the piece that lets branch-and-bound span both nodes over MPI.
#
# Run on the build/login node (uan1), where heavy compiles are allowed here:
#     bash scripts/build_parascip.sh
# or inside an interactive job for more cores:
#     qsub -I -l select=1:ncpus=32 -l walltime=02:00:00
#     cd ~/5g_allocation && JOBS=32 bash scripts/build_parascip.sh
#
# On success it installs the parallel binary as $HOME/scip_install/bin/fscip
# and prints the FSCIP_BIN line to add to your shell (pbs/env.sh picks it up).
#
# The Cray wrappers cc/CC embed MPI when cray-mpich is loaded, so building UG
# with CC yields the distributed (MPI) binary -- no separate -DMPI flag needed.

set -uo pipefail

VERSION="${SCIP_VERSION:-9.1.0}"
PREFIX="${SCIP_PREFIX:-$HOME/scip_install}"
JOBS="${JOBS:-16}"
SRC="$HOME/scipoptsuite-$VERSION"

echo "================ MODULES / COMPILERS ================"
module load PrgEnv-gnu/8.6.0 2>/dev/null || true
module load cray-mpich/8.1.32 2>/dev/null || true
module load cmake 2>/dev/null || true
echo "cc   -> $(command -v cc || echo MISSING)"
echo "CC   -> $(command -v CC || echo MISSING)"
echo "cmake-> $(command -v cmake || echo MISSING)"

echo "================ FETCH SOURCE ================"
cd "$HOME"
if [ ! -d "$SRC" ]; then
    wget -q "https://scipopt.org/download/release/scipoptsuite-$VERSION.tgz"
    tar xzf "scipoptsuite-$VERSION.tgz"
fi
echo "source: $SRC"

echo "================ CMAKE CONFIGURE (SoPlex + SCIP + UG) ================"
cd "$SRC"
rm -rf build && mkdir build && cd build
if ! cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=cc \
    -DCMAKE_CXX_COMPILER=CC \
    -DUG=ON \
    -DZIMPL=OFF -DIPOPT=OFF -DPAPILO=OFF -DREADLINE=OFF \
    -DCMAKE_INSTALL_PREFIX="$PREFIX"; then
    echo "ERROR: cmake configure failed -- paste the output above and I'll help."
    exit 1
fi

echo "================ BUILD (make -j$JOBS) ================"
if ! make -j"$JOBS"; then
    echo "ERROR: build failed -- paste the last ~30 lines and I'll help."
    exit 1
fi
make install || true   # UG binaries aren't always installed; we locate them next

echo "================ LOCATE PARALLEL BINARY ================"
# UG names the binary fscip (FiberSCIP) or parascip (ParaSCIP), sometimes with a
# long arch/comm suffix -- find whatever was produced.
mapfile -t FOUND < <(find "$SRC/build" "$SRC/ug" "$PREFIX" -type f \
    \( -name 'fscip*' -o -name 'parascip*' \) -perm -u+x 2>/dev/null)

if [ "${#FOUND[@]}" -eq 0 ]; then
    cat <<EOF

No fscip/parascip binary was produced -- '-DUG=ON' may not enable UG for this
SCIPOptSuite version. Fallback via the UG Makefile (MPI):

  cd $SRC
  make LPS=spx ZIMPL=false READLINE=false GMP=false -j$JOBS      # scip+soplex libs
  cd ug && make LPS=spx COMM=mpi SCIPDIR=../scip SOPLEXDIR=../soplex ZIMPL=false -j$JOBS
  ls $SRC/ug/bin/                                                # find the binary

See $SRC/ug/INSTALL for exact targets. Paste any error and I'll iterate with you.
EOF
    exit 2
fi

mkdir -p "$PREFIX/bin"
BIN="${FOUND[0]}"
cp -v "$BIN" "$PREFIX/bin/fscip"

echo
echo "================ SUCCESS ================"
echo "Built parallel binary: $BIN"
echo "Installed as:          $PREFIX/bin/fscip"
echo
echo "Add this to your shell (pbs/env.sh will then pick it up automatically):"
echo "    export FSCIP_BIN=$PREFIX/bin/fscip"
echo
echo "Quick check:"
echo "    \$PREFIX/bin/fscip --version   ||   $PREFIX/bin/fscip --help | head"

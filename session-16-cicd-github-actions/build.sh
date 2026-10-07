#!/usr/bin/env bash
# Build step of the pipeline: a wheel + sdist and a build-info file.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf build dist
python -m build --outdir dist . > /dev/null
mkdir -p build
cat > build/build-info.txt <<INFO
application : cgpa-calculator $(python -c 'import app; print(app.__version__)')
commit      : ${GITHUB_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}
built by    : ${GITHUB_ACTOR:-$(whoami)} on $(uname -n)
built at    : $(date -u +%Y-%m-%dT%H:%M:%SZ)
python      : $(python --version 2>&1)
INFO
cp dist/* build/
echo "Build artifacts:"
ls -la build

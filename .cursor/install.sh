#!/usr/bin/env bash
set -euo pipefail

# Cloud Agent dev-environment setup for the "viewer" PHP image proxy.
#
# The Cloud Agent egress policy blocks the Ubuntu apt mirrors
# (archive.ubuntu.com / security.ubuntu.com return HTTP 403), so `apt-get
# install php-cli` cannot be used here. Instead we install a self-contained,
# statically linked PHP CLI binary published in the NativePHP/php-bin GitHub
# repository, which is reachable because github.com / api.github.com are on the
# egress allowlist. The binary is fetched through the GitHub git-blobs API
# (base64) rather than raw.githubusercontent.com, which is not allowlisted.

PHP_BIN_REPO="NativePHP/php-bin"
PHP_BIN_TAG="1.2.0"
PHP_SERIES="8.3"
INSTALL_PATH="/usr/local/bin/php"

if command -v php >/dev/null 2>&1 && php -v >/dev/null 2>&1; then
  echo "php already installed: $(php -v | head -n1)"
  exit 0
fi

case "$(uname -m)" in
  x86_64 | amd64) ARCH="x64" ;;
  aarch64 | arm64) ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

ASSET_PATH="bin/linux/${ARCH}/php-${PHP_SERIES}.zip"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Resolving ${ASSET_PATH} from ${PHP_BIN_REPO}@${PHP_BIN_TAG} ..."
BLOB_SHA="$(curl -fsSL "https://api.github.com/repos/${PHP_BIN_REPO}/git/trees/${PHP_BIN_TAG}?recursive=1" |
  python3 -c "import sys,json; t=json.load(sys.stdin)['tree']; print(next(x['sha'] for x in t if x['path']=='${ASSET_PATH}'))")"

echo "Downloading static PHP ${PHP_SERIES} (${ARCH}) blob ${BLOB_SHA} ..."
curl -fsSL "https://api.github.com/repos/${PHP_BIN_REPO}/git/blobs/${BLOB_SHA}" |
  python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('${TMP_DIR}/php.zip','wb').write(base64.b64decode(d['content']))"

python3 -c "import zipfile; zipfile.ZipFile('${TMP_DIR}/php.zip').extractall('${TMP_DIR}')"
sudo install -m 0755 "${TMP_DIR}/php" "${INSTALL_PATH}"

echo "Installed: $(php -v | head -n1)"

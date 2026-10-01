#!/bin/sh
set -eu

version=1.5.2
case "$(uname -s)" in
  Darwin) lobby_os=darwin ;;
  Linux) lobby_os=linux ;;
  *) printf '%s\n' 'Use install.ps1 on Windows.' >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64) lobby_arch=x64 ;;
  arm64|aarch64) lobby_arch=arm64 ;;
  *) printf '%s\n' 'This processor is not supported by the installer.' >&2; exit 1 ;;
esac
asset="runlobby-$version-$lobby_os-$lobby_arch.tar.gz"
base="https://github.com/blankmeta/runlobby/releases/download/v$version"
lobby_tmp=$(mktemp -d)
trap 'rm -rf "$lobby_tmp"' EXIT HUP INT TERM
curl -fLsS --retry 3 "$base/$asset" -o "$lobby_tmp/$asset"
curl -fLsS --retry 3 "$base/$asset.sha256" -o "$lobby_tmp/checksum"
expected=$(cut -d ' ' -f 1 "$lobby_tmp/checksum")
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$lobby_tmp/$asset" | cut -d ' ' -f 1)
else
  actual=$(shasum -a 256 "$lobby_tmp/$asset" | cut -d ' ' -f 1)
fi
[ "$expected" = "$actual" ] || { printf '%s\n' 'Checksum mismatch. Nothing was installed.' >&2; exit 1; }
tar -xzf "$lobby_tmp/$asset" -C "$lobby_tmp"
lobby_root="${XDG_DATA_HOME:-$HOME/.local/share}/runlobby/$version"
lobby_bin="$HOME/.local/bin"
mkdir -p "$(dirname "$lobby_root")" "$lobby_bin"
# Keep old versions intact so open sessions and their status hooks keep working.
if [ ! -d "$lobby_root" ]; then mv "$lobby_tmp/runlobby" "$lobby_root"; fi
for name in runlobby rlb codex-lobby cxl codex-switch codex-vpn codex-proxy; do
  if [ -e "$lobby_bin/$name" ] && [ ! -L "$lobby_bin/$name" ]; then
    printf 'Existing %s was kept. Launch: %s/rlb\n' "$lobby_bin/$name" "$lobby_root"
  else
    ln -sfn "$lobby_root/$name" "$lobby_bin/$name"
  fi
done
case ":$PATH:" in
  *":$lobby_bin:"*) printf '%s\n' 'Installed. Run: rlb' ;;
  *)
    case "${SHELL:-}" in
      */zsh) lobby_profile="$HOME/.zshrc" ;;
      */bash) lobby_profile="$HOME/.bashrc" ;;
      *) lobby_profile="$HOME/.profile" ;;
    esac
    if ! grep -Eq '# (RunLobby|Codex Lobby) PATH' "$lobby_profile" 2>/dev/null; then
      printf '\n%s\n%s\n' '# RunLobby PATH' 'export PATH="$HOME/.local/bin:$PATH"' >> "$lobby_profile"
    fi
    printf 'Installed. Open a new terminal and run rlb. Start now: %s/rlb\n' "$lobby_root"
    ;;
esac
"$lobby_root/rlb" --version

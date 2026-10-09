# Source this to load the gateway settings into the current shell:
#
#   source scripts/env.sh            # reads .env.op.local
#   ENV_FILE=other source scripts/env.sh
#
# Plain values are exported as-is. op:// references are resolved with the
# 1Password CLI, so the key only ever lives in this shell's environment —
# never in a file. A variable that is already set in the environment is kept
# and op is not called for it: that is how the Windows launcher
# (scripts/run_full_windows.ps1) hands LLM_API_KEY in through WSLENV, because
# the 1Password app does not authorize op.exe when it is called from inside
# WSL (see docs/setup-windows.md). A read that fails or comes back empty is
# an error — the first Windows run exported an empty key and got 401s.

_bf_env_file="${ENV_FILE:-.env.op.local}"
if [ ! -f "$_bf_env_file" ]; then
  echo "env.sh: $_bf_env_file not found. Copy .env.op to .env.op.local and put your item name in it." >&2
  return 1 2>/dev/null || exit 1
fi

_bf_op="$(command -v op || command -v op.exe || true)"

while IFS= read -r _bf_line || [ -n "$_bf_line" ]; do
  _bf_line="${_bf_line%%#*}"                       # drop comments
  _bf_line="$(printf '%s' "$_bf_line" | sed 's/[[:space:]]*$//')"
  [ -z "$_bf_line" ] && continue
  _bf_key="${_bf_line%%=*}"
  _bf_val="${_bf_line#*=}"
  case "$_bf_val" in
    op://*)
      if eval "[ -n \"\${$_bf_key:-}\" ]"; then
        continue                                   # already in the environment: keep it
      fi
      if [ -z "$_bf_op" ]; then
        echo "env.sh: $_bf_key is a 1Password reference but neither op nor op.exe is on PATH." >&2
        return 1 2>/dev/null || exit 1
      fi
      _bf_val="$("$_bf_op" read "$_bf_val")" || {
        echo "env.sh: could not read $_bf_key from 1Password." >&2
        return 1 2>/dev/null || exit 1
      }
      _bf_val="$(printf '%s' "$_bf_val" | tr -d '\r')"   # op.exe ends lines with CRLF
      if [ -z "$_bf_val" ]; then
        echo "env.sh: 1Password returned an empty $_bf_key." >&2
        return 1 2>/dev/null || exit 1
      fi
      ;;
  esac
  export "$_bf_key=$_bf_val"
done < "$_bf_env_file"

unset _bf_env_file _bf_op _bf_line _bf_key _bf_val

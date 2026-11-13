#!/usr/bin/env bash
# Deploys Studio to production whenever main moves and something Studio ships changed. Builds from a
# clean checkout of main, so uncommitted work never goes live. A systemd user path unit watches main's
# reflog: commits made inside Claude's sandbox can't reach the network, so a git hook can't deploy.
# Anything to tell you (a build newly behind, or main not deployed within half an hour because a deploy
# failed or the unit isn't running) is printed by the git hooks on your next commit on main.
#
# Usage: just studio-autodeploy on|off|status    (run: what the unit calls; notify: what the hooks call)
set -uo pipefail
COMMON=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --path-format=absolute --git-common-dir)
MAIN=$(dirname "$COMMON")
TREE=$COMMON/studio-deploy-tree
LOG=$COMMON/studio-autodeploy.log
WARN=$COMMON/studio-autodeploy-warn
DONE=$COMMON/studio-autodeploy-done
SELF=$MAIN/scripts/studio_autodeploy.sh
UNIT=purple-studio-deploy
UNITS=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
HOOKS=(post-commit post-merge)
source "$MAIN/build-scripts/config.sh"

deployed() {
    curl -fsS --max-time 10 "https://studio.purplecomputer.org/version.json?t=$(date +%s)" \
        | sed -n 's/.*"commit": *"\([^"]*\)".*/\1/p'
}

deploy() {
    local sha=$1 out
    out=$(mktemp)
    echo "=== $(date '+%F %T') deploying ${sha:0:8}"
    git -C "$TREE" checkout -q --force --detach "$sha" && git -C "$TREE" clean -fdq || return 1
    # The compat prompt only appears when a build fell behind since the last check: say yes, then warn.
    (cd "$TREE" && just studio-deploy --prod < <(yes)) 2>&1 | tee "$out"
    local status=${PIPESTATUS[0]}
    grep -q "Newly behind" "$out" && echo "Studio ${sha:0:8} went live, and a Purple out there can't open everything it makes now: $(grep "Newly behind" "$out"). Run just compat-check." >>"$WARN"
    rm -f "$out"
    return "$status"
}

run() {
    exec >>"$LOG" 2>&1
    sleep 20  # a lane landing as several cherry-picks moves main several times
    local sha last=""
    while sha=$(git -C "$MAIN" rev-parse main) && [ "$sha" != "$last" ]; do
        last=$sha
        local live; live=$(deployed)
        if [ -n "$live" ] && git -C "$MAIN" diff --quiet "$live" "$sha" -- "${STUDIO_PATHS[@]}" 2>/dev/null; then
            echo "$(date '+%F %T') main ${sha:0:8}: nothing new for Studio since ${live:0:8}"
        else
            deploy "$sha" || continue
        fi
        echo "$sha" >"$DONE"
    done
}

notify() {
    [ "$(git symbolic-ref --short -q HEAD)" = main ] || return 0
    local old; old=$(git rev-parse -q --verify 'main@{30 minutes ago}' 2>/dev/null)
    [ -n "$old" ] && ! git merge-base --is-ancestor "$old" "$(cat "$DONE" 2>/dev/null)" 2>/dev/null \
        && echo "Studio auto-deploy hasn't handled main ${old:0:8} from over half an hour ago: just studio-autodeploy status" >>"$WARN"
    [ -s "$WARN" ] || return 0
    printf '\033[1;33m%s\033[0m\n' "$(cat "$WARN")" >&2
    rm -f "$WARN"
}

on() {
    [ -e "$TREE" ] || git -C "$MAIN" worktree add -q --detach "$TREE" main || exit 1
    ln -sf "$MAIN/build-scripts/.env" "$TREE/build-scripts/.env"
    [ -e "$TREE/studio/.vercel" ] || cp -r "$MAIN/studio/.vercel" "$TREE/studio/" || exit 1
    for h in "${HOOKS[@]}"; do
        local f=$COMMON/hooks/$h
        [ -e "$f" ] && ! grep -q studio_autodeploy "$f" && { echo "$f exists; add: $SELF notify" >&2; continue; }
        printf '#!/bin/sh\n[ -x "%s" ] && exec "%s" notify\nexit 0\n' "$SELF" "$SELF" >"$f" && chmod +x "$f"
    done
    mkdir -p "$UNITS"
    printf '[Unit]\nDescription=Deploy Purple Studio when main moves\n\n[Path]\nPathModified=%s\n\n[Install]\nWantedBy=default.target\n' \
        "$COMMON/logs/refs/heads/main" >"$UNITS/$UNIT.path"
    # NixOS: the venv's numpy finds libstdc++ only through nix-ld's LD_LIBRARY_PATH.
    printf '[Service]\nType=oneshot\nEnvironment="PATH=%s"\nEnvironment="LD_LIBRARY_PATH=%s"\nExecStart=%s run\n' \
        "$PATH" "${LD_LIBRARY_PATH:-}" "$SELF" >"$UNITS/$UNIT.service"
    systemctl --user daemon-reload && systemctl --user enable --now "$UNIT.path" || exit 1
    git -C "$MAIN" rev-parse main >"$DONE"
    echo "Studio now deploys itself when main changes. Log: $LOG"
    loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes \
        || echo "Note: it only runs while you're logged in. To keep it running: loginctl enable-linger"
}

off() {
    systemctl --user disable --now "$UNIT.path" 2>/dev/null
    rm -f "$UNITS/$UNIT.path" "$UNITS/$UNIT.service"
    systemctl --user daemon-reload
    for h in "${HOOKS[@]}"; do grep -qs studio_autodeploy "$COMMON/hooks/$h" && rm -f "$COMMON/hooks/$h"; done
    [ -e "$TREE" ] && git -C "$MAIN" worktree remove --force "$TREE"
    rm -f "$DONE"
    echo "Studio auto-deploy is off: just studio-deploy --prod deploys by hand."
}

status() {
    systemctl --user is-active "$UNIT.path" "$UNIT.service"
    [ -s "$WARN" ] && cat "$WARN"
    tail -n 15 "$LOG" 2>/dev/null
}

case ${1:-} in
    on|off|status|run|notify) "$1" ;;
    *) echo "usage: just studio-autodeploy on|off|status" >&2; exit 1 ;;
esac

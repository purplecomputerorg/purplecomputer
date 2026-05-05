#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-main}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git worktree list --porcelain | awk '
  /^worktree / { path=$2 }
  /^branch / {
    branch=$2
    sub("refs/heads/", "", branch)
    print path "|" branch
  }
' | while IFS='|' read -r path branch; do
  safe_branch="${branch//\//__}"
  git -C "$path" diff --name-only "$BASE...HEAD" \
    | sed "s|$|	$branch|" \
    > "$TMP/$safe_branch.files" || true
done

echo "Exact file overlaps:"
cat "$TMP"/*.files 2>/dev/null \
  | awk -F '\t' '
    {
      file=$1
      branch=$2
      files[file]=files[file] " " branch
      count[file]++
    }
    END {
      found=0
      for (file in count) {
        if (count[file] > 1) {
          found=1
          print "- " file ":" files[file]
        }
      }
      if (!found) print "- none"
    }
  '

echo
echo "Directory overlaps:"
cat "$TMP"/*.files 2>/dev/null \
  | awk -F '\t' '
    {
      n=split($1, parts, "/")
      dir = n > 1 ? parts[1] "/" parts[2] : parts[1]
      branch=$2
      key=dir SUBSEP branch
      if (!seen[key]++) {
        dirs[dir]=dirs[dir] " " branch
        count[dir]++
      }
    }
    END {
      found=0
      for (dir in count) {
        if (count[dir] > 1) {
          found=1
          print "- " dir ":" dirs[dir]
        }
      }
      if (!found) print "- none"
    }
  '

#!/usr/bin/env bash
set -euo pipefail
: "${RELEASE_VERSION:?Release version is required}"
: "${GITHUB_REPOSITORY:?GitHub repository is required}"
: "${GITHUB_SHA:?Build commit is required}"
: "${RUNNER_TEMP:?Runner temporary directory is required}"
: "${GITHUB_OUTPUT:?GitHub step output path is required}"
: "${RELEASE_KIND:?Release kind is required}"
: "${MOD_NAME:?Project name is required}"
git check-ref-format "refs/tags/$RELEASE_VERSION"
if git show-ref --verify --quiet "refs/tags/$RELEASE_VERSION"; then
    printf 'Tag already exists: %s. Choose a new release version.\n' "$RELEASE_VERSION" >&2
    exit 1
fi
strReleases="$RUNNER_TEMP/ExistingReleases.json"
gh api --paginate --slurp "repos/$GITHUB_REPOSITORY/releases?per_page=100" > "$strReleases"
if jq -e --arg strTag "$RELEASE_VERSION" 'any(.[][]; .tag_name == $strTag)' "$strReleases" > /dev/null; then
    printf 'A release already uses tag %s. Choose a new release version.\n' "$RELEASE_VERSION" >&2
    exit 1
fi
strPrevious="$(jq -r '[.[][] | select(.draft == false)] | sort_by(.published_at) | last | .tag_name // empty' "$strReleases")"
printf 'previous_tag=%s\n' "$strPrevious" >> "$GITHUB_OUTPUT"
strNotes="$RUNNER_TEMP/ReleaseNotes.md"
case "$RELEASE_KIND" in
    ipa)
        printf 'Includes %s-NeedsSigning.ipa and %s.dylib.\n\n' "$MOD_NAME" "$MOD_NAME" > "$strNotes"
        printf '%s\n\n' 'Sign the entire IPA, including embedded frameworks and dylibs, before installing.' >> "$strNotes"
        ;;
    dylib)
        printf 'Includes %s.dylib only.\n\n' "$MOD_NAME" > "$strNotes"
        printf '%s\n\n' 'Inject the library into a compatible decrypted IPA and sign the entire app before installing.' >> "$strNotes"
        ;;
    *) printf 'Unknown release kind: %s\n' "$RELEASE_KIND" >&2; exit 1 ;;
esac
strCommits="$RUNNER_TEMP/ReleaseCommits.md"
if [[ -n "$strPrevious" ]]; then
    git rev-parse --verify "refs/tags/$strPrevious^{commit}" > /dev/null
    printf '## Commits since %s\n\n' "$strPrevious" >> "$strNotes"
    git log --format='- %s (%h)' "refs/tags/$strPrevious..$GITHUB_SHA" > "$strCommits"
else
    printf '## Initial release commits\n\n' >> "$strNotes"
    git log --format='- %s (%h)' "$GITHUB_SHA" > "$strCommits"
fi
if [[ -s "$strCommits" ]]; then
    cat "$strCommits" >> "$strNotes"
else
    printf '%s\n' 'No source commits since the previous published release.' >> "$strNotes"
fi

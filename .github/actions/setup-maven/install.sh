#!/usr/bin/env bash
# Installs the Maven pinned as MAVEN_VERSION in the given tool-versions.env and puts it first
# on PATH for the remaining steps of the job.
#
# The runner image's own Maven is whatever the image ships that week (3.9.16 until 2026-09, 3.10.0
# from the 2026-10-04 image) and the Central publishing plugin does not bundle cleanly with 3.10.
# A pinned Maven makes every build, test and release of the ecosystem use the same one.
#
#   install.sh <path to tool-versions.env>
#
# MAVEN_DIST_BASE overrides where the distribution is fetched from (tests point it at a fake).
set -euo pipefail

pins="${1:?usage: install.sh <path to tool-versions.env>}"
base="${MAVEN_DIST_BASE:-https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven}"

version="$(sed -n 's/^MAVEN_VERSION=//p' "$pins" | head -n 1 | tr -d '"'"'"'[:space:]')"
if [[ -z "$version" ]]; then
  echo "::error::MAVEN_VERSION is not set in $pins" >&2
  exit 1
fi

archive="apache-maven-${version}-bin.tar.gz"
work="${RUNNER_TEMP:?RUNNER_TEMP is not set}"
download="$work/maven-download"
rm -rf "$download"
mkdir -p "$download"

# Never fall back to the runner's Maven: a missing download must fail the job.
if ! curl -fsSL --retry 3 -o "$download/$archive" "$base/$version/$archive" \
  || ! curl -fsSL --retry 3 -o "$download/$archive.sha512" "$base/$version/$archive.sha512"; then
  echo "::error::could not download Maven ${version} from ${base}" >&2
  exit 1
fi

expected="$(tr -d '[:space:]' < "$download/$archive.sha512")"
expected="${expected%%[!0-9a-fA-F]*}"
if command -v sha512sum >/dev/null 2>&1; then
  actual="$(sha512sum "$download/$archive" | cut -d' ' -f1)"
else
  actual="$(shasum -a 512 "$download/$archive" | cut -d' ' -f1)"
fi
if [[ -z "$expected" || "$expected" != "$actual" ]]; then
  echo "::error::checksum mismatch for $archive (published ${expected:-none}, downloaded ${actual})" >&2
  exit 1
fi

tar -xzf "$download/$archive" -C "$work"
home="$work/apache-maven-${version}"

# The archive must be the version it is named after before anything depends on it.
reported="$("$home/bin/mvn" --version | sed -n '1p')"
if [[ "$reported" != "Apache Maven ${version}"* ]]; then
  echo "::error::expected Apache Maven ${version}, the archive reports: ${reported}" >&2
  exit 1
fi

echo "$home/bin" >> "$GITHUB_PATH"
echo "MAVEN_VERSION=${version}" >> "$GITHUB_ENV"
echo "Installed ${reported}"

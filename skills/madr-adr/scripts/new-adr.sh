#!/usr/bin/env bash
# new-adr.sh — scaffold the next MADR decision record under docs/adr/.
# Spec: skills/madr-adr/SKILL.md §2/§4 — issue #60 (AC1/AC6).
# Usage: new-adr.sh "<short imperative title>"
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "Usage: $(basename "$0") \"<short imperative title>\"" >&2
    echo "Scaffolds the next docs/adr/NNNN-<slug>.md from the MADR template." >&2
    exit 1
fi
title=$1

# Slugify: lowercase; runs of non-alphanumerics -> single hyphen; trim edges.
slug=$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-')
slug=${slug#-}
slug=${slug%-}
if [ -z "$slug" ]; then
    echo "Error: title must contain at least one letter or digit." >&2
    exit 1
fi

adr_dir=docs/adr
mkdir -p "$adr_dir"

# Next sequence number: max existing NNNN-*.md + 1 (gap-free from 0001).
next=1
for f in "$adr_dir"/[0-9][0-9][0-9][0-9]-*.md; do
    [ -e "$f" ] || continue
    n=$(basename "$f")
    n=${n%%-*}
    n=$((10#$n))
    if [ "$n" -ge "$next" ]; then
        next=$((n + 1))
    fi
done
num=$(printf '%04d' "$next")
target=$adr_dir/$num-$slug.md
date_today=$(date +%F)

# Safety: never clobber an existing record (race/sequence edge cases).
if [ -e "$target" ]; then
    echo "Error: refusing to overwrite existing file: $target" >&2
    exit 1
fi

cat > "$target" <<EOF
# MADR-$num: $title

- **Status:** proposed
- **Date:** $date_today
- **Deciders:** <@architect, @fpittelo, other deciders>

## Context

<The architectural forces at play: the problem, the constraints, what triggered this decision.>

## Decision Drivers

- <Driver 1 — e.g., a governance rule, cost constraint, Swiss nLPD privacy constraint>

## Considered Options

### Option 1: <name>

- Pros: <...>
- Cons: <...>

### Option 2: <name>

- Pros: <...>
- Cons: <...>

## Decision Outcome

Chosen option: "<Option name>", because <rationale tying back to the decision drivers>.

## Consequences

- **Positive:** <...>
- **Negative:** <...>
- **Mitigations:** <...>
EOF

echo "Created $target"

#!/usr/bin/env bash
# Copy per-grid scrape artifacts into the checkout.
#
# Each artifact is artifacts/grid-<id>/{files,history}. files/ holds only the
# finished results for that grid (not sibling party/promo directories). history/
# holds the new *.csv.gz snapshot from that job. Existing history files and
# sibling grids already in the checkout are left in place.
set -euo pipefail

artifacts_root="${1:?artifacts root}"
repo_root="${2:?repo root}"

copied=0
for grid in 2a3c 2a3c-mhot 4a1c 4a1c-mhot; do
  case "${grid}" in
    2a3c) rel="output/eilat" ;;
    2a3c-mhot) rel="output/eilat/promo-mhot" ;;
    4a1c) rel="output/eilat/party-4a1c" ;;
    4a1c-mhot) rel="output/eilat/party-4a1c/promo-mhot" ;;
  esac
  src="${artifacts_root}/grid-${grid}"
  if [[ ! -d "${src}/files" ]]; then
    echo "No artifact for ${grid}; skipping"
    continue
  fi
  target="${repo_root}/${rel}"
  mkdir -p "${target}"
  for required in results.csv results.json offers.csv report.html; do
    if [[ ! -f "${src}/files/${required}" ]]; then
      echo "Artifact for ${grid} is missing ${required}" >&2
      exit 1
    fi
  done
  shopt -s nullglob
  files=("${src}/files"/*)
  shopt -u nullglob
  for file in "${files[@]}"; do
    if [[ -f "${file}" ]]; then
      cp -a "${file}" "${target}/"
      echo "copied ${grid}: $(basename "${file}") -> ${rel}/"
    fi
  done
  hist_dir="${src}/history"
  if [[ -d "${hist_dir}" ]]; then
    mkdir -p "${repo_root}/output/history/runs"
    shopt -s nullglob
    hists=("${hist_dir}"/*.csv.gz)
    shopt -u nullglob
    if [[ ${#hists[@]} -eq 0 ]]; then
      echo "Artifact for ${grid} has no history snapshot" >&2
      exit 1
    fi
    for hist in "${hists[@]}"; do
      base="$(basename "${hist}")"
      dest_hist="${repo_root}/output/history/runs/${base}"
      if [[ -e "${dest_hist}" ]]; then
        echo "history already present: ${base}"
      else
        cp -a "${hist}" "${dest_hist}"
        echo "history: ${base}"
      fi
    done
  else
    echo "Artifact for ${grid} is missing history/" >&2
    exit 1
  fi
  copied=$((copied + 1))
done

if [[ "${copied}" -eq 0 ]]; then
  echo "No grid artifacts to publish" >&2
  exit 1
fi
echo "Published ${copied} grid(s)"

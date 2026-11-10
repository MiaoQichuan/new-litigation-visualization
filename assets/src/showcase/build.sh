#!/usr/bin/env bash
# 首页成品墙的八张展示图：八个虚构的高端案件，逐个模块实际跑出来。
# 用法：bash assets/src/showcase/build.sh [输出目录]（默认 /tmp/nlv-showcase）。只写输出目录，不改本目录与各模块。
set -euo pipefail
# 本目录的文件名含中文、以 UTF-8 存盘；在非 UTF-8 区域设置下也按 UTF-8 解析路径，结果与 UTF-8 下逐字节相同。
export PYTHONUTF8=1
HERE="$(cd "$(dirname "$0")" && pwd)"
SK="$HERE/../../../plugins/mqc-nlv/skills"
OUT="${1:-/tmp/nlv-showcase}"; rm -rf "$OUT"; mkdir -p "$OUT"
python3 "$SK/mqc-litigation-visual-redraw/scripts/render.py" "$HERE/v1-flow.json" "$OUT/v1" --formats=svg
python3 "$SK/mqc-timeline-master/scripts/render_figure.py" "$HERE/v2-timeline.json" "$OUT/v2.svg"
python3 "$SK/mqc-legal-relation-master/scripts/make.py" "$HERE/v3-relations.json" --out "$OUT/v3" --choice "$HERE/v3-choice.json"
mkdir -p "$OUT/v4"; python3 "$SK/mqc-chronicle-master/scripts/build_brief.py" "$HERE/v4-brief.json" "$OUT/v4"
mkdir -p "$OUT/v5"; (cd "$OUT/v5" && python3 "$SK/mqc-trial-confrontation-master/scripts/pipeline.py" "$HERE/v5-case.json" 出图)
mkdir -p "$OUT/v6"; python3 "$SK/mqc-legal-chart-master/scripts/make.py" "$HERE/v6-rose.json" -o "$OUT/v6/chart"
cp -r "$HERE/v7-deck" "$OUT/v7"; python3 "$SK/mqc-legal-courseware-master/scripts/build.py" "$OUT/v7"
cp -r "$HERE/v8-case/materials" "$OUT/v8"; python3 "$SK/mqc-fact-chronology-master/scripts/ingest.py" "$OUT/v8"
cp "$HERE/v8-case/facts.json" "$OUT/v8/_案件看板/事实.json"; python3 "$SK/mqc-fact-chronology-master/scripts/make.py" "$OUT/v8/_案件看板"
echo "完成：$OUT（截图裁切后拼成首页的 assets/modules.png）"

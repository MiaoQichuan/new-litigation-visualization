# New Litigation Visualization · Make the Law Visible

Seven litigation visualisation skills for lawyers. Once installed, just describe what you need in the chat, for example "turn these judgments and exhibits into a case timeline" or "draw the legal relationships in this case".

Results are written to your current workspace; the chat shows a file card you can click to preview in the right sidebar.

## The seven skills

| Skill | What it does | Delivers |
| --- | --- | --- |
| Litigation visual redraw | Redraws an existing timeline, flowchart or relationship diagram without changing a word | SVG, PNG, PPTX |
| Timeline master | Builds a case timeline from case files; every event traces back to its source sentence | SVG, PPTX, Visio, drawio; Word trace index (needs Node.js) |
| Legal relationship master | Who is related to whom, under which contract or payment | SVG, PPTX, Visio, drawio |
| Chronicle master | Turns a batch of materials into a case chronicle | Excel, A4 brief; Word (needs Node.js) |
| Trial confrontation master | Pre-trial confrontation map and analysis table (nine-step method) | SVG, Excel |
| Legal chart master | Statistical charts of legal data; every number in a title must follow from the data | SVG, editable PPTX |
| Legal courseware master | Puts the figures into lecture slides with conclusions, notes and statutes | PPTX |

## First use

The engines are written in Python: **Python 3.9 or later** must be installed. Say "check the New Litigation Visualization environment" in the chat and it reports what is missing and how to install it. On Windows, tick **"Add python.exe to PATH"** on the first page of the python.org installer, then quit and reopen DeepSeek Harness. openpyxl ships with the plugin; LibreOffice, Graphviz and Node.js are optional.

## Security and privacy

Everything runs locally: no network calls, no external APIs, nothing uploaded. Only the scripts shipped with the plugin are run, and results are written only to the current workspace.

## License

AGPL-3.0-only. Author: Miao Qichuan. Source: https://github.com/MiaoQichuan/new-litigation-visualization

# -*- coding: utf-8 -*-
"""给判据用的最小渲染：只画主体与线，不画标签。

判据读的是坐标，不看样式，所以验证用的图不必完整——
省下的渲染时间在每个候选上都要花一次。
"""
import math, tempfile, os


def render(a, pos, rects, skel, d):
    NW, NH = d["node"]
    OX = OY = 100
    O = []
    for k, v in rects.items():
        O.append(f'<rect data-kind="node" x="{v[0]+OX}" y="{v[1]+OY}" '
                 f'width="{NW}" height="{NH}" rx="12" fill="#F3F4F6" '
                 f'stroke="#D6DAE0" stroke-width="1"/>')
    for p in skel:
        q = [(x + OX, y + OY) for x, y in p]
        dx, dy = q[-1][0] - q[-2][0], q[-1][1] - q[-2][1]
        L = math.hypot(dx, dy) or 1
        q[-1] = (q[-1][0] - dx / L * 12, q[-1][1] - dy / L * 12)
        path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in q)
        O.append(f'<path data-kind="edge" d="{path}" fill="none" '
                 f'stroke="#4B5563" stroke-width="1.30" marker-end="url(#a)"/>')
    xs = [x for p in skel for x, _ in p] + [v[0] + NW for v in rects.values()]
    ys = [y for p in skel for _, y in p] + [v[1] + NH for v in rects.values()]
    W, H = int(max(xs)) + 2 * OX, int(max(ys)) + 2 * OY
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">', f'<rect width="{W}" height="{H}" fill="#FFF"/>',
            '<defs><marker id="a" markerWidth="12" markerHeight="8.4" refX="0" '
            'refY="4.2" markerUnits="userSpaceOnUse" orient="auto">'
            '<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="#4B5563"/></marker></defs>']
    fd, p = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    open(p, "w", encoding="utf-8").write("\n".join(head + O) + "\n</svg>")
    return p

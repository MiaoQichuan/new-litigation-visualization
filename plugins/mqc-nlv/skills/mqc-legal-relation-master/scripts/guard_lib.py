# -*- coding: utf-8 -*-
"""判据库：出图之后自动验一遍。

索引表只保证交叉与拐弯的指标，不保证不穿主体、不贴边、箭头到位。
查表出图的流程若不接判据，等于没人把关。

这里不重写判据，直接调用已经验证多轮的 route_guard，解析它的输出——
判据本身读的是产物 SVG 的坐标，那才是唯一可信的依据。
"""
import subprocess, sys, re, os

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "route_guard.py")


def check(svg_path, verbose=False):
    """返回 (是否全过, 结果清单)。清单每条含判据名、是否通过、量值说明。"""
    # 必须指定 UTF-8：Windows 默认按 GBK 解码子进程输出，判据的中文一读就坏，
    # stdout 变成 None，后面整条判据链静默失效。
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([sys.executable, GUARD, svg_path], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=120, env=env)
    out = r.stdout or ""
    res = []
    for m in re.finditer(r"^\s+(OK|FAIL|WARN)\s+(G\d+)\s+(.*)$", out, re.M):
        state, name, msg = m.groups()
        res.append(dict(name=name, ok=state != "FAIL", warn=state == "WARN",
                        msg=msg.strip()))
    if verbose:
        for x in res:
            tag = "OK  " if x["ok"] and not x["warn"] else ("WARN" if x["warn"] else "FAIL")
            print(f"  {tag} {x['name']}  {x['msg']}")
    return all(x["ok"] for x in res) and bool(res), res


def report(svg_path):
    """给使用者看的一句话：过了就说过了，没过就说明哪里不对。"""
    ok, res = check(svg_path)
    if not res:
        return False, "判据没读到内容，多半是 SVG 结构变了"
    bad = [x for x in res if not x["ok"]]
    warn = [x for x in res if x["warn"]]
    if bad:
        return False, "；".join(f"{x['name']} {x['msg']}" for x in bad)
    if warn:
        return True, "；".join(f"{x['name']} {x['msg']}" for x in warn)
    return True, f"{len(res)} 条判据全部通过"

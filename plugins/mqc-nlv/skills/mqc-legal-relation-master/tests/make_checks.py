# -*- coding: utf-8 -*-
"""make.py 的端到端自检，含改坏验证。

    python tests/make_checks.py

一、示例案：奇川风带两处重点，一条命令出齐，路线判据与导出物判据全过
二、缓存：换成白描再跑，布局必须复用，不得重新求解
三、拒绝：非奇川风带重点、关系名空着、指向不存在的主体、重点三处
四、长名称：换行加高能装下的必须装下；装不下的如实写进交付说明，不删字
五、第〇轮：超 9 个模块、超 12 条关系都拦下；精简后连通、不丢关系名、未入图的全部进出处索引
六、画不好的输入先拦下并说清原因：自指、反向双关系、孤立模块、不连通的小图
七、第〇轮写回的文件，第二轮能正常列出关系；名称带 & < > 不被误判撑破；长关系名不越出画布
五、第〇轮：超过 9 个模块时停下；建议、拒绝越界、未入图入索引、「全部」放行
"""
import os, sys, json, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
MAKE = os.path.join(HERE, "..", "scripts", "make.py")
FX = os.path.join(HERE, "fixtures", "relations-demo.json")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
tmp = tempfile.mkdtemp()
fails = []
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(*args):
    r = subprocess.run([sys.executable, MAKE, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    return r.returncode, r.stdout + r.stderr


def expect(cond, name, detail=""):
    print(("  OK    " if cond else "  FAIL  ") + name + ("" if cond else f"\n        {detail[-300:]}"))
    if not cond:
        fails.append(name)


def dump(obj, name):
    p = os.path.join(tmp, name)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


out = os.path.join(tmp, "o")
print("一、示例案")
ch = dump({"style": "奇川风", "emphasis": {"nodes": ["PRICE"], "edges": [9]}}, "c1.json")
code, log = run(FX, "--out", out, "--choice", ch, "--name", "demo")
chk = open(os.path.join(out, "demo-qichuan-checks.txt"), encoding="utf-8").read() if code == 0 else ""
expect(code == 0 and "交付：svg、png、pptx、vsdx、drawio" in log, "五种格式全部交付", log)
expect("FAIL" not in chk, "路线判据与导出物判据全过", chk)

print("二、缓存")
ch2 = dump({"style": "白描", "emphasis": {"nodes": [], "edges": []}}, "c2.json")
code, log = run(FX, "--out", out, "--choice", ch2, "--name", "demo")
expect(code == 0 and "复用缓存" in log and "开始求解" not in log, "换风格不重跑布局", log)

print("三、拒绝")
bad = dump({"style": "歸藏风", "emphasis": {"nodes": ["PRICE"], "edges": []}}, "c3.json")
expect(run(FX, "--out", out, "--choice", bad)[0] != 0, "歸藏风带重点 → 拒绝")
rel = json.load(open(FX, encoding="utf-8"))
r1 = json.loads(json.dumps(rel)); r1["edges"][0][2] = ""
expect(run(dump(r1, "r1.json"), "--plan-only")[0] != 0, "关系名空着 → 拒绝")
r2 = json.loads(json.dumps(rel)); r2["edges"][0][1] = "NOBODY"
expect(run(dump(r2, "r2.json"), "--plan-only")[0] != 0, "指向不存在的主体 → 拒绝")
bad3 = dump({"style": "奇川风", "emphasis": {"nodes": ["PRICE", "GC"], "edges": [1]}}, "c4.json")
expect(run(FX, "--out", out, "--choice", bad3)[0] != 0, "重点三处 → 拒绝")

print("四、长名称")
r3 = json.loads(json.dumps(rel))
r3["nodes"][0]["name"] = "Example（China）Limited"
r3["nodes"][0]["note"] = "被上诉人 / 投资方 / 受托人"
out3 = os.path.join(tmp, "o3")
code, log = run(dump(r3, "r3.json"), "--out", out3, "--name", "long")
chk = open(os.path.join(out3, "long-qichuan-checks.txt"), encoding="utf-8").read() if code == 0 else ""
expect(code == 0 and "FAIL" not in chk and "须人工处理" not in log, "名称与备注各换一行、加高模块，判据全过", log + chk)
r4 = json.loads(json.dumps(rel))
r4["nodes"][0]["name"] = "Example (China) Investment Holdings Limited"
r4["nodes"][0]["note"] = "被上诉人 / 投资方 / 受托人"
code, log = run(dump(r4, "r4.json"), "--out", os.path.join(tmp, "o4"), "--name", "long4")
expect(code == 0 and "须人工处理" in log and "装不下" in log, "五行装不下 → 交付说明如实写明，不删字", log)

print("五、第〇轮")
ASK = os.path.join(HERE, "..", "scripts", "ask.py")


def ask(*args):
    r = subprocess.run([sys.executable, ASK, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    return r.returncode, r.stdout + r.stderr


R15 = os.path.join(HERE, "fixtures", "relations-15.json")
full = json.load(open(R15, encoding="utf-8"))
code, log = run(R15, "--plan-only")
expect(code == 4 and "ask.py trim" in log, "15 个模块 → make.py 拦下，提示第〇轮", log)
code, log = ask("trim", R15)
import re as _re
starred = _re.findall(r"^\d+　★ ", log, _re.M)
expect(code == 0 and len(starred) == 9 and "至多 9 个" in log, "第〇轮列出全部模块，★ 恰好标出 9 个", log)
t1 = os.path.join(tmp, "t1.json")
code, log = ask("trim", R15, "--keep", "0", "--out", t1)
r1 = json.load(open(t1, encoding="utf-8")) if code == 0 else {}
expect(code == 0 and len(r1["nodes"]) == 9, "不回答 → 按建议留 9 个", log)
ids = {n["id"] for n in r1.get("nodes", [])}
adj = {k: set() for k in ids}
for e in r1.get("edges", []):
    adj[e["from"]].add(e["to"]); adj[e["to"]].add(e["from"])
seen, stack = set(), [next(iter(ids))] if ids else []
while stack:
    x = stack.pop()
    if x not in seen:
        seen.add(x); stack += list(adj[x])
expect(seen == ids, "建议留下的 9 个模块彼此连通")
labels_all = sorted(e["label"] for e in full["edges"])
labels_now = sorted([e["label"] for e in r1.get("edges", [])] +
                    [e["label"] for e in r1.get("dropped", {}).get("edges", [])])
expect(labels_all == labels_now, "关系一条不丢：留下的 + 未入图的 = 原有的")
code, log = run(t1, "--plan-only")
expect(code == 4 and "超过 12 条" in log, "9 个模块 17 条关系 → 再拦一次", log)
t2 = os.path.join(tmp, "t2.json")
code, log = ask("trim", t1, "--keep-edges", "0", "--out", t2)
r2 = json.load(open(t2, encoding="utf-8")) if code == 0 else {}
ends = {x for e in r2.get("edges", []) for x in (e["from"], e["to"])}
expect(code == 0 and len(r2["edges"]) == 12 and ends == {n["id"] for n in r2["nodes"]},
       "按建议留 12 条，每个模块至少挂一条", log)
labels_now = sorted([e["label"] for e in r2.get("edges", [])] +
                    [e["label"] for e in r2.get("dropped", {}).get("edges", [])])
expect(labels_all == labels_now, "两步精简后关系仍一条不丢")
out5 = os.path.join(tmp, "o5")
code, log = run(t2, "--out", out5, "--name", "c15")
prov = open(os.path.join(out5, "c15-provenance.md"), encoding="utf-8").read() if code == 0 else ""
missing = [n["name"] for n in r2.get("dropped", {}).get("nodes", []) if n["name"] not in prov]
expect(code == 0 and "未入图" in prov and not missing and "判据：全部通过" in log,
       "精简后出图，判据全过，未入图的模块全部写进出处索引", log)
expect(ask("trim", R15, "--keep", "1,2,3,4,5,6,7,8,9,10", "--out", os.path.join(tmp, "x.json"))[0] != 0,
       "留 10 个 → 拒绝")
expect(ask("trim", t1, "--keep-edges", "1,2", "--out", os.path.join(tmp, "y.json"))[0] != 0,
       "有模块一条关系都没留 → 拒绝")
tall = os.path.join(tmp, "all.json")
ask("trim", R15, "--keep", "全部", "--out", tall)
expect(run(tall, "--plan-only")[0] == 0, "回答「全部」→ 放行（不删，但会慢）")
dup = json.loads(json.dumps(rel))
dup["edges"].append([dup["edges"][0][0], dup["edges"][0][1], "另一关系"])
dp = dump(dup, "dup.json"); dout = os.path.join(tmp, "dup-out.json")
code, log = ask("trim", dp, "--out", dout)
m = json.load(open(dout, encoding="utf-8")) if code == 0 else {"edges": []}
expect(code == 0 and len(m["edges"]) == len(rel["edges"]) and
       any(e["label"] == dup["edges"][0][2] + "；另一关系" for e in m["edges"]),
       "同向重复关系合并，关系名原样用「；」连起来", log)

print("六、输入检查")
two = lambda es: {"nodes": [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}, {"id": "C", "name": "丙"}], "edges": es}
code, log = run(dump(two([["A", "A", "自己"], ["A", "B", "x"], ["B", "C", "y"]]), "self.json"), "--plan-only")
expect(code == 2 and "同一个模块" in log, "起止同一模块 → 拒绝并说明", log)
code, log = run(dump(two([["A", "B", "买"], ["B", "A", "卖"], ["B", "C", "y"]]), "opp.json"), "--plan-only")
expect(code == 2 and "方向相反" in log and "客体" in log, "反向双关系 → 拒绝并给出经由客体的画法", log)
code, log = run(dump(two([["A", "B", "x"]]), "lonely.json"), "--plan-only")
expect(code == 2 and "丙" in log and "一条关系都没有" in log, "孤立模块 → 拒绝并点名", log)
four = {"nodes": [{"id": k, "name": k} for k in "ABCD"], "edges": [["A", "B", "x"], ["C", "D", "y"]]}
code, log = run(dump(four, "disc.json"), "--plan-only")
expect(code == 3 and "互不相连" in log and "5 到 16" not in log, "不连通的小图 → 说明是不连通，而不是超出范围", log)

print("七、第二轮与文字")
ASKP = os.path.join(HERE, "..", "scripts", "ask.py")
r = subprocess.run([sys.executable, ASKP, "round2", t2], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=ENV)
expect(r.returncode == 0 and "from → to" not in r.stdout and "→" in r.stdout,
       "第〇轮写回的文件，第二轮列出的是真实关系", r.stdout[-300:])
sp = {"nodes": [{"id": "A", "name": "A&B <公司>"}, {"id": "B", "name": "乙"}], "edges": [["A", "B", "a<b & c"]]}
code, log = run(dump(sp, "sp.json"), "--out", os.path.join(tmp, "sp"), "--name", "sp")
expect(code == 0 and "判据：全部通过" in log, "名称带 & < > 判据全过", log)
ll = {"nodes": [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}],
      "edges": [["A", "B", "这是一条非常非常长的关系名称用来测试标签是否放得下而不越界"]]}
code, log = run(dump(ll, "ll.json"), "--out", os.path.join(tmp, "ll"), "--name", "ll")
expect(code == 0 and "判据：全部通过" in log, "长关系名不越出画布（G12）", log)

shutil.rmtree(tmp, ignore_errors=True)
print("全部通过" if not fails else f"{len(fails)} 项未过")
sys.exit(1 if fails else 0)

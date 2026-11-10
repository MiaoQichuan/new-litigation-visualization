# -*- coding: utf-8 -*-
"""由页面源码生成单文件页面。只给改页面的人用；技能运行时用的是已经生成好的 assets/template.html。

    python3 web/build.py            # 重新生成 ../assets/template.html（不含示例案件，留一个底稿数据槽）
    python3 web/build.py --demo     # 另出 web/out/demo.html：带全部示例案件，用来看效果、跑页面测试
    python3 web/build.py -o 某路径   # 写到别处（测试用它核对仓库里的模板与源码一致）

需要 fontTools（pip install fonttools）：标题宋体只嵌入页面用到的字，整页控制在 1MB 以内。
字体：Noto Serif CJK SC Bold、Inter，均为 SIL Open Font License 1.1，见 web/fonts/OFL.txt。
"""
import base64, glob, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
FONTS = os.path.join(HERE, 'fonts')
sys.path.insert(0, HERE)
import palette  # noqa: E402

DEMO = '--demo' in sys.argv
OUT = os.path.join(HERE, 'out', 'demo.html') if DEMO else os.path.join(HERE, '..', 'assets', 'template.html')
if '-o' in sys.argv:
    OUT = os.path.abspath(sys.argv[sys.argv.index('-o') + 1])
DATA_JS = ("\n(()=>{ try{ const el=document.getElementById('v8-data'); const t=el?el.textContent.trim():''; "
           "if(t && t[0]!=='@') CASES.push(...[].concat(JSON.parse(t))); }catch(e){ console.error('底稿数据读不出来', e); } })();\n")


def read(p):
    return open(p, encoding='utf-8').read()


def main():
    cases = sorted(glob.glob(os.path.join(SRC, 'cases', '*.js')))
    src_all = ''.join(read(f) for f in glob.glob(os.path.join(SRC, '*.js')) + glob.glob(os.path.join(SRC, '*.css')) + cases)
    chars = ''.join(sorted(set(c for c in src_all if ord(c) > 0x2E80))) + '０１２３４５６７８９（）《》「」〔〕【】、，。；：？！·—…'
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, 'chars.txt'), 'w', encoding='utf-8').write(chars)
    sub = os.path.join(tmp, 'song.woff')
    try:
        subprocess.run([sys.executable, '-m', 'fontTools.subset', os.path.join(FONTS, 'noto-serif-cjk-sc-bold.woff'),
                        '--text-file=' + os.path.join(tmp, 'chars.txt'), '--unicodes=U+0020-007E', '--flavor=woff',
                        '--output-file=' + sub], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit('需要 fontTools：pip install fonttools')
    b64 = lambda p: base64.b64encode(open(p, 'rb').read()).decode()
    fonts = (f'@font-face{{font-family:"QC Song";src:url(data:font/woff;base64,{b64(sub)}) format("woff");font-weight:400 900;font-display:swap}}\n'
             f'@font-face{{font-family:"QC Inter";src:url(data:font/woff;base64,{b64(os.path.join(FONTS, "inter-400.woff"))}) format("woff");font-weight:400;font-display:swap}}\n'
             f'@font-face{{font-family:"QC Inter";src:url(data:font/woff;base64,{b64(os.path.join(FONTS, "inter-600.woff"))}) format("woff");font-weight:600;font-display:swap}}\n')
    nocom = lambda s: re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    css = fonts + nocom(read(os.path.join(SRC, 'style.css')) + read(os.path.join(SRC, 'skin.css')))
    js = (read(os.path.join(SRC, 'core.js')) + read(os.path.join(SRC, 'packs.js'))
          + (''.join(read(f) for f in cases) if DEMO else '') + DATA_JS
          + read(os.path.join(SRC, 'app.js')) + read(os.path.join(SRC, 'features.js')) + read(os.path.join(SRC, 'skin.js')))
    js = nocom(js)
    js = re.sub(r'(?m)^\s*//.*$', '', js)
    js = re.sub(r'\n\s*\n+', '\n', js)
    # 脚本里不能出现真正的 </body> </html>：外部往页面末尾追加调试脚本时会切错位置
    js = js.replace('</body>', '<\\/body>').replace('</html>', '<\\/html>')
    css, js = palette.apply(css), palette.apply(js)
    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>V8 · 案件看板</title><style>{css}</style></head><body>
<div class="shell" id="shell"><div class="main"><div class="wrap" id="view"></div></div><aside class="drawer" id="drawer"><div class="drawer-in" id="drawerIn"></div></aside></div>
<div class="tip" id="tip"></div><div id="gaptip"></div><div class="toast" id="toast"></div>
<script id="v8-data" type="application/json">@@CASE_JSON@@</script>
<script>
{js}
</script></body></html>'''
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write(html)
    kb = len(html.encode('utf-8')) // 1024
    print(f'{os.path.relpath(OUT, os.path.join(HERE, ".."))}：{kb} KB')
    # 本地另有不宜出现在页面上的词表时（web/.forbidden-terms，一行一个，不进仓库），顺带扫一遍
    ft = os.path.join(HERE, '.forbidden-terms')
    if os.path.exists(ft):
        terms = [t.strip() for t in read(ft).splitlines() if t.strip()]
        body = re.sub(r'data:[a-z/+-]+;base64,[A-Za-z0-9+/=]+', '', html)
        hit = [t for t in terms if t in body]
        print('词表命中：' + ('、'.join(hit) if hit else '无'))
        if hit:
            sys.exit(1)
    if kb > 1024 and not DEMO:
        sys.exit('页面超过 1MB：请检查字体子集或新加的资源')


if __name__ == '__main__':
    main()

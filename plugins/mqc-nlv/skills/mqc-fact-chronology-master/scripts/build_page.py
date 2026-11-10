# -*- coding: utf-8 -*-
"""生成案件看板页面：只用 Python 标准库。

用法：
    python scripts/build_page.py 案件.base.json [-o 输出.html] [--force]

先跑一遍底稿检查；有错误就不生成（--force 可强行生成，仅供排查）。
生成的是一个单文件 HTML，不联网、不依赖任何外部资源，双击即可在浏览器打开。
"""
import json, os, sys, datetime
if hasattr(sys.stdout, 'reconfigure'):  # 中文 Windows（GBK）下打印不因个别字符崩掉
    sys.stdout.reconfigure(errors='replace'); sys.stderr.reconfigure(errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_base import check, log, SKILL_DIR

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, '..', 'assets', 'template.html')


def main():
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        print(__doc__); sys.exit(0)
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith('--') and a != '-o' and sys.argv[i - 1] != '-o']
    if not args:
        print(__doc__); sys.exit(2)
    src = args[0]
    out = None
    if '-o' in sys.argv:
        out = sys.argv[sys.argv.index('-o') + 1]
    c = json.load(open(src, encoding='utf-8'))
    E, W, st = check(c)
    if E and '--force' not in sys.argv:
        print(f'底稿有 {len(E)} 处错误，先改好再生成页面：')
        for x in E[:30]:
            print('  - ' + x)
        log(src, '生成页面（未生成）', [f'- 底稿有 {len(E)} 处错误，未生成'] + [f'  - 错误：{x}' for x in E])
        sys.exit(1)
    if not out:
        stem = os.path.splitext(os.path.splitext(src)[0])[0]
        if stem.endswith('.案件看板'):
            stem = stem[:-len('.案件看板')]
        out = stem + '.案件看板.html'
        if os.path.commonpath([os.path.abspath(out), SKILL_DIR]) == SKILL_DIR:
            out = os.path.join(os.getcwd(), os.path.basename(out))  # 范例在技能目录里：页面写到当前工作目录
    tpl = open(TEMPLATE, encoding='utf-8').read()
    data = json.dumps(c, ensure_ascii=False).replace('</', '<\\/')
    html = tpl.replace('@@CASE_JSON@@', data, 1)
    t = c.get('title') or '案件看板'
    html = html.replace('<title>V8 · 案件看板</title>', f'<title>{t} · 案件看板</title>', 1)
    open(out, 'w', encoding='utf-8').write(html)
    kb = os.path.getsize(out) // 1024
    lines = [f'- 底稿：{os.path.basename(src)}', f'- 页面：{os.path.basename(out)}（{kb} KB）',
             '- 统计：' + '，'.join(f'{k} {v}' for k, v in st.items()),
             f'- 提醒 {len(W)} 条' + ('；带错误强行生成' if E else '')]
    print('\n'.join(lines))
    log(src, '生成页面', lines)


if __name__ == '__main__':
    main()

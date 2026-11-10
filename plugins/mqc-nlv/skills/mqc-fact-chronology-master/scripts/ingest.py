# -*- coding: utf-8 -*-
"""材料入库：把材料文件夹里的文件统一抽成带行号的原文，免得每次各写一套抽取脚本。

用法：
    python scripts/ingest.py 材料文件夹 [工作目录]

工作目录默认是「材料文件夹/_案件看板」。产出：
    原文/S01_文件名.txt   带行号的原文，Agent 读这个（行号就是引用时写的 ln）
    清单.json             每个源文件：编号、文件名、页数、哪些页没有文字层（需看图识读）、逐行原文

支持：.txt .md .csv（直接读）、.docx（段落与表格，表格一行写成「列 ｜ 列」）、.xlsx（逐表逐行）、
.pdf（依次尝试 PyMuPDF、pypdf、pdftotext，哪个装了用哪个）。图片与没有文字层的 PDF 页记为「需看图识读」。
只用 Python 标准库；PDF 需要上面三者之一。

增量：再次运行时，已入库的文件（按文件名与大小）保持原编号，新文件接着编号，不重复抽取。
"""
import json, os, re, sys, zipfile, shutil, subprocess, hashlib
if hasattr(sys.stdout, 'reconfigure'):  # 中文 Windows（GBK）下打印不因个别字符崩掉
    sys.stdout.reconfigure(errors='replace'); sys.stderr.reconfigure(errors='replace')
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
IMG = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.heic')
END = '。！？；：」』）)!?;:.'
PAGENO = re.compile(r'^\s*(第\s*\d+\s*页(\s*[，,/]?\s*共\s*\d+\s*页)?|[-—–]?\s*\d{1,3}\s*[-—–]?|\d+\s*/\s*\d+|Page \d+( of \d+)?)\s*$', re.I)


def clean(s):
    s = s.replace('　', ' ').replace('\xa0', ' ').replace('\t', ' ')
    return re.sub(r' {2,}', ' ', s).strip()


def docx_lines(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read('word/document.xml'))
    body = root.find(W + 'body')
    out = []

    def ptext(p):
        return clean(''.join(t.text or '' for t in p.iter(W + 't')))
    for el in body:
        if el.tag == W + 'p':
            t = ptext(el)
            if t:
                out.append(t)
        elif el.tag == W + 'tbl':
            for tr in el.iter(W + 'tr'):
                cells = [clean(' '.join(ptext(p) for p in tc.iter(W + 'p'))) for tc in tr.findall(W + 'tc')]
                if any(cells):
                    out.append(' ｜ '.join(c or '（空白）' for c in cells))
    return out, None, []


def xlsx_lines(path):
    z = zipfile.ZipFile(path)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(S + 'si'):
            ss.append(''.join(t.text or '' for t in si.iter(S + 't')))
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    names = [s.get('name') for s in wb.iter(S + 'sheet')]
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid = {r.get('Id'): r.get('Target') for r in rels}
    out = []
    for sh in wb.iter(S + 'sheet'):
        tgt = rid.get(sh.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'), '')
        tgt = 'xl/' + tgt.lstrip('/').replace('xl/', '')
        if tgt not in z.namelist():
            continue
        out.append('#工作表：' + sh.get('name'))
        for row in ET.fromstring(z.read(tgt)).iter(S + 'row'):
            vals = []
            for c in row.findall(S + 'c'):
                v = c.find(S + 'v'); t = c.get('t')
                if t == 's' and v is not None:
                    vals.append(ss[int(v.text)])
                elif t == 'inlineStr':
                    vals.append(''.join(x.text or '' for x in c.iter(S + 't')))
                else:
                    vals.append(v.text if v is not None and v.text else '')
            if any(x.strip() for x in vals):
                out.append(' ｜ '.join(clean(x) or '（空白）' for x in vals))
    return out, None, []


def _cjk(u):
    return sum('\u4e00' <= c <= '\u9fff' or c in '，。、：；（）《》「」' for c in u)


def _ucs2(line):
    """部分 PDF 用未嵌入的中文字体，pypdf 会把两字节编码当成两个拉丁字母吐出来；按 UTF-16 还原。"""
    best, bs = line, _cjk(line) / max(1, len(line))
    for t in (line, line.replace(' ', '\x00')):
        try:
            b = t.encode('latin-1')
        except UnicodeEncodeError:
            continue
        if len(b) % 2:
            continue
        u = b.decode('utf-16-be', 'replace'); sc = _cjk(u) / max(1, len(u))
        if sc > bs + 0.2:
            best, bs = u, sc
    return best


def pdf_pages(path):
    try:
        import fitz  # PyMuPDF
        d = fitz.open(path)
        return [p.get_text() for p in d]
    except ImportError:
        pass
    try:
        import pypdf
        return ['\n'.join(_ucs2(l) for l in (p.extract_text() or '').split('\n')) for p in pypdf.PdfReader(path).pages]
    except ImportError:
        pass
    if shutil.which('pdftotext'):
        r = subprocess.run(['pdftotext', '-enc', 'UTF-8', path, '-'], capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode('utf-8', 'replace').split('\f')[:-1] or ['']
    return None


def reflow(text):
    """PDF 一页的文字：去页码，把排版折行接回成段；以句末标点、列表编号判断段落边界。"""
    rows = [clean(x) for x in text.split('\n')]
    rows = [x for x in rows if x and not PAGENO.match(x)]
    out = []
    for x in rows:
        starts_new = bool(re.match(r'^([一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）|\d+[.、．]|第[一二三四五六七八九十百\d]+[条章节]|[①-⑳])', x))
        if out and not starts_new and out[-1][-1] not in END and len(out[-1]) >= 12:
            out[-1] += x
        else:
            out.append(x)
    return out


def pdf_lines(path):
    pages = pdf_pages(path)
    if pages is None:
        return None, None, None
    out, blank = [], []
    for i, t in enumerate(pages, 1):
        ls = reflow(t or '')
        body = ''.join(ls)
        if len(body) < 15:
            blank.append(i)
            out.append(f'#第{i}页：没有文字层，需看图识读')
            continue
        odd = sum(1 for c in body if not (c.isascii() or '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' or '\uff00' <= c <= '\uffef' or c in '“”‘’—…·×√'))
        if odd > len(body) * 0.06:
            blank.append(i)
            out.append(f'#第{i}页：文字层有乱码（约 {odd} 处），需对照原件看图识读；以下为抽出的文字，仅供定位')
        else:
            out.append(f'#第{i}页')
        out += ls
    return out, len(pages), blank


def read_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.txt', '.md', '.csv'):
        raw = open(path, 'rb').read()
        for enc in ('utf-8-sig', 'gb18030'):
            try:
                t = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        return [clean(x) for x in t.splitlines() if clean(x)], None, []
    if ext == '.docx':
        return docx_lines(path)
    if ext == '.xlsx':
        return xlsx_lines(path)
    if ext == '.pdf':
        return pdf_lines(path)
    if ext in IMG:
        return ['#图片：需看图识读'], 1, [1]
    return None, None, None


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    src = os.path.abspath(sys.argv[1])
    work = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(src, '_案件看板')
    os.makedirs(os.path.join(work, '原文'), exist_ok=True)
    mf = os.path.join(work, '清单.json')
    old = json.load(open(mf, encoding='utf-8')) if os.path.exists(mf) else {'sources': []}
    known = {(s['file'], s['size']): s for s in old['sources']}
    n = max([int(s['id'][1:]) for s in old['sources']] or [0])
    files = []
    for dp, dn, fn in os.walk(src):
        if os.path.abspath(dp).startswith(work):
            continue
        dn.sort()
        for f in sorted(fn):
            if f.startswith(('.', '~$')) or f.endswith('.zip'):
                continue
            files.append(os.path.join(dp, f))
    sources, report = [], []
    for p in files:
        rel = os.path.relpath(p, src); size = os.path.getsize(p)
        if (rel, size) in known:
            sources.append(known[(rel, size)]); report.append(f'  {known[(rel, size)]["id"]}  {rel}（已入库，跳过）'); continue
        lines, pages, blank = read_file(p)
        if lines is None:
            report.append(f'  ——  {rel}：读不了（{os.path.splitext(p)[1]} 格式，或 PDF 没有可用的读取工具），请另存为 PDF/Word/文本后重跑，或由 Agent 直接识读'); continue
        n += 1; sid = f'S{n:02d}'
        s = {'id': sid, 'file': rel, 'size': size, 'pages': pages, 'blank_pages': blank or [], 'lines': lines}
        sources.append(s)
        name = re.sub(r'[\\/:*?"<>|]', '_', os.path.splitext(os.path.basename(rel))[0])[:40]
        with open(os.path.join(work, '原文', f'{sid}_{name}.txt'), 'w', encoding='utf-8') as fh:
            info = f'{pages} 页' if pages else f'{len(lines)} 行'
            if blank:
                info += f'；第 {"、".join(map(str, blank))} 页没有文字层或有乱码，需看图识读'
            fh.write(f'# {sid}　{rel}（{info}）\n# 引用时写：src 为 {sid}，ln 为行号\n')
            for i, l in enumerate(lines, 1):
                fh.write(f'{i:04d}｜{l}\n')
        report.append(f'  {sid}  {rel}：{len(lines)} 行' + (f'，{pages} 页' if pages else '') + (f'，第 {"、".join(map(str, blank))} 页没有文字层或有乱码，需看图识读' if blank else ''))
    json.dump({'sources': sources}, open(mf, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'入库 {len(sources)} 个文件 → {work}')
    print('\n'.join(report))
    print('\n下一步：逐份读「原文」文件夹里的 txt（行号即 ln），写 事实.json，再运行 make.py。')


if __name__ == '__main__':
    main()

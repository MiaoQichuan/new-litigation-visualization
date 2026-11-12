"""生成材料 pageImages 的单页对象，保留原件。PDF 页码从 1 开始。"""
import argparse
import base64
import json
from pathlib import Path


def image_bytes(path, page):
    ext = path.suffix.lower()
    if ext in ('.jpg', '.jpeg', '.png'):
        return ('png' if ext == '.png' else 'jpeg'), path.read_bytes()
    if ext != '.pdf':
        raise ValueError('请指定 PDF、PNG 或 JPEG')
    try:
        import pymupdf
    except ImportError as exc:
        raise ValueError('读取 PDF 需要 PyMuPDF。也可传入已截取的 PNG 或 JPEG。') from exc
    with pymupdf.open(path) as pdf:
        if page > len(pdf):
            raise ValueError(f'第 {page} 页超出原始 PDF 的 {len(pdf)} 页')
        pix = pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
        return 'jpeg', pix.tobytes('jpeg', jpg_quality=86)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('page', type=int, help='原件页码，从 1 开始')
    parser.add_argument('--label', help='如「借款合同签署页」')
    parser.add_argument('--why', help='应核对的区域、字段与识读疑点')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出单页 JSON 的新路径')
    args = parser.parse_args()
    if args.page < 1:
        parser.error('原件页码至少是 1')
    try:
        fmt, data = image_bytes(args.file, args.page)
        obj = {'page': args.page, 'data': f'data:image/{fmt};base64,' + base64.b64encode(data).decode('ascii')}
        if args.label:
            obj['label'] = args.label
        if args.why:
            obj['why'] = args.why
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(obj, output, ensure_ascii=False)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()

"""V8 色板：灰阶底；991B 只表示「关键事实与选中」；Claude 陶土色表示「冲突／待审」；选中区域用沉稳的墨蓝。"""
import re, colorsys
KEEP={'002FA7','3C6DB4','14897F','5A4DB3','C9961E','3A8445','C24E7C','8E4FA0','3D4B5E','8E8C85','8A7352','991B1B'}
FIX={  # 精确指定
 'F2A50C':'D97757','F0A020':'D97757','C98A16':'991B1B',            # 冲突点 / 关键星
 '8A5A06':'A4502F','7A5108':'A4502F','7A4E05':'A4502F','6E4C0B':'8F4428','B7790F':'B85F3E',
 'FFF6DB':'F7ECEC','F0D78A':'E2BDBD','FFE7A3':'EFD3D3',            # 关键按钮用 991B 浅色
 '346ED6':'2F5A8F','3E6FD6':'2F5A8F','2457B8':'27507F','1F5CB8':'27507F',
}
def hx(h): return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
def tohex(rgb): return ''.join('%02X'%round(max(0,min(1,c))*255) for c in rgb)
def remap(h):
  h=h.upper()
  if h in KEEP: return h
  if h in FIX: return FIX[h]
  r,g,b=hx(h); H,L,S=colorsys.rgb_to_hls(r,g,b); deg=H*360
  if S<.25 or L>.985: return h
  if 200<=deg<=232:   # 蓝 → 墨蓝
    return tohex(colorsys.hls_to_rgb(213/360,L,min(S,.42 if L<.7 else .38)))
  if 28<=deg<=52:     # 琥珀 → 陶土
    return tohex(colorsys.hls_to_rgb(16/360,L,min(S,.62 if L<.7 else .58)))
  return h
def rgba(m):
  r,g,b=int(m.group(1)),int(m.group(2)),int(m.group(3))
  n=remap('%02X%02X%02X'%(r,g,b)); return 'rgba(%d,%d,%d,'%(int(n[0:2],16),int(n[2:4],16),int(n[4:6],16))
def apply(s):
  s=re.sub(r'#([0-9A-Fa-f]{6})\b',lambda m:'#'+remap(m.group(1)),s)
  s=re.sub(r'rgba\((\d+),\s*(\d+),\s*(\d+),',rgba,s)
  return s

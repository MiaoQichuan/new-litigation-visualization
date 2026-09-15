#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图 · 几何与校验。零第三方依赖。
所有位置都算得出来：栏位、行组、通道、落点四级栅格，走线只在通道里走。
"""
import math

def text_w(t, fs):
    """G1 字宽：中文全宽 = 1.0×字号，西文数字 ≈ 0.5×字号。
    此前按 0.52 一刀切，导致中文卡宽容量算大近一倍、正文溢出卡框。"""
    return sum(fs if ord(c) > 0x2E80 else fs*0.5 for c in t)

def wrap_w(t, maxw, fs):
    """G2 按可用宽度贪心折行，只折不截。"""
    out, cur, w = [], "", 0.0
    for ch in t:
        cw = fs if ord(ch) > 0x2E80 else fs*0.5
        if w + cw > maxw and cur:
            out.append(cur); cur, w = ch, cw
        else:
            cur += ch; w += cw
    if cur: out.append(cur)
    return out or [""]

class Rect:
    __slots__=("x","y","w","h","tag")
    def __init__(s,x,y,w,h,tag=""): s.x,s.y,s.w,s.h,s.tag=x,y,w,h,tag
    def hit_seg(s, x0,y0,x1,y1, pad=0.0):
        """线段是否穿过本矩形（只处理正交段）。"""
        X0,X1=min(x0,x1),max(x0,x1); Y0,Y1=min(y0,y1),max(y0,y1)
        return not (X1 < s.x-pad or X0 > s.x+s.w+pad or Y1 < s.y-pad or Y0 > s.y+s.h+pad)

class Channels:
    """G3 通道：栏间距被切成固定 lane。R2 从内侧起编号，R3 从外侧起编号，
    两者不共用同一 lane；用满即拒绝出图。"""
    def __init__(s, x_lo, x_hi, lane_w, keep):
        s.lo, s.hi, s.lw = x_lo+keep, x_hi-keep, lane_w
        s.cap = max(1, int((s.hi-s.lo)//lane_w)+1)
        s.inner, s.outer = 0, 0
    def take(s, kind, from_left):
        """R2 从通道中心向两侧展开（贴边的折线是扁 Z，不好看）；R3 不走栏间通道。"""
        if s.inner >= s.cap:
            raise RuntimeError(f"G3 通道用满：容量 {s.cap}")
        i = s.inner; s.inner += 1
        mid = (s.lo + s.hi)/2
        off = ((i+1)//2) * s.lw * (1 if i % 2 else -1)
        return mid + off

class Ports:
    """G4 落点：先数清这条边要落几个点，再由边长反解间距——不是先定间距再看够不够。
    need 为需落点数；间距 = (可用边长)/(need-1)，并以 pitch_max 封顶避免过疏。"""
    def __init__(s, y0, y1, need, keep, pitch_max):
        s.a, s.b = y0+keep, y1-keep
        need = max(1, need)
        s.p = min(pitch_max, (s.b-s.a)/(need-1)) if need > 1 else 0.0
        s.cap = need
        s.top, s.bot = 0, 0
    def take(s, kind):
        if s.top + s.bot >= s.cap:
            raise RuntimeError(f"G4 落点用满：容量 {s.cap}")
        if kind == "R3":
            j = s.bot; s.bot += 1; return s.b - j*s.p
        i = s.top; s.top += 1
        return s.a + i*s.p if s.cap > 1 else (s.a+s.b)/2

def verify(rects, paths, pad=1.0):
    """G5 自证：任何走线不得穿过非端点卡片。返回违规清单。"""
    bad=[]
    for pid, pts, endpoints in paths:
        for i in range(len(pts)-1):
            (x0,y0),(x1,y1)=pts[i],pts[i+1]
            for r in rects:
                if r.tag in endpoints: continue
                if r.hit_seg(x0,y0,x1,y1,pad):
                    bad.append((pid, r.tag, f"段{i}"))
    return bad

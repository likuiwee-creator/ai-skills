#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mirror_patch.py —— 纯色 / 几何图形类图片（logo、图标、按钮、色块）去水印的「镜像重建」工具。

为什么需要它：
  remove_watermark.py 用的是「可分离插值 + 颗粒叠加」，适合**照片**（渐变、纹理）。
  但如果图是**扁平纯色 / 几何图形**（如圆角方形 logo、纯色按钮、图标），
  插值法会在图形边缘产生接缝/锯齿，反而更难看（实测踩过）。
  这类图应该用「从无水印的一侧镜像覆盖」——只要图形左右（或上下）对称，就是像素级完美。

用法：
  # 1) 先探测对称性，决定从哪一侧镜像
  python mirror_patch.py probe --img logo.png --box 900,900,1024,1024

  # 2) 执行修补（原地会先备份 *_raw.png；也可 --out 输出到新文件）
  python mirror_patch.py patch --img logo.png --box 900,900,1024,1024 --from left --out logo.png

  # 3) 自检：输出水印区域的放大对比图
  python mirror_patch.py patch --img logo.png --box 900,900,1024,1024 --from left --check chk.png

依赖：Pillow + numpy（Windows 用系统 Python D:\\Python\\python.exe）
"""

import argparse
import os
import shutil
import sys

import numpy as np
from PIL import Image


def parse_box(s):
    parts = [int(float(x)) for x in s.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("box 需为 x0,y0,x1,y1")
    return tuple(parts)


def load(path):
    im = Image.open(path)
    mode = im.mode
    return np.array(im.convert("RGB")).astype(np.int16), mode


def fg_mask(a, tol=18):
    """把「与四角背景色不同」的像素视为前景（图形本体）。"""
    corners = np.array([a[2, 2], a[2, -3], a[-3, 2], a[-3, -3]]).astype(np.int16)
    bg = np.median(corners, axis=0)
    diff = np.abs(a - bg).sum(axis=2)
    return diff > tol * 3


def validate_box(a, box):
    H, W = a.shape[0], a.shape[1]
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H):
        print(f"ERR: --box {box} 超出图片尺寸 {W}x{H}；请用图片实际像素坐标（右下角水印通常接近 W,H）。",
              file=sys.stderr)
        sys.exit(2)


def probe(a, box):
    validate_box(a, box)
    x0, y0, x1, y1 = box
    H, W = a.shape[0], a.shape[1]
    h, w = y1 - y0, x1 - x0
    m = fg_mask(a)
    print("== 对称性探测 ==")
    print(f"  图片 {W}x{H}；box={box}（{w}x{h}）")

    # 左右对称：整幅图中线两侧的前景掩码应互为镜像
    cx = W // 2
    half = min(cx, W - cx)
    left = m[y0:y1, cx - half: cx]
    right = m[y0:y1, cx: cx + half][:, ::-1]
    bad_h = int((left != right).sum())
    tot_h = left.size

    # 上下对称：box 上方等大区域上下翻转后应等于 box 本身
    bad_v = -1
    if y0 - h >= 0:
        up = m[y0 - h: y0, x0:x1][::-1]
        bad_v = int((up != m[y0:y1, x0:x1]).sum())
    tot_v = h * w

    print(f"  左右镜像差异像素：{bad_h} / {tot_h}（{bad_h / max(1, tot_h) * 100:.2f}%）")
    print(f"  上下镜像差异像素：{bad_v} / {tot_v}" + ("" if bad_v >= 0 else "  （上方空间不足，未测）"))
    print("  建议：")
    if bad_h / max(1, tot_h) < 0.02:
        print("    → 左右基本对称：--from left（水印在右下）/ --from right（水印在左下）可用 ✅")
    else:
        print("    → 左右不够对称；若上下差异很小可用 --from top / --from bottom，否则改用 remove_watermark.py 或缩小 box")
    if 0 <= bad_v <= max(10, tot_v // 100):
        print("    → 上下也几乎对称：--from top / --from bottom 亦可 ✅")


def patch(a, box, src, feather=0):
    validate_box(a, box)
    x0, y0, x1, y1 = box
    a = a.copy()
    h, w = y1 - y0, x1 - x0
    if src == "left":
        if x0 - w < 0:
            print("ERR: 左侧空间不足，改用 --from right", file=sys.stderr)
            sys.exit(2)
        a[y0:y1, x0:x1] = a[y0:y1, x0 - w: x0][:, ::-1]
    elif src == "right":
        if x1 + w > a.shape[1]:
            print("ERR: 右侧空间不足，改用 --from left", file=sys.stderr)
            sys.exit(2)
        a[y0:y1, x0:x1] = a[y0:y1, x1: x1 + w][:, ::-1]
    elif src == "top":
        if y0 - h < 0:
            print("ERR: 上方空间不足，改用 --from bottom", file=sys.stderr)
            sys.exit(2)
        a[y0:y1, x0:x1] = a[y0 - h: y0, x0:x1][::-1, :]
    elif src == "bottom":
        if y1 + h > a.shape[0]:
            print("ERR: 下方空间不足，改用 --from top", file=sys.stderr)
            sys.exit(2)
        a[y0:y1, x0:x1] = a[y1: y1 + h, x0:x1][::-1, :]
    else:
        print("ERR: --from 只能是 left/right/top/bottom", file=sys.stderr)
        sys.exit(2)

    if feather > 0:
        # 只在「镜像接缝」那一侧做线性羽化混合，避免出现硬边
        alpha = np.linspace(0, 1, min(feather, w if src in ("left", "right") else h))
        if src == "left":
            a[y0:y1, x0: x0 + len(alpha)] = (
                a[y0:y1, x0 - len(alpha): x0][:, ::-1] * (1 - alpha)[None, :]
                + a[y0:y1, x0: x0 + len(alpha)] * alpha[None, :]
            ).astype(np.int16)
    return a


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "patch"):
        p = sub.add_parser(name)
        p.add_argument("--img", required=True)
        p.add_argument("--box", required=True, type=parse_box, help="x0,y0,x1,y1")
        if name == "patch":
            p.add_argument("--from", dest="src", required=True,
                           choices=["left", "right", "top", "bottom"])
            p.add_argument("--feather", type=int, default=0)
            p.add_argument("--out", default=None)
            p.add_argument("--check", default=None)
    args = ap.parse_args()

    a, mode = load(args.img)

    if args.cmd == "probe":
        probe(a, args.box)
        return

    dst = args.out or args.img
    if dst == args.img:
        raw = os.path.splitext(args.img)[0] + "_raw.png"
        if not os.path.exists(raw):
            shutil.copy2(args.img, raw)
            print("备份 ->", raw)

    out = patch(a, args.box, args.src, args.feather)
    Image.fromarray(out.astype(np.uint8)).save(dst)
    print(f"已修补 -> {dst}  (from {args.src}, box={args.box})")
    if mode == "RGBA":
        print("提示：原图是 RGBA，本脚本按 RGB 处理；若需保留透明通道请自行拼回 alpha。")

    if args.check:
        x0, y0, x1, y1 = args.box
        pad = 80
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        crop = Image.fromarray(out.astype(np.uint8)).crop((cx0, cy0, x1, y1))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.NEAREST)
        crop.save(args.check)
        print("自检图 ->", args.check, "（放大 2x，人工确认无水印残留 / 无接缝）")


if __name__ == "__main__":
    main()

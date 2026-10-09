# -*- coding: utf-8 -*-
"""纸质文档照片 -> 扫描件（自动找纸张边界 + 裁背景 + 增强 + 输出 A4 JPG/PDF）

用法:
  python photo_to_scan.py 输入图片 [--rotate 90] [--outdir DIR] [--name NAME]
                            [--box x0,y0,x1,y1] [--dark-thr 110] [--no-enhance]

依赖: Pillow + numpy（用 D:\\Python\\python.exe 运行）
"""
import argparse
import os
import sys

from PIL import Image, ImageEnhance, ImageOps
import numpy as np

A4_RATIO = 210.0 / 297.0          # 0.7071
A4_W, A4_H = 1654, 2339           # A4 @ 200dpi
RATIO_TOL = 0.06                  # 宽高比容差


def longest_run(mask, max_gap=0):
    """最长连续 True 段；max_gap>0 时允许段内出现不超过 max_gap 个连续 False
    （纸面上密集的表格线/阴影会让个别行误判为背景，必须容忍空洞）
    返回 (length, start, end)
    """
    n = len(mask)
    best = (0, 0, 0)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        last_true = i
        while j < n:
            if mask[j]:
                last_true = j
                j += 1
                continue
            k = j
            while k < n and not mask[k]:
                k += 1
            if k - j > max_gap or k >= n:
                break
            j = k
        if last_true - i + 1 > best[0]:
            best = (last_true - i + 1, i, last_true + 1)
        i = last_true + 1
    return best


def detect_paper_box(gray, dark_thr=110, low=0.55, high=0.72, margin=2):
    """按行/列暗像素比例定位纸张矩形。返回 (x0,y0,x1,y1) 或 None"""
    dark = gray < dark_thr

    def scan(arr):
        # arr: 每行或每列的暗像素比例
        cand = arr < low
        # 必须存在少量"高暗比例"区域，否则说明背景不是深色（此法不适用）
        if (arr > high).sum() < 3:
            return None
        ln, s, e = longest_run(cand, max_gap=40)
        return (s, e) if ln > 0.3 * len(arr) else None

    cols = scan(dark.mean(axis=0))
    rows = scan(dark.mean(axis=1))
    if not cols or not rows:
        return None

    x0, x1 = cols[0] + margin, cols[1] - margin
    y0, y1 = rows[0] + margin, rows[1] - margin
    if x1 - x0 < 50 or y1 - y0 < 50:
        return None

    ratio = (x1 - x0) / float(y1 - y0)
    ok = abs(ratio - A4_RATIO) / A4_RATIO < RATIO_TOL
    print("detect box: (%d,%d)-(%d,%d)  ratio=%.4f (A4=%.4f) %s"
          % (x0, y0, x1, y1, ratio, A4_RATIO, "OK" if ok else "!! ratio off, review"))
    return (x0, y0, x1, y1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                    help="逆时针旋转角度")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--box", default=None, help="手动指定 x0,y0,x1,y1，跳过自动检测")
    ap.add_argument("--dark-thr", type=int, default=110)
    ap.add_argument("--no-enhance", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.src):
        print("ERR: not found " + a.src)
        return 1

    outdir = a.outdir or os.path.dirname(os.path.abspath(a.src))
    os.makedirs(outdir, exist_ok=True)
    base = a.name or os.path.splitext(os.path.basename(a.src))[0]

    im = ImageOps.exif_transpose(Image.open(a.src)).convert("RGB")
    print("opened: %s  size=%s" % (a.src, im.size))

    if a.rotate:
        im = im.transpose({90: Image.ROTATE_90, 180: Image.ROTATE_180,
                           270: Image.ROTATE_270}[a.rotate])
        print("rotated %d ccw -> %s" % (a.rotate, im.size))

    # 先落一张旋转原图，供人工确认方向
    rot_preview = os.path.join(outdir, base + "_rot.png")
    im.save(rot_preview)

    gray = np.asarray(im.convert("L"), dtype=np.float32)

    if a.box:
        box = tuple(int(v) for v in a.box.split(","))
        print("manual box:", box)
    else:
        box = detect_paper_box(gray, dark_thr=a.dark_thr)
        if box is None:
            print("WARN: 自动检测失败（可能是亮色背景）。已输出旋转预览，"
                  "请确认方向后用 --box 手动指定裁剪范围。")
            return 2

    page = im.crop(box)
    print("cropped: %s  ratio=%.4f" % (page.size, page.size[0] / float(page.size[1])))

    if not a.no_enhance:
        page = ImageEnhance.Contrast(page).enhance(1.18)
        page = ImageEnhance.Brightness(page).enhance(1.05)
        page = ImageEnhance.Sharpness(page).enhance(1.30)

    target_h = int(round(A4_W * page.size[1] / float(page.size[0])))
    page = page.resize((A4_W, target_h), Image.LANCZOS)

    jpg = os.path.join(outdir, base + ".jpg")
    pdf = os.path.join(outdir, base + ".pdf")
    page.save(jpg, "JPEG", quality=90, optimize=True, dpi=(200, 200))
    page.save(pdf, "PDF", resolution=200.0)

    chk = os.path.join(outdir, base + "_check.png")
    page.resize((827, int(827 * page.size[1] / page.size[0]))).save(chk)

    for p in (jpg, pdf, chk, rot_preview):
        print("  %s  %.1f KB" % (p, os.path.getsize(p) / 1024.0))
    print("NEXT: 打开 %s 目视校验（纸完整 / 无桌面残留 / 字章清晰）" % chk)
    return 0


if __name__ == "__main__":
    sys.exit(main())

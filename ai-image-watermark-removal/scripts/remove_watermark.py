# -*- coding: utf-8 -*-
"""
去除 AI 生图右下角水印（"AI生成 / WORKBUDD>" 之类）—— 无缝修补版

原理（比整块搬运稳得多）：
  1. 包围盒右/下边对齐图像边缘 → 该两侧天然无缝，只需处理左/上边
  2. 用盒子上边一行 T(x) 与左边一列 L(y) 构造可分离背景场
     F(x,y) = T(x) + L(y) - T(x0)
     对纵向/横向渐变背景可完美贴合，不会带进错误亮度（摄影/投影暗带尤其明显）
  3. 从盒子上方取同宽区域做像素级高通（半径~1.8，只留颗粒不带结构）叠加，
     并按盒子左侧邻近区的噪声强度自适应缩放，避免"塑料感"或过强噪点
  4. 左/上边宽羽化（默认 30px）融合，消除可见方框边界
  ⚠ 羽化宽度必须小于"盒子边缘到水印"的距离，否则会把水印混回来（脚本会自检）

用法：
  python remove_watermark.py 图1.png 图2.jpg ...            # 自动按比例定位，原地覆盖
  python remove_watermark.py --outdir cleaned 图1.png       # 输出到 cleaned/
  python remove_watermark.py --box 1385,933,1536,1024 图.png  # 手动指定包围盒
  python remove_watermark.py --feather 30 --check 图.png     # 另存 _check.png 供肉眼复核

依赖：Pillow + numpy（Windows 常用系统 Python：D:\\Python\\python.exe）
"""
import os, sys, shutil, argparse
import numpy as np
from PIL import Image, ImageFilter

# 实测（1536x1024 的 AI 生图）：水印占据右下角约 8% 宽 × 7% 高
# 盒子按比例给出，右/下顶到图像边缘
BOX_RATIO = (0.90, 0.91, 1.00, 1.00)
FEATHER_RATIO = 0.020   # 羽化宽度 ≈ 2% 图宽；须 < 盒子边缘到水印的距离


def _gauss(a, r):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r))).astype(np.float32)


def auto_box(w, h):
    x0, y0, x1, y1 = BOX_RATIO
    return (int(w * x0), int(h * y0), int(w * x1), int(h * y1))


def remove(path, box=None, feather=None, out=None, check=False, offset=(0, 0)):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    x0, y0, x1, y1 = box or auto_box(W, H)
    # 微调（同一批图水印位置略有偏移时用）
    x0 += offset[0]; x1 += offset[0]; y0 += offset[1]; y1 += offset[1]
    x0 = max(0, x0); y0 = max(0, y0); x1 = min(W, x1); y1 = min(H, y1)
    FE = feather if feather is not None else max(10, int(W * FEATHER_RATIO))
    bw, bh = x1 - x0, y1 - y0

    arr = np.asarray(im).astype(np.float32)
    T = arr[y0 - 1, x0:x1]
    L = arr[y0:y1, x0 - 1]
    F = T[None, :, :] + L[:, None, :] - T[0][None, None, :]          # 可分离背景场

    sy1 = y0 - 4
    src = arr[max(0, sy1 - bh):sy1, x0:x1]
    tex = src - _gauss(src, 1.8)
    nb = arr[y0:y1, max(0, x0 - bw):x0]
    s_loc = float((nb - _gauss(nb, 1.8)).std())
    s_tex = float(tex.std()) + 1e-6
    F = np.clip(F + tex * min(1.0, s_loc / s_tex), 0, 255)

    m = np.ones((bh, bw), dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, max(1, FE), dtype=np.float32)
    fx = min(FE, bw); fy = min(FE, bh)
    m[:, :fx] = np.minimum(m[:, :fx], ramp[:fx][None, :])
    m[:fy, :] = np.minimum(m[:fy, :], ramp[:fy][:, None])
    mask = Image.fromarray((m * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(4))
    a = np.asarray(mask).astype(np.float32)[..., None] / 255.0

    arr[y0:y1, x0:x1] = F * a + arr[y0:y1, x0:x1] * (1 - a)
    out_im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    dst = out or path
    out_im.save(dst, "PNG" if dst.lower().endswith(".png") else "JPEG",
                **({} if dst.lower().endswith(".png") else {"quality": 92}))
    print(f"  {os.path.basename(path)} -> {dst}   box=({x0},{y0})-({x1},{y1})  feather={FE}")
    if check:
        c = out_im.crop((max(0, x1 - int(W * 0.30)), max(0, y1 - int(H * 0.24)), x1, y1))
        c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
        cp = os.path.splitext(dst)[0] + "_check.png"
        c.save(cp)
        print(f"     自检图 -> {cp}（右下角放大 2x，人工确认无方框/亮度差）")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--box", help="x0,y0,x1,y1（默认按比例自动定位）")
    ap.add_argument("--offset", default="0,0", help="包围盒微调 dx,dy")
    ap.add_argument("--feather", type=int, default=None)
    ap.add_argument("--outdir")
    ap.add_argument("--suffix", default="", help="输出文件名后缀（默认原地覆盖）")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()

    box = tuple(int(v) for v in a.box.split(",")) if a.box else None
    off = tuple(int(v) for v in a.offset.split(","))
    for f in a.files:
        if not os.path.isfile(f):
            print(f"  [MISS] {f}"); continue
        if a.no_backup is False and not a.outdir:
            bak = os.path.splitext(f)[0] + "_raw" + os.path.splitext(f)[1]
            if not os.path.exists(bak):
                shutil.copy2(f, bak); print(f"  备份 -> {os.path.basename(bak)}")
        if a.outdir:
            os.makedirs(a.outdir, exist_ok=True)
            base, ext = os.path.splitext(os.path.basename(f))
            dst = os.path.join(a.outdir, base + a.suffix + ext)
        else:
            base, ext = os.path.splitext(f)
            dst = base + a.suffix + ext
        remove(f, box=box, feather=a.feather, out=dst, check=a.check, offset=off)


if __name__ == "__main__":
    main()

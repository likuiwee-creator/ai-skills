"""
Yidun 缺口定位 v3 —— 轮廓匹配（抗明暗变化）
原生像素 1:1，无缩放误差。
输出: DRAG_CSS
"""
import numpy as np
import scipy.ndimage as ndi
from PIL import Image, ImageDraw


def main():
    bg = np.array(Image.open('D:/tmp_cc/_raw_bg.png').convert('RGB')).astype(float)
    jig = np.array(Image.open('D:/tmp_cc/_raw_jig.png'))
    alpha = jig[:, :, 3] > 128

    ys, xs = np.where(alpha)
    ax0, ax1, ay0, ay1 = xs.min(), xs.max(), ys.min(), ys.max()
    msk = alpha[ay0:ay1 + 1, ax0:ax1 + 1].astype(bool)
    mh, mw = msk.shape

    gray = bg.mean(axis=2)
    H, W = gray.shape
    gy, gx = np.gradient(ndi.gaussian_filter(gray, 1.0))
    grad = np.hypot(gx, gy)

    er = ndi.binary_erosion(msk, iterations=3)
    contour = msk & (~er)
    interior = ndi.binary_erosion(msk, iterations=6)
    if interior.sum() < 50:
        interior = er

    rows = []
    for mx in range(0, W - mw + 1):
        g = grad[ay0:ay0 + mh, mx:mx + mw]
        c = g[contour].mean()
        i = g[interior].mean()
        rows.append((c - 0.45 * i, mx, c, i))
    rows.sort(reverse=True)

    print('top by contour score:')
    for r in rows[:8]:
        print('  score=%.2f mx=%d contour=%.1f interior=%.1f' % r)

    best = rows[0]
    mx = best[1]
    drag = mx - ax0
    print('GAPX=%d ALPHA_X0=%d PIECE_PNG_W=%d DRAG_CSS=%.1f' % (mx, ax0, 60, drag))

    im = Image.open('D:/tmp_cc/_raw_bg.png').convert('RGB')
    d = ImageDraw.Draw(im)
    cols = [(255, 0, 0), (0, 255, 0), (0, 128, 255)]
    seen = []
    for i, r in enumerate(rows):
        x = r[1]
        if any(abs(x - s) < 12 for s in seen):
            continue
        seen.append(x)
        d.rectangle([x, ay0, x + mw, ay0 + mh], outline=cols[len(seen) - 1], width=1)
        if len(seen) >= 3:
            break
    im.resize((W * 3, H * 3), Image.NEAREST).save('D:/tmp_cc/_match_check.png')


if __name__ == '__main__':
    main()

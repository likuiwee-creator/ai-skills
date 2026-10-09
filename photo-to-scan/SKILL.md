---
name: photo-to-scan
description: 把手机拍的纸质文档照片处理成干净的扫描件——自动旋转回正、检测纸张边界并裁掉背景、增强清晰度，输出 A4 比例的 JPG + PDF。当用户发来合同/授权书/盖章文件/签章页/发票等拍照图，要求"处理成扫描件/转正/裁剪/转PDF/上传用/清晰一点"时使用。含无 OpenCV 环境下（纯 numpy/scipy）的纸张边界检测法与踩坑记录。
agent_created: true
---

# 纸质文档照片 → 扫描件

## 适用场景
- 用户发来手机拍的纸质文件（盖章件、签章页、合同、发票、证明材料），要"弄干净/转正/裁一下/转成 PDF"
- 后续要上传到政务/申报平台，不能有桌面背景、不能是歪的、字要清楚

## 环境（重要）
用 **`D:\Python\python.exe`** 跑脚本 —— 它有 Pillow + numpy + scipy。
⚠️ managed python（`C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`）
**没有 PIL / numpy / scipy**，但有 pymupdf。别搞混：图像处理走 D:\Python，PDF 文本提取走 managed。

## 快速用法
```bash
D:\Python\python.exe "<skill>/scripts/photo_to_scan.py" "输入图片路径" --rotate 90 --name 输出名
```
参数：
- `--rotate 0|90|180|270`：**逆时针**旋转角度（多数手机横拍纸张时需要 90）
- `--outdir`：输出目录（默认与输入同目录）
- `--name`：输出文件名前缀（默认源文件名）
- 输出：`<name>.jpg`（quality 90）+ `<name>.pdf`（A4 200dpi）+ `_check.png`（缩略校验图）

## 流程（照做，别跳步）
1. `exif_transpose` 先按 EXIF 摆正
2. **定旋转方向：不要猜。** 生成 ROTATE_90 / ROTATE_270 两版，各存一张，**读图确认哪版文字正立**再继续
3. **定纸张边界**：用「暗像素比例法」
   - 手机拍纸通常放在深色桌面上 → 桌面 `gray < 110`，纸面亮
   - 逐行/逐列统计 `(gray < 110).mean()`：纸所在行/列该比例低（≈0.1），桌面行/列高（>0.8）
   - 取**最长连续低比例段**作边界；左右/上下各留 2px 余量
   - **自检**：算出宽高比应贴近 A4 的 `0.707`（±5%）。偏太多说明边界错了，回到步骤 2/3 复查
4. `crop` → 温和增强：`Contrast 1.18` / `Brightness 1.05` / `Sharpness 1.30`
   （别过度：公章红色会被拉爆、手写笔迹会糊）
5. `resize` 到 A4 200dpi：`1654 x 2339`（按检测比例微调），`LANCZOS`
6. 输出 JPG（quality 90，含 dpi）+ PDF（`save(..., "PDF", resolution=200)`）
7. **必做**：把结果缩略图读一遍，确认①纸张完整、四角无桌面残留 ②文字/公章清晰可辨。不要盲信坐标算出来的结果

## 踩过的坑
- ❌ **`gray > 150` 阈值 + 最大连通域找纸张**：纸面表格线、渐变阴影会把白区切成多块，最大连通域可能只占 25%，bbox 也不对。用上面第 3 步的「按行/列统计比例」法。
- ❌ **手填四角坐标做透视变换**：目测几乎必偏（曾把右边界少写 220px，结果整页被放大裁掉）。先用比例法得到矩形边界；手机正对拍摄时透视很轻，**直接裁剪即可**，不必强行透视校正。
- ❌ **靠目测判断图片是横的还是竖的**：容易把表格框线误当纸边。以第 3 步量出来的数值为准。
- ⚠️ 生成后如果底部/边缘还残留深色桌面带，说明下/右边界多留了 2–6px，回退一点重出即可。
- ⚠️ 输出 JPG 前确认平台限制（政务类平台常见 2MB / 10MB 上限；405KB 的 A4 200dpi 扫描件是安全值）。
- ⚠️ **上传平台可能只吃 PDF 不吃 JPG**（如中国版权保护中心签章页），所以两个格式都出一份，先试 PDF。

## 背景明暗混杂时（自动检测必失败）怎么办
典型场景：执照/文件放在桌上，**上半部是深色木纹、下半部是浅色台面**（或还有反光的亮木区）。
此时「暗像素比例法」失效（不存在整行/整列都高暗比例的区域），脚本会返回 `WARN: 自动检测失败`。

**别硬调阈值，换这两招（实测 5 分钟搞定）：**

1. **画网格目视读坐标**（最可靠）
   ```python
   from PIL import Image, ImageDraw
   im = Image.open(src).convert("RGB"); W,H = im.size
   d = ImageDraw.Draw(im)
   for x in range(0,W,100): d.line([(x,0),(x,H)],fill=(255,0,0),width=2); d.text((x+3,6),str(x),fill=(255,0,0)); d.text((x+3,H-40),str(x),fill=(255,0,0))
   for y in range(0,H,100): d.line([(0,y),(W,y)],fill=(0,0,255),width=2); d.text((4,y+3),str(y),fill=(0,0,255)); d.text((W-70,y+3),str(y),fill=(0,0,255))
   im.save("grid.png")
   ```
   然后 **Read 这张 grid.png**，直接读出证件四边的像素坐标。

2. **逐列扫边框线定上下边**（比看网格更精确）
   证件四周有边框线（比纸面暗），从外往里扫首个 `gray < 185` 的点即是边框：
   ```python
   g = np.asarray(Image.open(src).convert("L"), dtype=np.float32)
   def first_dark_below(x, y0, y1, thr=185):
       for y in range(y0, y1):
           if g[y,x] < thr: return y
   def first_dark_above(x, y0, y1, thr=185):
       for y in range(y0, y1, -1):
           if g[y,x] < thr: return y
   # 每 80px 取一列，polyfit 出斜率 → 顺便知道有没有倾斜
   ```
   注意排除标题/国徽等突出元素造成的离群点（拟合时直接肉眼剔除）。

3. **裁切直接手写**，不必用脚本的 `--box`（脚本会强制 resize 到 1654 宽，**小图会被放大反而变糊**）。
   自己 `Image.open(src).crop(box)` → `ImageEnhance` 轻度增强（Contrast 1.15 / Brightness 1.04 / Sharpness 1.35，别过头，公章红色会爆）→
   以 **quality 92、dpi=(300,300)、保持原分辨率** 存 JPG。1280×940 的裁切图约 190KB，远低于 10MB 上限。

4. **文件名用 ASCII**：`setInputFiles`/上传控件的路径带中文偶发失败 → 复制一份 `license_scan.jpg` 类名字再传。

## 相关
- 该文档要上传到中国版权保护中心（软著）时，见 skill `soft-copyright-progress`

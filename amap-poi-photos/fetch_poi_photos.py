# -*- coding: utf-8 -*-
"""
高德 POI 实景图批量抓取
--------------------------------------------------
用法：
  python fetch_poi_photos.py --key <高德Web服务Key> --city 上海 \
         --names names.json --out ./out [--width 800] [--quality 86] [--force]

输入：names.json（["上海野生动物园", ...]）或 names.txt（每行一个名称）
输出：
  <out>/images/<名称>.jpg      居中裁切 4:3 + 压缩后的图片
  <out>/poi_photos.json        映射表 {名称: {file, poi, src, size, matched}}
  <out>/poi_photos_report.txt  成功/失败/疑似误配 + 质量分级

依赖：requests（或标准库 urllib）、Pillow
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    from PIL import Image
except ImportError:
    print("缺少 Pillow，请先安装：pip install Pillow")
    sys.exit(1)

API = "https://restapi.amap.com/v3/place/text"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

CITY_PREFIX = ["上海", "北京", "广州", "深圳", "杭州", "南京", "苏州", "成都",
               "重庆", "武汉", "西安", "天津", "青岛", "厦门", "长沙", "昆明", "郑州"]
NAME_SUFFIX = ["景区", "乐园", "度假区", "观光厅", "博物馆", "纪念馆", "文化村",
               "生态园", "植物园", "动物园", "森林公园", "古镇", "园林", "公园"]

# 允许出现在文件名中的字符（Windows 非法字符剔除）
ILLEGAL = r'\\/:*?"<>|'


def safe_name(s):
    return "".join(c for c in s if c not in ILLEGAL).strip()


def city_stripped(name, city):
    for p in ([city] if city else []) + CITY_PREFIX:
        if p and name.startswith(p):
            return name[len(p):]
    return name


def build_queries(name, city):
    """多策略搜索词：原名 → 去城市前缀 → 再去后缀（核心词≥3字才用）"""
    qs = [name]
    core = city_stripped(name, city)
    if core and core != name:
        qs.append(core)
    for suf in NAME_SUFFIX:
        if core.endswith(suf) and len(core) - len(suf) >= 3:
            qs.append(core[:-len(suf)])
            break
    out, seen = [], set()
    for q in qs:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def match_level(poi_name, target, city):
    """返回匹配等级：strict（名称互相包含）/ loose（核心词命中）/ none"""
    if not poi_name:
        return "none"
    if target in poi_name or poi_name in target:
        return "strict"
    core = city_stripped(target, city)
    if core and (core in poi_name or poi_name in core):
        return "strict"
    if core and (core[:3] in poi_name or poi_name[:3] in core):
        return "loose"
    return "none"


def search_photos(key, kw, city, offset=20):
    """调用 place/text，返回 [(poi_name, photo_url), ...]"""
    params = {"key": key, "keywords": kw, "city": city or "",
              "offset": offset, "page": 1, "extensions": "all"}
    url = API + "?" + urllib.parse.urlencode(params)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read()
    data = json.loads(raw.decode("utf-8"))
    if str(data.get("status")) != "1":
        raise RuntimeError("接口返回异常：%s" % data.get("info"))
    out = []
    for p in data.get("pois", []):
        pname = p.get("name") or ""
        for ph in (p.get("photos") or []):
            u = ph.get("url")
            if u:
                out.append((pname, u))
    return out


def download_image(url, timeout=30):
    """优先取原图（?operate=original），失败则退回默认缩略图"""
    tried = []
    base = url.split("?")[0]
    if "operate=original" in url:
        tried = [url, base]
    else:
        tried = [base + "?operate=original", base]
    last_err = None
    for u in tried:
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read()
            if len(raw) < 3000:          # 过小多为占位图
                raise ValueError("图片过小 %d bytes" % len(raw))
            return u, raw
        except Exception as e:
            last_err = e
    raise RuntimeError(str(last_err))


def crop_resize(raw, width=800, quality=86):
    """居中裁切为 4:3，限制到指定宽度，输出 JPEG bytes 与尺寸"""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    target = 4 / 3
    if w / h > target:
        nw = int(h * target)
        x = (w - nw) // 2
        im = im.crop((x, 0, x + nw, h))
    else:
        nh = int(w / target)
        y = (h - nh) // 2
        im = im.crop((0, y, w, y + nh))
    if im.width > width:
        im = im.resize((width, int(width * 3 / 4)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue(), im.size


def grade(w, h):
    m = min(w, h)
    if m >= 600:
        return "A"
    if m >= 400:
        return "B"
    if m >= 300:
        return "C"
    return "D"


def load_names(path):
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="高德 Web服务 Key")
    ap.add_argument("--city", default="", help="城市名，如 上海")
    ap.add_argument("--names", required=True, help="名称列表 json 或 txt")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--quality", type=int, default=86)
    ap.add_argument("--sleep", type=float, default=0.15, help="每次请求间隔秒")
    ap.add_argument("--force", action="store_true", help="忽略已有结果，全部重抓")
    args = ap.parse_args()

    names = load_names(args.names)
    img_dir = os.path.join(args.out, "images")
    os.makedirs(img_dir, exist_ok=True)
    map_path = os.path.join(args.out, "poi_photos.json")

    result = {}
    if os.path.exists(map_path) and not args.force:
        result = json.load(open(map_path, encoding="utf-8"))

    done, failed, loose = [], [], []

    for i, name in enumerate(names, 1):
        if name in result and os.path.exists(os.path.join(args.out, result[name]["file"])):
            continue

        got = None
        for kw in build_queries(name, args.city):
            try:
                for poi_name, url in search_photos(args.key, kw, args.city):
                    lvl = match_level(poi_name, name, args.city)
                    if lvl == "none":
                        continue
                    try:
                        used, raw = download_image(url)
                        jpg, size = crop_resize(raw, args.width, args.quality)
                    except Exception:
                        continue
                    fn = safe_name(name) + ".jpg"
                    with open(os.path.join(img_dir, fn), "wb") as f:
                        f.write(jpg)
                    got = {
                        "file": os.path.join("images", fn).replace("\\", "/"),
                        "poi": poi_name,
                        "src": used,
                        "size": "%dx%d" % size,
                        "grade": grade(*size),
                        "matched": lvl,
                        "kw": kw,
                    }
                    break
                if got:
                    break
            except Exception as e:
                print("  ! %s (kw=%s) %s" % (name, kw, str(e)[:60]))
            time.sleep(args.sleep)

        if got:
            result[name] = got
            flag = "" if got["matched"] == "strict" else "  ← 疑似误配，请复核"
            print("[%d/%d] ✓ %-22s → %-18s %s %s%s"
                  % (i, len(names), name, got["poi"], got["size"], got["grade"], flag))
            if got["matched"] != "strict":
                loose.append((name, got["poi"]))
            done.append(name)
        else:
            print("[%d/%d] ✗ %s  无匹配" % (i, len(names), name))
            failed.append(name)

        json.dump(result, open(map_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 报告 ----------
    grades = {}
    for v in result.values():
        grades[v.get("grade", "?")] = grades.get(v.get("grade", "?"), 0) + 1
    small = [k for k, v in result.items()
             if v.get("size") and min(map(int, v["size"].split("x"))) < 400]

    lines = []
    lines.append("高德 POI 图片抓取报告")
    lines.append("=" * 46)
    lines.append("目标 %d 家 | 成功 %d | 失败 %d" % (len(names), len(result), len(failed)))
    lines.append("质量分级：A(≥600边) %d | B(≥400) %d | C(≥300) %d | D(<300) %d"
                 % (grades.get("A", 0), grades.get("B", 0), grades.get("C", 0), grades.get("D", 0)))
    lines.append("")
    lines.append("【疑似误配 · 需人工复核】")
    lines.extend(["  %s → %s" % (a, b) for a, b in loose] or ["  无"])
    lines.append("")
    lines.append("【抓取失败】")
    lines.extend(["  " + n for n in failed] or ["  无"])
    lines.append("")
    lines.append("【图片偏小（最短边 <400，建议替换）】")
    lines.extend(["  %s  %s" % (k, result[k]["size"]) for k in small] or ["  无"])
    lines.append("")
    if result and len(small) / len(result) > 0.10:
        lines.append("⚠ 偏小比例超过 10%，检查是否漏加 ?operate=original 参数")
    lines.append("提醒：高德 POI 图著作权属高德或其上传者，正式上线建议换授权图/免费图库/UGC")

    report = "\n".join(lines)
    rp = os.path.join(args.out, "poi_photos_report.txt")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)
    print("\n输出：\n  %s\n  %s\n  %s" % (img_dir, map_path, rp))


if __name__ == "__main__":
    main()

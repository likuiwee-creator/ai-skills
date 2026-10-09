# -*- coding: utf-8 -*-
"""
WorkBuddy 大赛网页投稿 —— 参数化模板（有头模式，健壮版）
用法：把下方「投稿参数」替换为本次内容，直接 `python submit_template.py` 运行。
扫码那步会停在可见浏览器窗口，用户扫微信码即可；扫完自动二次提交。
"""
import os, json, time, re

os.environ.pop("NODE_OPTIONS", None)  # 必须：否则 playwright node 驱动因 --use-system-ca 报错

from playwright.sync_api import sync_playwright

# ===================== 投稿参数（每次替换这里） =====================
URL = "https://www.workbuddy.link/p/LpW8we9wQ4oxDpPACkP6Zb"   # 大赛投稿页（以实际为准）
CONTEST_ID = "LpW8we9wQ4oxDpPACkP6Zb"
SHOTS_DIR = r"D:\workbuddy\2026-08-25-17-59-48\contest-screenshots"
PROFILE = r"D:\workbuddy\2026-08-25-17-59-48\pw_profile_headed"
os.makedirs(SHOTS_DIR, exist_ok=True)
os.makedirs(PROFILE, exist_ok=True)

TITLE = "作品名称"
LINK = "https://workbuddy.link/p/你的模板链接"      # 资料库发布的公开模板页
UID = "用户UserID"
NICK = "作者昵称"
PHONE = "手机号"
TAG = "理财记账"                                    # 参赛标签，按实际选
DESC = """作品介绍（多行）。
合规声明：仅用于记录/复盘/统计实验，不预测结果、不保证收益。"""
SHOTS = [os.path.join(SHOTS_DIR, n) for n in ["shot1.png", "shot2.png", "shot3.png"]]  # 1~3 张截图
# ===================== 结束参数 =====================

STATUS = os.path.join(SHOTS_DIR, "headed_submit_status.txt")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(line + "\n")

hp = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "").rstrip("/")
proxy = {"server": hp} if hp else None
log(f"proxy={hp}")

BROWSER = None

def get_frame(page):
    return next((f for f in page.frames if "workbuddy-space-static" in f.url), None)

def find_contest_page():
    for pg in BROWSER.pages:
        if CONTEST_ID in pg.url and "codebuddy" not in pg.url:
            return pg
    return None

def find_login_page():
    for pg in BROWSER.pages:
        if "codebuddy.cn" in pg.url:
            return pg
    return None

def page_text(pg):
    try:
        return pg.evaluate("document.body.innerText") or ""
    except Exception:
        return ""

def open_form(page):
    frame = get_frame(page)
    if not frame:
        return None
    frame.locator("button#pub").first.click()
    page.wait_for_timeout(1500)
    frame.locator("text=我已经做好了，直接投稿").click()
    page.wait_for_timeout(3000)
    return get_frame(page)

def fill_form(frame, page):
    def fill(idv, val):
        el = frame.locator("#" + idv)
        el.scroll_into_view_if_needed()
        el.fill(val)
    fill("fName", TITLE); fill("fUrl", LINK); fill("fRaw", DESC)
    fill("fUid", UID); fill("fAuthor", NICK); fill("fPhone", PHONE)
    frame.locator("#fFile").set_input_files(SHOTS)
    page.wait_for_timeout(2500)
    frame.locator("button.trkb", has_text=TAG).first.click()
    page.wait_for_timeout(500)
    cb = frame.locator("#fOk")
    cb.scroll_into_view_if_needed()
    if not cb.is_checked():
        try:
            frame.locator("label[for='fOk']").first.click(timeout=3000)
        except Exception:
            pass
        try:
            if not cb.is_checked():
                cb.locator("..").click(timeout=3000)
        except Exception:
            pass
        if not cb.is_checked():
            frame.evaluate("""() => { const el=document.querySelector('#fOk'); if(el){ el.checked=true; el.dispatchEvent(new Event('change',{bubbles:true})); } }""")
    log("授权勾选 checked=" + str(cb.is_checked()))

def iframe_text(page):
    try:
        fr = get_frame(page)
        if fr:
            return fr.evaluate("document.body.innerText") or ""
    except Exception:
        pass
    return ""

def has_success(page):
    txt = iframe_text(page)
    return bool(re.search(r"提交成功|投稿成功|已提交|发布成功|等待审核", txt))

def handle_login(lp):
    try:
        btn = lp.locator(".agree-btn").first
        if btn.count() and btn.is_visible(timeout=4000):
            log("点击登录页【同意】按钮")
            btn.click()
            page_wait(lp, 2.5)
    except Exception as e:
        log("同意按钮: " + str(e))
    log("[QR_READY] 可见浏览器窗口已显示微信二维码，请现在扫码（如弹出“选择账号”请点选你的账号）")
    start = time.time()
    while time.time() - start < 540:
        cp = find_contest_page()
        lpg = find_login_page()
        if cp and not lpg:
            log("扫码完成，已回到投稿页")
            return True
        for pg in BROWSER.pages:
            if "选择账号" in page_text(pg):
                log("[提醒] 检测到“选择账号”，请在窗口点选你的账号")
                break
        time.sleep(3)
    log("TIMEOUT 等待扫码")
    return False

def page_wait(pg, secs):
    try:
        pg.wait_for_timeout(int(secs * 1000))
    except Exception:
        time.sleep(secs)

def do_submit_flow(page):
    frame = get_frame(page)
    if not frame:
        log("ERROR do_submit: 无表单")
        return "error"
    log("点击提交 #fSub")
    frame.locator("#fSub").click()
    page_wait(page, 1.5)
    start = time.time()
    while time.time() - start < 90:
        lp = find_login_page()
        if lp:
            ok = handle_login(lp)
            return "need_resubmit" if ok else "timeout"
        if has_success(page):
            return "done"
        time.sleep(2)
    return "unknown"

def main():
    global BROWSER
    with open(STATUS, "w", encoding="utf-8") as f:
        f.write("")
    with sync_playwright() as p:
        BROWSER = p.chromium.launch_persistent_context(
            PROFILE, headless=False, viewport={"width": 1280, "height": 1400},
            proxy=proxy, args=["--use-system-ca", "--ignore-certificate-errors", "--no-sandbox"],
        )
        page = BROWSER.new_page()
        page.on("dialog", lambda d: (log("DIALOG: " + d.message), d.accept()))
        log("打开投稿页（仅一次加载，避免 429）")
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_timeout(4000)
        frame = get_frame(page)
        if not frame:
            log("ERROR: 未找到投稿 iframe")
            BROWSER.close()
            return
        frame = open_form(page)
        if not frame:
            log("ERROR: 打开发布表单失败")
            BROWSER.close()
            return
        fill_form(frame, page)
        page.screenshot(path=os.path.join(SHOTS_DIR, "headed_prefill.png"), full_page=True)
        res = do_submit_flow(page)
        log("第一次提交结果: " + res)
        if res in ("need_resubmit", "unknown"):
            if has_success(page):
                res = "done"
            else:
                page = find_contest_page() or page
                frame = open_form(page)
                if not frame:
                    BROWSER.close()
                    return
                fill_form(frame, page)
                page.screenshot(path=os.path.join(SHOTS_DIR, "headed_refill.png"), full_page=True)
                res = do_submit_flow(page)
                log("第二次提交结果: " + res)
        ok = has_success(page)
        page.screenshot(path=os.path.join(SHOTS_DIR, "headed_result.png"), full_page=True)
        if ok or res == "done":
            log("[SUCCESS] 投稿成功！查看 headed_result.png 确认「提交成功，等待审核」")
        else:
            log("[UNKNOWN] 未识别到成功文案，请查看 headed_result.png")
        BROWSER.close()

if __name__ == "__main__":
    main()

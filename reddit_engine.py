import sys
import os
import time
import json
import urllib.parse
import requests
from camoufox.sync_api import Camoufox

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TELEGRAM_TOKEN_PROTECTED")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1936436999")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "Tuanciro")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "ciroxtreme0703")
REDDIT_EMAIL = os.getenv("REDDIT_EMAIL", "tuanciroxtreme@gmail.com")
WEBSHARE_PROXY = os.getenv("WEBSHARE_PROXY", "")
SESSION_FILE = "session_reddit.json"

def get_proxy_config():
    if not WEBSHARE_PROXY:
        return None
    try:
        p = urllib.parse.urlparse(WEBSHARE_PROXY)
        if p.hostname and p.port:
            cfg = {"server": f"http://{p.hostname}:{p.port}"}
            if p.username:
                cfg["username"] = urllib.parse.unquote(p.username)
            if p.password:
                cfg["password"] = urllib.parse.unquote(p.password)
            return cfg
    except Exception as e:
        print(f"Proxy parse error: {e}")
    return None

def send_telegram(text):
    print(f"[TELEGRAM] {text[:120]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        print(f"Error sending telegram: {e}")

def send_telegram_photo(photo_path, caption=""):
    print(f"[TELEGRAM PHOTO] {photo_path} - {caption}")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"photo": f}, timeout=25)
    except Exception as e:
        print(f"Error sending telegram photo: {e}")

def wait_for_telegram_code(prompt_msg, timeout_sec=300):
    send_telegram(f"⏳ {prompt_msg}\n\n👉 Kirim balasannya ke chat bot ini dalam {timeout_sec} detik.")
    start_time = time.time()
    last_update_id = 0

    try:
        u_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset=-1"
        res = requests.get(u_url, timeout=10).json()
        if res.get("result"):
            last_update_id = res["result"][-1]["update_id"]
    except Exception:
        pass

    while time.time() - start_time < timeout_sec:
        time.sleep(3)
        try:
            poll_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}"
            poll_res = requests.get(poll_url, timeout=10).json()
            results = poll_res.get("result", [])
            for res in results:
                last_update_id = res["update_id"]
                msg = res.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id"))
                text = msg.get("text", "").strip()
                if chat_id == str(TELEGRAM_CHAT_ID) and text:
                    send_telegram(f"✅ Menerima balasan dari Telegram: '{text[:50]}...', memproses di Reddit...")
                    return text
        except Exception as e:
            print(f"Error polling telegram: {e}")

    send_telegram("❌ Waktu habis (timeout) menunggu kode/link verifikasi dari Telegram.")
    return None

def deep_fill_shadow_input(page, selector_keywords, value):
    for sel in selector_keywords:
        loc = page.locator(sel)
        cnt = loc.count()
        for i in range(cnt):
            item = loc.nth(i)
            try:
                if not item.is_visible(timeout=1500):
                    continue
                item.scroll_into_view_if_needed(timeout=2000)
                item.click(force=True, timeout=2000)
                item.fill("")
                time.sleep(0.2)
                item.press_sequentially(value, delay=35)
                time.sleep(0.3)
                item.evaluate("""(el, val) => {
                    if (el.value !== val) {
                        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeSetter.call(el, val);
                    }
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, data: val, inputType: 'insertText' }));
                    el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                    el.dispatchEvent(new FocusEvent('blur', { bubbles: true, composed: true }));
                }""", value)
                print(f"[SHADOW-FILL] Berhasil mengisi '{sel}' (nth={i}) via press_sequentially + composed event!")
                return True
            except Exception as e:
                print(f"[SHADOW-FILL] Warning pada '{sel}' (nth={i}): {e}")
    return False

def click_auth_flow_link_by_text(page, target_substring):
    """
    Khusus untuk <auth-flow-link> Reddit yang meletakkan teksnya di Light DOM (slot),
    sedangkan elemen <a role="button"> ada di dalam shadowRoot tanpa innerText!
    """
    info = page.evaluate("""(targetSub) => {
        const sub = targetSub.toLowerCase();
        // 1. Cek semua auth-flow-link, faceplate-tracker, button, a di Light DOM & Shadow DOM
        const walk = (root) => {
            const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
            for (const el of els) {
                const tag = el.tagName ? el.tagName.toLowerCase() : '';
                const lightText = (el.innerText || el.textContent || '').trim().toLowerCase();
                if ((tag === 'auth-flow-link' || tag === 'button' || tag === 'a') && lightText.includes(sub) && lightText.length < 60) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        if (el.shadowRoot) {
                            const innerBtn = el.shadowRoot.querySelector('a, button, [role="button"]');
                            if (innerBtn) {
                                innerBtn.click();
                                innerBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
                            }
                        }
                        el.removeAttribute('disabled');
                        el.disabled = false;
                        el.click();
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
                        return { found: true, tag, text: lightText, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
                    }
                }
                if (el.shadowRoot) {
                    const res = walk(el.shadowRoot);
                    if (res) return res;
                }
            }
            return null;
        };
        return walk(document);
    }""", target_substring)

    if info and info.get("found"):
        print(f"[AUTH-FLOW-CLICK] Menemukan <{info['tag']}> '{info['text']}' di ({info['x']}, {info['y']}), mengklik mouse...")
        try:
            page.mouse.click(info["x"], info["y"])
        except Exception:
            pass
        return True
    return False

def login_and_search_reddit(target="Barca", mode="sub"):
    proxy_cfg = get_proxy_config()
    proxy_label = f"Residential Proxy ({proxy_cfg['server']})" if proxy_cfg else "Direct IP"
    send_telegram(f"🔴 [Reddit Relay] Memulai eksekusi Reddit Engine via {proxy_label}...")

    with Camoufox(headless=True, proxy=proxy_cfg, geoip=True if proxy_cfg else False, i_know_what_im_doing=True) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        has_session = False
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r") as f:
                    cookies = json.load(f)
                    if cookies:
                        context.add_cookies(cookies)
                        print(f"Loaded {len(cookies)} cookies from {SESSION_FILE}")
                        has_session = True
            except Exception as e:
                print(f"Failed to load cookies: {e}")

        page = context.new_page()

        def on_response(resp):
            u = resp.url.lower()
            if any(k in u for k in ["login", "auth", "account", "otp", "one-time", "svc/shreddit"]):
                try:
                    status = resp.status
                    print(f"🌐 [NET-AUTH] {resp.request.method} {resp.url} -> HTTP {status}")
                    if status >= 400 or "login" in u or "one-time" in u or "magic" in u:
                        try:
                            print(f"   [NET-BODY] {resp.text()[:300]}")
                        except Exception:
                            pass
                except Exception:
                    pass
        page.on("response", on_response)

        need_login = True
        if has_session:
            print("Checking session status on reddit.com...")
            try:
                page.goto("https://www.reddit.com/", timeout=45000, wait_until="domcontentloaded")
                time.sleep(5)
                cookies_now = context.cookies()
                if any(c.get("name") == "reddit_session" for c in cookies_now):
                    need_login = False
                    print("Verified: reddit_session cookie is active!")
            except Exception as e:
                print(f"Session check error: {e}")

        if need_login:
            print(f"Opening https://www.reddit.com/login/ via Residential Proxy...")
            send_telegram(f"🔑 Membuka login Reddit via Residential Proxy & mengaktifkan One-Time Magic Link untuk {REDDIT_EMAIL}...")
            page.goto("https://www.reddit.com/login/", timeout=55000, wait_until="domcontentloaded")
            time.sleep(6)

            # Klik tombol <auth-flow-link> "Email me a one-time link" (di koordinat ~640, 414)
            for attempt in range(1, 5):
                body_now = page.evaluate("() => document.body ? document.body.innerText : ''").lower()
                if "where should we send the link to" in body_now:
                    print("✅ Berhasil masuk ke layar 'Email me a one-time link to login'!")
                    break
                print(f"Attempt {attempt}: Clicking <auth-flow-link> 'Email me a one-time link'...")
                click_auth_flow_link_by_text(page, "Email me a one-time link")
                time.sleep(3)

            page.screenshot(path="reddit_onetime_view.png")
            send_telegram_photo("reddit_onetime_view.png", "📸 Layar 'Email me a one-time link to login'")

            # Isi email tuanciroxtreme@gmail.com pada form one-time link
            print(f"Mengisi email {REDDIT_EMAIL} pada form one-time link...")
            deep_fill_shadow_input(
                page,
                ["input[type='email']", "input[name='email']", "input#login-email", "input[name='username']", "input"],
                REDDIT_EMAIL
            )
            time.sleep(1.5)
            page.screenshot(path="reddit_onetime_filled.png")

            # Klik tombol Continue
            print("Mengklik tombol 'Continue' untuk mengirim email magic link...")
            click_auth_flow_link_by_text(page, "Continue")
            time.sleep(1)
            page.keyboard.press("Enter")
            time.sleep(6)

            page.screenshot(path="reddit_onetime_sent.png")
            send_telegram_photo("reddit_onetime_sent.png", f"📧 Permintaan One-Time Link/OTP dikirim ke {REDDIT_EMAIL}!")

            # Tunggu Magic Link atau Kode OTP dari Tuan Ciro di Telegram
            user_inp = wait_for_telegram_code(
                f"Cek inbox Gmail {REDDIT_EMAIL} sekarang!\n\n"
                f"1. Jika masuk email berisi tombol 'Log In' / Magic Link dari Reddit: tekan tahan tombolnya -> Copy Link URL -> Paste ke chat ini!\n"
                f"2. Jika masuk kode angka 6-digit: ketik angkanya ke chat ini!",
                timeout_sec=300
            )

            if user_inp:
                if "http://" in user_inp or "https://" in user_inp:
                    # Ekstrak URL jika ada teks tambahan
                    import re
                    urls = re.findall(r"https?://[^\s]+", user_inp)
                    magic_url = urls[0] if urls else user_inp
                    print(f"Navigating to magic link: {magic_url}")
                    send_telegram("🚀 Membuka Magic Link Login di Camoufox...")
                    page.goto(magic_url, timeout=55000, wait_until="domcontentloaded")
                    time.sleep(8)
                else:
                    print(f"Entering verification code: {user_inp}")
                    deep_fill_shadow_input(
                        page,
                        ["input[data-testid='verification-code-input']", "input[name='otp']", "input[name='code']", "input[type='tel']", "input[type='text']", "input"],
                        user_inp
                    )
                    time.sleep(1)
                    click_auth_flow_link_by_text(page, "Continue")
                    click_auth_flow_link_by_text(page, "Check code")
                    click_auth_flow_link_by_text(page, "Verify")
                    page.keyboard.press("Enter")
                    time.sleep(8)

            # Pastikan cookie sesi tersimpan (reddit_session)
            cookies = context.cookies()
            print("Current cookies names:", [c.get("name") for c in cookies])
            session_cookie = next((c for c in cookies if c.get("name") == "reddit_session"), None)
            if not session_cookie:
                page.screenshot(path="reddit_login_failed.png")
                send_telegram_photo("reddit_login_failed.png", "❌ Login Reddit Belum Berhasil! Cookie reddit_session belum terbentuk.")
                sys.exit(1)

            print(f"🎉 SUCCESS! Sesi login resmi terverifikasi via reddit_session!")
            with open(SESSION_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
            page.screenshot(path="reddit_login_success.png")
            send_telegram_photo("reddit_login_success.png", f"🎉 Berhasil Login Reddit! Sesi tersimpan permanen.")

        # 2. JALANKAN SCRAPING SUBREDDIT / SEARCH:
        if mode == "sub":
            sub_name = target.replace("r/", "").strip()
            url = f"https://www.reddit.com/r/{sub_name}/"
            label = f"r/{sub_name}"
        else:
            url = f"https://www.reddit.com/search/?q={target}&sort=relevance"
            label = f"Reddit Search '{target}'"

        send_telegram(f"🔍 Sesi Login Reddit Aktif! Menjelajahi {label}...")
        print(f"Navigating to {url}...")
        page.goto(url, timeout=50000, wait_until="domcontentloaded")
        time.sleep(5)

        for _ in range(5):
            page.mouse.wheel(0, 1000)
            time.sleep(2)

        page.screenshot(path="reddit_snapshot.png")

        posts_data = page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            const posts = document.querySelectorAll('shreddit-post');
            posts.forEach(p => {
                const title = p.getAttribute('post-title') || (p.querySelector('[slot="title"]') ? p.querySelector('[slot="title"]').innerText.trim() : '');
                const author = p.getAttribute('author') || 'Reddit User';
                const score = p.getAttribute('score') || '0';
                const comments = p.getAttribute('comment-count') || '0';
                const permalink = p.getAttribute('permalink') || '';
                const fullUrl = permalink.startsWith('/') ? 'https://www.reddit.com' + permalink : permalink;

                if (title && !seen.has(title)) {
                    seen.add(title);
                    results.push({ title, author, score, comments, url: fullUrl });
                }
            });

            if (results.length === 0) {
                const links = document.querySelectorAll('a[data-testid="post-title"], a[href*="/comments/"]');
                links.forEach(a => {
                    const text = a.innerText.trim();
                    const href = a.getAttribute('href') || '';
                    if (text && text.length > 5 && !seen.has(text) && href.includes('/comments/')) {
                        seen.add(text);
                        const fullUrl = href.startsWith('/') ? 'https://www.reddit.com' + href : href;
                        results.push({ title: text, author: 'Reddit User', score: '-', comments: '-', url: fullUrl });
                    }
                });
            }
            return results.slice(0, 20);
        }""")

        print(f"Total unique posts collected: {len(posts_data)}")

        if posts_data:
            results_text = []
            for idx, p in enumerate(posts_data[:15], 1):
                item = f"{idx}. 📌 {p['title']}\n   👤 u/{p['author']} | ⬆️ {p['score']} | 💬 {p['comments']} komentar\n   🔗 {p['url']}"
                results_text.append(item)

            report = f"🔥 Postingan Terhangat di {label} ({len(results_text)} Diskusi):\n\n" + "\n\n───────────────────\n\n".join(results_text)

            if len(report) > 3800:
                mid = len(results_text) // 2
                chunk1 = f"🔥 Postingan Terhangat di {label} (Bagian 1):\n\n" + "\n\n───────────────────\n\n".join(results_text[:mid])
                chunk2 = f"🔥 Lanjutan {label} (Bagian 2):\n\n" + "\n\n───────────────────\n\n".join(results_text[mid:])
                send_telegram(chunk1)
                time.sleep(0.6)
                send_telegram(chunk2)
            else:
                send_telegram(report)

            send_telegram_photo("reddit_snapshot.png", f"📸 Bukti Reddit: {label}")
        else:
            send_telegram(f"⚠️ Tidak ada postingan yang ditarik untuk {label}, lihat screenshot.")
            send_telegram_photo("reddit_snapshot.png", f"Snapshot {label}")

if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "sub"
    target_arg = sys.argv[2] if len(sys.argv) > 2 else "Barca"
    login_and_search_reddit(target_arg, mode_arg)

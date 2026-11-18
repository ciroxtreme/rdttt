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

def wait_for_telegram_code(prompt_msg, timeout_sec=240):
    send_telegram(f"⏳ {prompt_msg}\n\n👉 Kirim balasannya (kode OTP 6 digit / Magic Link / atau 'reddit_session=...') ke chat bot ini dalam {timeout_sec} detik.")
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
                    send_telegram(f"✅ Menerima input dari Telegram: '{text[:40]}...', memproses di Reddit...")
                    return text
        except Exception as e:
            print(f"Error polling telegram: {e}")

    send_telegram("❌ Waktu habis (timeout) menunggu kode verifikasi dari Telegram.")
    return None

def deep_fill_shadow_input(page, selector_keywords, value):
    """
    Menemukan <input> di dalam Shadow DOM berlapis (<faceplate-text-input> dll),
    memfokuskan, mengetik nilai asli, dan memicu event input/change composed:true
    agar Lit/Faceplate form state ter-update dan tombol submit menjadi ENABLED.
    """
    # 1. Coba via Playwright native locator (otomatis menembus open shadow roots)
    for sel in selector_keywords:
        loc = page.locator(sel).first
        if loc.count() > 0:
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(force=True, timeout=3000)
                # Bersihkan isi sebelumnya
                loc.fill("")
                time.sleep(0.2)
                # Ketik karakter per karakter agar event keyboard & faceplate listener aktif
                loc.press_sequentially(value, delay=35)
                time.sleep(0.3)
                # Dispatch composed input/change events ke atas
                loc.evaluate("""(el, val) => {
                    if (el.value !== val) {
                        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeSetter.call(el, val);
                    }
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, data: val, inputType: 'insertText' }));
                    el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                    el.dispatchEvent(new FocusEvent('blur', { bubbles: true, composed: true }));
                }""", value)
                print(f"[SHADOW-FILL] Berhasil mengisi '{sel}' via press_sequentially + composed event!")
                return True
            except Exception as e:
                print(f"[SHADOW-FILL] Warning pada '{sel}': {e}")
    return False

def dump_deep_dom_state(page):
    """Mengekstrak semua elemen interaktif (input, button, a) menembus seluruh Shadow Root."""
    return page.evaluate("""() => {
        const items = [];
        const walk = (root, path = "document") => {
            if (!root) return;
            const children = root.querySelectorAll ? root.querySelectorAll('*') : [];
            for (const el of children) {
                const tag = el.tagName ? el.tagName.toLowerCase() : '';
                if (['input', 'button', 'a', 'faceplate-text-input'].includes(tag) || el.getAttribute('role') === 'button') {
                    const rect = el.getBoundingClientRect();
                    items.push({
                        tag,
                        name: el.getAttribute('name') || '',
                        id: el.id || '',
                        type: el.getAttribute('type') || '',
                        disabled: el.disabled || el.hasAttribute('disabled'),
                        text: (el.innerText || el.value || '').trim().slice(0, 60),
                        visible: rect.width > 0 && rect.height > 0,
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2),
                        path
                    });
                }
                if (el.shadowRoot) {
                    walk(el.shadowRoot, path + " > " + tag + "#shadow");
                }
            }
        };
        walk(document);
        return items;
    }""")

def click_deep_shadow_button(page, text_matches):
    """Mencari dan mengklik tombol di dalam Shadow DOM baik via koordinat mouse maupun JS click()."""
    info = page.evaluate("""(targets) => {
        const walk = (root) => {
            const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
            for (const el of els) {
                const tag = el.tagName ? el.tagName.toLowerCase() : '';
                if (tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button') {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    for (const t of targets) {
                        if (txt === t.toLowerCase() || (txt.includes(t.toLowerCase()) && txt.length < 45)) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                el.removeAttribute('disabled');
                                el.disabled = false;
                                el.click();
                                return { found: true, text: txt, x: r.x + r.width / 2, y: r.y + r.height / 2 };
                            }
                        }
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
    }""", text_matches)
    if info and info.get("found"):
        print(f"[SHADOW-CLICK] Menemukan tombol '{info['text']}' di ({info['x']}, {info['y']}), mengklik mouse...")
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

        # Load existing session jika ada
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

        # Pasang network response logger untuk endpoint auth/login Reddit
        auth_responses = []
        def on_response(resp):
            u = resp.url.lower()
            if any(k in u for k in ["login", "auth", "account", "otp", "one-time", "svc/shreddit"]):
                try:
                    status = resp.status
                    print(f"🌐 [NET-AUTH] {resp.request.method} {resp.url} -> HTTP {status}")
                    if status >= 400 or "login" in u or "one-time" in u:
                        body_preview = ""
                        try:
                            body_preview = resp.text()[:300]
                        except Exception:
                            pass
                        print(f"   [NET-BODY] {body_preview}")
                        auth_responses.append({"url": resp.url, "status": status, "body": body_preview})
                except Exception:
                    pass
        page.on("response", on_response)

        # 1. Pastikan status login
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
            print(f"Starting login flow at https://www.reddit.com/login/ for {REDDIT_USERNAME}...")
            send_telegram(f"🔑 Membuka halaman login Reddit via Residential Proxy untuk akun: {REDDIT_USERNAME}...")
            page.goto("https://www.reddit.com/login/", timeout=55000, wait_until="domcontentloaded")
            time.sleep(6)

            dom_items = dump_deep_dom_state(page)
            print(f"🔍 [DOM INSPECT] Ditemukan {len(dom_items)} elemen interaktif:")
            for it in dom_items[:25]:
                print(f"   - {it}")

            # 1. Isi Username dengan Shadow-Piercing Sequential Typing
            print(f"Filling username: {REDDIT_USERNAME}...")
            ok_user = deep_fill_shadow_input(
                page,
                ["input[name='username']", "input#login-username", "input[autocomplete='username']"],
                REDDIT_USERNAME
            )

            # 2. Isi Password dengan Shadow-Piercing Sequential Typing
            print("Filling password...")
            ok_pwd = deep_fill_shadow_input(
                page,
                ["input[name='password']", "input#login-password", "input[type='password']"],
                REDDIT_PASSWORD
            )

            time.sleep(1.5)
            page.screenshot(path="reddit_before_submit.png")
            send_telegram_photo("reddit_before_submit.png", "📸 Form login terisi via Residential Proxy & Shadow DOM Typing")

            # Cek status tombol Log In setelah pengisian
            dom_after_fill = dump_deep_dom_state(page)
            for it in dom_after_fill:
                if "log in" in it.get("text", "").lower() or it.get("type") == "submit":
                    print(f"   [SUBMIT-BTN-STATE] {it}")

            # 3. Klik tombol Log In + tekan Enter
            print("Submitting login form...")
            clicked_login = click_deep_shadow_button(page, ["Log In", "Log in"])
            if not clicked_login:
                page.keyboard.press("Enter")
            else:
                time.sleep(1)
                page.keyboard.press("Enter")

            time.sleep(7)
            page.screenshot(path="reddit_after_submit.png")
            send_telegram_photo("reddit_after_submit.png", "📸 Status layar setelah klik Log In")

            # 4. Cek apakah reddit_session sudah dapat, atau masih kena block / butuh One-Time Link / OTP
            cookies = context.cookies()
            session_cookie = next((c for c in cookies if c.get("name") == "reddit_session"), None)

            body_text = page.evaluate("() => document.body ? document.body.innerText : ''")
            body_lower = body_text.lower()
            print(f"📄 [BODY TEXT AFTER LOGIN]: {body_text[:400].replace(chr(10), ' ')}")

            # Jika kena 'blocked by network security' atau 'invalid username or password', otomatis coba One-Time Email Link!
            if not session_cookie and (
                "blocked by network security" in body_lower
                or "invalid username or password" in body_lower
                or "incorrect username or password" in body_lower
                or "email me a one-time link" in body_lower
            ):
                print("⚠️ Standard password login ditolak/butuh verifikasi. Mengaktifkan tombol 'Email me a one-time link'...")
                send_telegram("🔄 Mengklik tombol 'Email me a one-time link' untuk mengirim Magic Link / OTP ke email...")
                click_deep_shadow_button(page, ["Email me a one-time link"])
                time.sleep(4)
                page.screenshot(path="reddit_onetime_view.png")
                send_telegram_photo("reddit_onetime_view.png", "📸 Status setelah klik 'Email me a one-time link'")

                body_ot = page.evaluate("() => document.body ? document.body.innerText : ''").lower()
                if "where should we send" in body_ot or "email" in body_ot:
                    print(f"Mengisi email {REDDIT_EMAIL} pada form one-time link...")
                    deep_fill_shadow_input(
                        page,
                        ["input[type='email']", "input[name='email']", "input#login-email", "input[name='username']"],
                        REDDIT_EMAIL
                    )
                    time.sleep(1.5)
                    click_deep_shadow_button(page, ["Continue", "Send link", "Email me"])
                    page.keyboard.press("Enter")
                    time.sleep(5)
                    page.screenshot(path="reddit_onetime_sent.png")
                    send_telegram_photo("reddit_onetime_sent.png", f"📧 Permintaan One-Time Link/OTP dikirim ke {REDDIT_EMAIL}!")

            # 5. Loop cek HANYA cookie 'reddit_session' (BUKAN token_v2!) atau tunggu OTP / Magic Link / Cookie dari Telegram
            for attempt in range(1, 10):
                cookies = context.cookies()
                session_cookie = next((c for c in cookies if c.get("name") == "reddit_session"), None)
                if session_cookie:
                    print(f"🎉 Login success! Found authentic session cookie: reddit_session")
                    break

                body_text = page.evaluate("() => document.body ? document.body.innerText : ''").lower()
                print(f"Check login result (attempt {attempt}/10)...")

                if any(k in body_text for k in ["verification code", "two-factor", "security code", "check your email", "enter code", "6-digit", "we sent a", "one-time link"]) or attempt == 2:
                    page.screenshot(path="reddit_otp_prompt.png")
                    send_telegram_photo("reddit_otp_prompt.png", "⚠️ Menunggu Kode OTP / Magic Link / Cookie Sesi Reddit!")
                    user_inp = wait_for_telegram_code(
                        f"Silakan kirim salah satu ke chat ini:\n1. Kode 6-digit OTP dari email {REDDIT_EMAIL}\n2. Link Login (https://www.reddit.com/...) dari email\n3. Atau nilai cookie 'reddit_session' dari browser Anda",
                        timeout_sec=240
                    )
                    if user_inp:
                        if user_inp.startswith("http://") or user_inp.startswith("https://"):
                            print("Navigating to magic link from Telegram...")
                            page.goto(user_inp, timeout=50000, wait_until="domcontentloaded")
                            time.sleep(8)
                        elif len(user_inp) > 30 and not user_inp.isdigit():
                            # User mengirim nilai cookie reddit_session secara langsung
                            val = user_inp.replace("reddit_session=", "").strip()
                            context.add_cookies([{
                                "name": "reddit_session",
                                "value": val,
                                "domain": ".reddit.com",
                                "path": "/",
                                "httpOnly": True,
                                "secure": True
                            }])
                            page.goto("https://www.reddit.com/", timeout=45000, wait_until="domcontentloaded")
                            time.sleep(5)
                        else:
                            deep_fill_shadow_input(
                                page,
                                ["input[data-testid='verification-code-input']", "input[name='otp']", "input[name='code']", "input[type='text']", "input[type='number']"],
                                user_inp
                            )
                            time.sleep(1)
                            click_deep_shadow_button(page, ["Continue", "Verify", "Log In", "Submit"])
                            page.keyboard.press("Enter")
                            time.sleep(8)
                    else:
                        break
                time.sleep(3)

            # Pastikan cookie sesi tersimpan (HANYA reddit_session asli yang menandakan login berhasil)
            cookies = context.cookies()
            session_cookie = next((c for c in cookies if c.get("name") == "reddit_session"), None)
            if not session_cookie:
                page.screenshot(path="reddit_login_failed.png")
                send_telegram_photo("reddit_login_failed.png", "❌ Login Reddit Belum Berhasil! Cookie reddit_session belum terbentuk.")
                send_telegram("🛑 Proses dihentikan: tidak akan melakukan scraping sebelum login tuntas 100%.")
                sys.exit(1)

            print(f"🎉 SUCCESS! Sesi login resmi terverifikasi via reddit_session!")
            with open(SESSION_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
            page.screenshot(path="reddit_login_success.png")
            send_telegram_photo("reddit_login_success.png", f"🎉 Berhasil Login Reddit! Sesi tersimpan permanen.")

        # 2. HANYA JALAN JIKA LOGIN SUDAH 100% SUKSES:
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

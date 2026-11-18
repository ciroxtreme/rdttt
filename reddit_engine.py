import sys
import os
import time
import json
import requests
from camoufox.sync_api import Camoufox

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TELEGRAM_TOKEN_PROTECTED")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1936436999")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "Tuanciro")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "ciroxtreme0703")
SESSION_FILE = "session_reddit.json"

def send_telegram(text):
    print(f"[TELEGRAM] {text[:100]}...")
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

def wait_for_telegram_code(prompt_msg, timeout_sec=180):
    send_telegram(f"⏳ {prompt_msg}\n\n👉 Kirim balasannya (kode angka/email) ke chat bot ini dalam {timeout_sec} detik.")
    start_time = time.time()
    last_update_id = 0
    
    # Inisialisasi offset awal
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
                    send_telegram(f"✅ Menerima kode: '{text}', menyuntikkan ke Reddit...")
                    return text
        except Exception as e:
            print(f"Error polling telegram: {e}")
            
    send_telegram("❌ Waktu habis (timeout) menunggu kode verifikasi dari Telegram.")
    return None

def login_and_search_reddit(target="Barca", mode="sub"):
    send_telegram("🔴 [Reddit Relay] Memulai eksekusi Reddit Engine (Mode: Autentikasi Ketat)...")
    
    with Camoufox(headless=True, i_know_what_im_doing=True) as browser:
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
        
        # 1. Pastikan status login
        need_login = True
        if has_session:
            print("Checking session status on reddit.com...")
            try:
                page.goto("https://www.reddit.com/", timeout=40000, wait_until="domcontentloaded")
                time.sleep(4)
                body_txt = page.evaluate("() => document.body.innerText")
                # Jika tidak ada tombol Log In dan ada tanda user aktif
                if "Log In" not in body_txt and "Sign Up" not in body_txt:
                    need_login = False
                    print("Verified: Already logged in to Reddit!")
            except Exception as e:
                print(f"Session check error: {e}")

        if need_login:
            print("Starting login flow at https://www.reddit.com/login/...")
            send_telegram(f"🔑 Membuka halaman login resmi Reddit untuk akun {REDDIT_USERNAME}...")
            page.goto("https://www.reddit.com/login/", timeout=45000, wait_until="domcontentloaded")
            time.sleep(6)
            
            # Input username
            user_input = page.locator("input[name='username'], input#login-username, input[autocomplete='username'], input").first
            if user_input.count() > 0:
                print(f"Filling username {REDDIT_USERNAME}...")
                try:
                    user_input.click(force=True, timeout=5000)
                except Exception:
                    pass
                user_input.fill(REDDIT_USERNAME)
                time.sleep(1)
            else:
                send_telegram("❌ Gagal menemukan kolom input username Reddit!")
                page.screenshot(path="reddit_no_user.png")
                send_telegram_photo("reddit_no_user.png", "Input username Reddit hilang")
                sys.exit(1)
                
            # Input password
            pwd_input = page.locator("input[name='password'], input#login-password, input[type='password']").first
            if pwd_input.count() > 0:
                print("Filling password...")
                try:
                    pwd_input.click(force=True, timeout=5000)
                except Exception:
                    pass
                pwd_input.fill(REDDIT_PASSWORD)
                time.sleep(2)
                
                # Klik tombol login / submit / tekan Enter
                login_btn = page.locator("button[type='submit'], button:has-text('Log In'), button:has-text('Log in'), button.login").first
                if login_btn.count() > 0 and login_btn.is_visible():
                    try:
                        print("Clicking login submit button...")
                        login_btn.click(force=True)
                    except Exception as e:
                        print(f"Click submit failed ({e}), pressing Enter...")
                        page.keyboard.press("Enter")
                else:
                    print("Submit button not found/visible, pressing Enter...")
                    page.keyboard.press("Enter")
                    
                time.sleep(10)
            else:
                send_telegram("❌ Gagal menemukan kolom input password Reddit!")
                page.screenshot(path="reddit_no_pwd.png")
                send_telegram_photo("reddit_no_pwd.png", "Input password Reddit hilang")
                sys.exit(1)

            # Cek apakah butuh 2FA / OTP verifikasi atau ada respon login
            for attempt in range(12):
                cookies = context.cookies()
                # Reddit login cookies: 'reddit_session' atau 'token_v2'
                session_cookie = next((c for c in cookies if c.get("name") in ["reddit_session", "token_v2"]), None)
                if session_cookie:
                    print(f"Found session cookie: {session_cookie.get('name')}!")
                    break
                    
                body_text = page.locator("body").inner_text()
                current_url = page.url
                print(f"Polling login state (attempt {attempt+1}/12): URL={current_url}")
                
                if any(k in body_text.lower() for k in ["verification code", "two-factor", "security code", "check your email", "enter code", "one-time password", "enter the 6-digit"]):
                    page.screenshot(path="reddit_need_code.png")
                    send_telegram_photo("reddit_need_code.png", "⚠️ Reddit meminta Kode Verifikasi / 2FA!")
                    code = wait_for_telegram_code(f"Reddit meminta kode verifikasi / 2FA untuk akun {REDDIT_USERNAME}.", timeout_sec=180)
                    if code:
                        code_input = page.locator("input[data-testid='verification-code-input'], input[name='otp'], input[name='code'], input[type='number'], input[type='text']").first
                        if code_input.count() > 0:
                            try:
                                code_input.click(force=True)
                            except Exception:
                                pass
                            code_input.fill(code)
                            time.sleep(1)
                            page.keyboard.press("Enter")
                            time.sleep(8)
                    else:
                        send_telegram("❌ Login dibatalkan karena tidak ada kode yang dimasukkan.")
                        sys.exit(1)
                elif "incorrect username or password" in body_text.lower():
                    print("Detected incorrect credentials error message!")
                    break
                time.sleep(3)

            # Pastikan cookie sesi tersimpan
            cookies = context.cookies()
            session_cookie = next((c for c in cookies if c.get("name") in ["reddit_session", "token_v2"]), None)
            if not session_cookie:
                page.screenshot(path="reddit_login_failed.png")
                send_telegram_photo("reddit_login_failed.png", "❌ Login Reddit Gagal! Sesi login belum terbentuk.")
                send_telegram("🛑 Proses dihentikan sesuai instruksi: tidak akan melakukan scraping sebelum login tuntas 100%.")
                sys.exit(1)

            print(f"🎉 SUCCESS! Sesi login terverifikasi via {session_cookie.get('name')}!")
            with open(SESSION_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
            page.screenshot(path="reddit_login_success.png")
            send_telegram_photo("reddit_login_success.png", f"🎉 Berhasil Login Reddit ({REDDIT_USERNAME})! Sesi tersimpan permanen.")

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
        
        # Scroll perlahan untuk memicu progressive render shadow DOM Reddit
        for _ in range(5):
            page.mouse.wheel(0, 1000)
            time.sleep(2)
            
        page.screenshot(path="reddit_snapshot.png")
        
        # Ekstraksi postingan Reddit via JS evaluation (menembus shadow root & shreddit-post)
        posts_data = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            
            // 1. Selector shreddit-post custom elements
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
            
            // 2. Fallback: cari tag anchor artikel / feed
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
        
        # Format report message
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

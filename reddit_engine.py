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
REDDIT_EMAIL = os.getenv("REDDIT_EMAIL", "tuanciroxtreme@gmail.com")
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
            print(f"Starting login flow at https://www.reddit.com/login/ via Email One-Time Link ({REDDIT_EMAIL})...")
            send_telegram(f"🔑 Membuka login Reddit via Email One-Time Link untuk {REDDIT_EMAIL}...")
            page.goto("https://www.reddit.com/login/", timeout=45000, wait_until="domcontentloaded")
            time.sleep(6)
            
            # Cek opsi "Email me a one-time link"
            email_link_btn = page.locator("button:has-text('Email me a one-time link'), a:has-text('Email me a one-time link')").first
            if email_link_btn.count() > 0:
                print("Clicking 'Email me a one-time link'...")
                try:
                    email_link_btn.click(force=True)
                except Exception:
                    pass
                time.sleep(3)
                
                # Input email address
                email_input = page.locator("input[type='email'], input[name='email'], input#login-email, input").first
                if email_input.count() > 0:
                    print(f"Filling email {REDDIT_EMAIL}...")
                    try:
                        email_input.click(force=True)
                    except Exception:
                        pass
                    email_input.fill(REDDIT_EMAIL)
                    time.sleep(1)
                    
                    # Submit email request
                    submit_email_btn = page.locator("button[type='submit'], button:has-text('Send email'), button:has-text('Continue'), button:has-text('Email me')").first
                    if submit_email_btn.count() > 0:
                        submit_email_btn.click(force=True)
                    else:
                        page.keyboard.press("Enter")
                    time.sleep(5)
                    
                    page.screenshot(path="reddit_email_sent.png")
                    send_telegram_photo("reddit_email_sent.png", f"📧 Link/kode login telah dikirim ke {REDDIT_EMAIL}!")
                    
                    user_resp = wait_for_telegram_code(f"Buka email {REDDIT_EMAIL}, copy link login atau kode 6-digit dari Reddit lalu paste ke sini.", timeout_sec=240)
                    if user_resp:
                        if user_resp.startswith("http://") or user_resp.startswith("https://"):
                            print(f"Received one-time link: {user_resp}")
                            send_telegram("🚀 Membuka link one-time login Reddit di browser...")
                            page.goto(user_resp, timeout=45000, wait_until="domcontentloaded")
                            time.sleep(10)
                        else:
                            print(f"Received code: {user_resp}")
                            code_input = page.locator("input[data-testid='verification-code-input'], input[name='otp'], input[name='code'], input[type='number'], input[type='text'], input").first
                            if code_input.count() > 0:
                                code_input.fill(user_resp)
                                time.sleep(1)
                                page.keyboard.press("Enter")
                                time.sleep(8)
                    else:
                        send_telegram("❌ Login dibatalkan karena tidak ada input link/kode dari user.")
                        sys.exit(1)
            else:
                print("Email one-time link button not found, falling back to credentials...")
                # Input username
                user_input = page.locator("input[name='username'], input#login-username, input[autocomplete='username'], input").first
                if user_input.count() > 0:
                    user_input.fill(REDDIT_USERNAME)
                pwd_input = page.locator("input[name='password'], input#login-password, input[type='password']").first
                if pwd_input.count() > 0:
                    pwd_input.fill(REDDIT_PASSWORD)
                    page.keyboard.press("Enter")
                time.sleep(8)

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

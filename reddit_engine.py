import sys
import os
import re
import time
import json
import urllib.parse
import requests
from camoufox.sync_api import Camoufox

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
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

def inspect_real_screen_state(page, context):
    """
    Inspektor Anti-Halu: Membaca kondisi DOM, atribut shreddit-app, dan cookies nyata.
    Tidak boleh menebak atau berasumsi tanpa bukti nyata dari DOM/Cookie.
    """
    cookies = context.cookies()
    has_reddit_session = any(c.get("name") == "reddit_session" for c in cookies)
    dom_info = page.evaluate("""() => {
        const app = document.querySelector('shreddit-app');
        const userLoggedInAttr = app ? app.getAttribute('user-logged-in') : null;
        const mgr = document.querySelector('auth-flow-manager');
        const stepName = mgr ? (mgr.stepName || mgr.getAttribute('step-name')) : null;
        const bodyText = document.body ? document.body.innerText : '';
        const bodyLower = bodyText.toLowerCase();
        const title = document.title || '';
        const hasPosts = document.querySelectorAll('shreddit-post, [data-testid="search-post-unit"], [data-testid="search-post-with-content-preview"], [data-testid="search-sdui-comment-unit"]').length;
        let searchSort = null;
        const trackers = document.querySelectorAll('search-telemetry-tracker[data-faceplate-tracking-context]');
        for (const tr of trackers) {
            try {
                const ctx = JSON.parse(tr.getAttribute('data-faceplate-tracking-context') || '{}');
                if (ctx && ctx.search && ctx.search.sort) {
                    searchSort = ctx.search.sort;
                    break;
                }
            } catch (e) {}
        }
        return {
            url: location.href,
            title,
            userLoggedInAttr,
            stepName,
            hasPosts,
            searchSort,
            isBlocked: bodyLower.includes('blocked by network security') || bodyLower.includes('prove your humanity'),
            isMagicInput: bodyLower.includes('where should we send the link to'),
            isMagicSent: bodyLower.includes('check your inbox') || bodyLower.includes('we emailed a link to'),
            isMainLogin: bodyLower.includes('continue with phone number') || bodyLower.includes('email me a one-time link')
        };
    }""")

    if has_reddit_session and dom_info.get("userLoggedInAttr") == "true":
        state = "STATE_LOGGED_IN_VERIFIED"
    elif has_reddit_session and not dom_info.get("isBlocked"):
        state = "STATE_SESSION_COOKIE_PRESENT"
    elif dom_info.get("isBlocked"):
        state = "STATE_BLOCKED_BY_SECURITY"
    elif dom_info.get("isMagicSent"):
        state = "STATE_MAGIC_LINK_CHECK_INBOX"
    elif dom_info.get("isMagicInput") or dom_info.get("stepName") == "magic_link_login":
        state = "STATE_MAGIC_LINK_ENTER_EMAIL"
    elif dom_info.get("isMainLogin") or dom_info.get("stepName") == "login":
        state = "STATE_MAIN_LOGIN_SCREEN"
    else:
        state = "STATE_OTHER"

    dom_info["state"] = state
    dom_info["has_reddit_session"] = has_reddit_session
    print(f"🧭 [STATE INSPECTOR] Posisi Nyata: {state} | URL: {dom_info['url']} | user-logged-in={dom_info['userLoggedInAttr']} | items={dom_info['hasPosts']} | sort={dom_info.get('searchSort')}")
    return dom_info

def request_magic_link_direct_api(page, email):
    """
    Memanggil endpoint internal `/svc/shreddit/account/login/magic_link/initialize`
    secara langsung menggunakan token reCAPTCHA Enterprise dari <auth-flow-login>,
    dan mengembalikan HTTP status & body asli (Anti-Halu: hanya klaim sukses jika HTTP 200).
    """
    return page.evaluate("""async (targetEmail) => {
        const loginEl = document.querySelector('auth-flow-login') || document.querySelector('auth-magic-link-login');
        if (!loginEl || typeof loginEl.getRecaptchaToken !== 'function') {
            return { ok: false, status: 0, error: 'Elemen auth-flow-login / getRecaptchaToken tidak ditemukan di DOM' };
        }
        try {
            const token = await loginEl.getRecaptchaToken('v1/web/login_with_magic_link');
            const csrf = document.cookie.split('; ').find(r => r.startsWith('csrf_token='))?.split('=')[1] || '';
            const params = new URLSearchParams();
            params.set('identifier', targetEmail);
            params.set('recaptcha_token', token);
            params.set('recaptcha_use_checkbox', 'false');
            params.set('recaptcha_action', 'v1/web/login_with_magic_link');
            params.set('csrf_token', csrf);

            const res = await fetch('/svc/shreddit/account/login/magic_link/initialize', {
                method: 'POST',
                headers: {
                    'Accept': 'text/vnd.reddit.partial+html, application/json',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: params.toString()
            });
            const body = await res.text();
            return { ok: res.status === 200, status: res.status, body: body.slice(0, 300) };
        } catch (err) {
            return { ok: false, status: -1, error: String(err) };
        }
    }""", email)

def redeem_magic_link_direct_api(page, magic_url):
    """
    Mengekstrak token `mlt:...` dan `user_id` (`t2_...`) dari URL Magic Link
    lalu menukarnya langsung via JSON POST `/svc/shreddit/account/login/magic_link`
    tanpa membuka GET pada URL Magic Link agar single-use token tidak hangus!
    """
    m = re.search(r"(mlt:[^/?&#\s]+)/+(t2_[a-z0-9]+)", magic_url, re.IGNORECASE)
    if not m:
        return {"ok": False, "status": 0, "error": f"Format URL Magic Link tidak mengandung mlt:... dan t2_...: {magic_url}"}

    mlt_token = urllib.parse.unquote(m.group(1))
    user_id = m.group(2)
    print(f"🔑 Menukar token={mlt_token} untuk user_id={user_id} via JSON POST...")

    return page.evaluate("""async ({ mltToken, userId }) => {
        const loginEl = document.querySelector('auth-flow-login') || document.querySelector('auth-magic-link-login');
        if (!loginEl || typeof loginEl.getRecaptchaToken !== 'function') {
            return { ok: false, status: 0, error: 'Elemen auth-flow-login tidak ditemukan saat redeem' };
        }
        try {
            const recaptchaToken = await loginEl.getRecaptchaToken('v1/web/login_with_magic_link');
            const csrf = document.cookie.split('; ').find(r => r.startsWith('csrf_token='))?.split('=')[1] || '';
            const res = await fetch('/svc/shreddit/account/login/magic_link', {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    user_id: userId,
                    token: mltToken,
                    recaptcha_token: recaptchaToken,
                    recaptcha_action: 'v1/web/login_with_magic_link',
                    csrf_token: csrf
                })
            });
            const body = await res.text();
            return { ok: res.status === 200, status: res.status, body: body.slice(0, 300) };
        } catch (err) {
            return { ok: false, status: -1, error: String(err) };
        }
    }""", {"mltToken": mlt_token, "userId": user_id})

def run_session_workflow(target, mode, proxy_cfg):
    proxy_label = f"Residential Proxy ({proxy_cfg['server']})" if proxy_cfg else "Direct IP"
    print(f"Starting Camoufox with {proxy_label}...")

    with Camoufox(headless=True, proxy=proxy_cfg, geoip=True if proxy_cfg else False, i_know_what_im_doing=True) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        has_session = False
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r") as f:
                    cookies = json.load(f)
                    # Jangan masukkan token_v2 anonim jika sudah ada reddit_session
                    if any(c.get("name") == "reddit_session" for c in cookies):
                        cookies = [c for c in cookies if c.get("name") != "token_v2"]
                    if cookies:
                        context.add_cookies(cookies)
                        print(f"Loaded {len(cookies)} cookies from {SESSION_FILE}")
                        has_session = any(c.get("name") == "reddit_session" for c in cookies)
            except Exception as e:
                print(f"Failed to load cookies: {e}")

        page = context.new_page()
        return execute_on_page(page, context, target, mode, has_session, proxy_label)

def format_iso_to_wib(iso_str):
    if not iso_str:
        return "Baru saja"
    try:
        from datetime import datetime, timezone, timedelta
        clean = iso_str.replace("Z", "+00:00")
        if clean.endswith("+0000"):
            clean = clean[:-5] + "+00:00"
        dt = datetime.fromisoformat(clean)
        now = datetime.now(timezone.utc)
        diff_sec = max(0, int((now - dt).total_seconds()))
        if diff_sec < 60:
            rel = f"{diff_sec} dtk lalu"
        elif diff_sec < 3600:
            rel = f"{diff_sec // 60} mnt lalu"
        elif diff_sec < 86400:
            rel = f"{diff_sec // 3600} jam lalu"
        else:
            rel = f"{diff_sec // 86400} hari lalu"
        wib = dt.astimezone(timezone(timedelta(hours=7)))
        return f"{rel} ({wib.strftime('%d %b %H.%M')} WIB)"
    except Exception:
        return iso_str[:16]

def execute_on_page(page, context, target, mode, has_session, proxy_label):
    if mode == "sub":
        sub_name = target.replace("r/", "").strip()
        target_url = f"https://www.reddit.com/r/{sub_name}/new/"
        label = f"r/{sub_name} (New)"
    else:
        target_url = f"https://www.reddit.com/search/?q={urllib.parse.quote(target)}&sort=new"
        label = f"Reddit Search '{target}' (SORT=NEW)"

    need_login = True
    if has_session:
        print(f"Memverifikasi sesi reddit_session langsung di {target_url} ({proxy_label})...")
        try:
            page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(5)
            state_info = inspect_real_screen_state(page, context)
            if state_info["state"] in ("STATE_LOGGED_IN_VERIFIED", "STATE_SESSION_COOKIE_PRESENT") and not state_info["isBlocked"]:
                need_login = False
                print(f"✅ Sesi terverifikasi aktif! Posisi nyata: {state_info['state']} | sort={state_info.get('searchSort')}")
            elif state_info["isBlocked"]:
                print(f"⚠️ Koneksi {proxy_label} terkena blokir jaringan padahal punya sesi.")
                return "BLOCKED_WITH_SESSION"
        except Exception as e:
            print(f"Navigation check error ({proxy_label}): {e}")
            return "BLOCKED_WITH_SESSION"

    if need_login:
        send_telegram(f"🔑 Membuka https://www.reddit.com/login/ via {proxy_label} (Mode: Strict State Anti-Halu)...")
        page.goto("https://www.reddit.com/login/", timeout=55000, wait_until="domcontentloaded")
        time.sleep(6)

        state_info = inspect_real_screen_state(page, context)
        page.screenshot(path="reddit_state_1.png")

        if state_info["state"] == "STATE_BLOCKED_BY_SECURITY":
            send_telegram_photo("reddit_state_1.png", f"❌ [LAPORAN JUJUR] Posisi saat ini: STATE_BLOCKED_BY_SECURITY di {proxy_label}.")
            return "BLOCKED_NO_SESSION"

        send_telegram(f"🧭 Posisi Nyata Terkonfirmasi: {state_info['state']}. Mengirim request Magic Link API untuk {REDDIT_EMAIL}...")
        init_res = request_magic_link_direct_api(page, REDDIT_EMAIL)
        print(f"[MAGIC-LINK-INIT] Result: {init_res}")

        if not init_res.get("ok"):
            page.screenshot(path="reddit_magic_init_failed.png")
            send_telegram_photo(
                "reddit_magic_init_failed.png",
                f"❌ [ANTI-HALU STOP] Gagal meminta Magic Link! Server mengembalikan status={init_res.get('status')} ({init_res.get('error') or init_res.get('body')}). Bot berhenti & tidak akan klaim email terkirim!"
            )
            sys.exit(1)

        send_telegram_photo(
            "reddit_state_1.png",
            f"✅ [TERVERIFIKASI HTTP 200 OK] Server Reddit merespons {init_res.get('status')} {init_res.get('body')} untuk pengiriman Magic Link ke {REDDIT_EMAIL}!"
        )

        user_inp = wait_for_telegram_code(
            f"Cek inbox Gmail {REDDIT_EMAIL} sekarang!\n\n"
            f"⚠️ PENTING: JANGAN KLIK/BUKA link-nya di browser HP agar token sekali pakainya tidak hangus!\n"
            f"👉 Cukup tekan tahan tombol 'Log In' di email -> Copy Link URL -> Paste ke chat ini!",
            timeout_sec=300
        )

        if not user_inp:
            sys.exit(1)

        urls = re.findall(r"https?://[^\s]+", user_inp)
        magic_url = urls[0] if urls else user_inp
        redeem_res = redeem_magic_link_direct_api(page, magic_url)
        print(f"[MAGIC-LINK-REDEEM] Result: {redeem_res}")

        if not redeem_res.get("ok"):
            page.screenshot(path="reddit_redeem_failed.png")
            send_telegram_photo(
                "reddit_redeem_failed.png",
                f"❌ [ANTI-HALU STOP] Penukaran Magic Link ditolak server Reddit! Status={redeem_res.get('status')} Body={redeem_res.get('body') or redeem_res.get('error')}"
            )
            sys.exit(1)

        time.sleep(2)
        cookies = context.cookies()
        session_cookie = next((c for c in cookies if c.get("name") == "reddit_session"), None)
        if not session_cookie:
            page.screenshot(path="reddit_no_session_cookie.png")
            send_telegram_photo("reddit_no_session_cookie.png", "❌ [ANTI-HALU STOP] Cookie reddit_session belum ditemukan meskipun status 200.")
            sys.exit(1)

        clean_cookies = [c for c in cookies if c.get("name") != "token_v2"]
        with open(SESSION_FILE, "w") as f:
            json.dump(clean_cookies, f, indent=2)

        send_telegram("🎉 [TERVERIFIKASI] Cookie HttpOnly `reddit_session` berhasil didapatkan dan disimpan ke `session_reddit.json`!")
        page.goto(target_url, timeout=50000, wait_until="domcontentloaded")
        time.sleep(5)

    # Pastikan kita sudah di halaman target & jika mode search wajib sort=new (Anti-Buta Guard)
    if mode == "search" and "sort=new" not in page.url.lower():
        page.goto(target_url, timeout=50000, wait_until="domcontentloaded")
        time.sleep(5)

    final_state = inspect_real_screen_state(page, context)
    if mode == "search" and final_state.get("searchSort") and final_state.get("searchSort") != "NEW":
        print(f"⚠️ [ANTI-BUTA GUARD] Terdeteksi sort={final_state.get('searchSort')}, memaksa navigasi ulang ke type=posts&sort=new...")
        page.goto(f"https://www.reddit.com/search/?q={urllib.parse.quote(target)}&type=posts&sort=new", timeout=50000, wait_until="domcontentloaded")
        time.sleep(5)
        final_state = inspect_real_screen_state(page, context)

    for _ in range(3):
        page.mouse.wheel(0, 900)
        time.sleep(1.2)

    page.screenshot(path="reddit_snapshot.png")

    posts_data = page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        // 1. Ekstraksi presisi untuk halaman Search (search-post-unit / search-post-with-content-preview)
        const searchUnits = document.querySelectorAll('[data-testid="search-post-unit"], [data-testid="search-post-with-content-preview"]');
        searchUnits.forEach(u => {
            let sub = '';
            let author = '';
            let title = '';
            const trackers = u.querySelectorAll('search-telemetry-tracker[data-faceplate-tracking-context]');
            trackers.forEach(tr => {
                try {
                    const ctx = JSON.parse(tr.getAttribute('data-faceplate-tracking-context') || '{}');
                    if (ctx.subreddit && ctx.subreddit.name && !sub) sub = 'r/' + ctx.subreddit.name;
                    if (ctx.profile && ctx.profile.name && !author) author = ctx.profile.name;
                    if (ctx.post && ctx.post.title && !title) title = ctx.post.title;
                } catch (e) {}
            });

            const titleEl = u.querySelector('a[data-testid="post-title-text"], a[data-testid="post-title"]');
            if (!title && titleEl) title = titleEl.innerText.trim();
            const href = titleEl ? (titleEl.getAttribute('href') || '') : '';
            const fullUrl = href.startsWith('/') ? 'https://www.reddit.com' + href : href;

            const timeEl = u.querySelector('faceplate-timeago, time');
            const ts = timeEl ? (timeEl.getAttribute('ts') || timeEl.getAttribute('datetime') || '') : '';

            const counterRow = u.querySelector('[data-testid="search-counter-row"]');
            let score = '0';
            let comments = '0';
            if (counterRow) {
                const nums = counterRow.querySelectorAll('faceplate-number');
                if (nums.length >= 1) score = nums[0].getAttribute('number') || nums[0].innerText.trim() || '0';
                if (nums.length >= 2) comments = nums[1].getAttribute('number') || nums[1].innerText.trim() || '0';
            }

            let snippet = '';
            const previewEl = u.querySelector('[data-testid="search-post-content-preview"], p');
            if (previewEl && !previewEl.closest('[data-testid="search-counter-row"]')) {
                const txt = previewEl.innerText.trim();
                if (txt && txt !== title && !txt.includes('votes') && txt.length > 15) {
                    snippet = txt.slice(0, 260);
                }
            }

            if (title && !seen.has(title)) {
                seen.add(title);
                results.push({ title, sub: sub || 'r/reddit', author: author || 'redditor', ts, score, comments, snippet, url: fullUrl });
            }
        });

        // 2. Ekstraksi untuk halaman Subreddit (shreddit-post)
        const posts = document.querySelectorAll('shreddit-post');
        posts.forEach(p => {
            const title = p.getAttribute('post-title') || (p.querySelector('[slot="title"]') ? p.querySelector('[slot="title"]').innerText.trim() : '');
            const sub = p.getAttribute('subreddit-prefixed-name') || '';
            const author = p.getAttribute('author') || 'redditor';
            const score = p.getAttribute('score') || '0';
            const comments = p.getAttribute('comment-count') || '0';
            const ts = p.getAttribute('created-timestamp') || '';
            const permalink = p.getAttribute('permalink') || '';
            const fullUrl = permalink.startsWith('/') ? 'https://www.reddit.com' + permalink : permalink;
            const bodySlot = p.querySelector('[slot="text-body"]');
            const snippet = bodySlot ? bodySlot.innerText.trim().replace(/\\s+/g, ' ').slice(0, 280) : '';

            if (title && !seen.has(title)) {
                seen.add(title);
                results.push({ title, sub, author, ts, score, comments, snippet, url: fullUrl });
            }
        });

        return results.slice(0, 12);
    }""")

    print(f"Total unique posts collected: {len(posts_data)} (verified sort={final_state.get('searchSort')})")

    comments_data = []
    comments_state = None
    if mode == "search":
        comments_url = f"https://www.reddit.com/search/?q={urllib.parse.quote(target)}&type=comments&sort=new"
        print(f"💬 Mengambil isi komentar & diskusi live terbaru dari {comments_url}...")
        try:
            page.goto(comments_url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)
            comments_state = inspect_real_screen_state(page, context)
            for _ in range(3):
                page.mouse.wheel(0, 900)
                time.sleep(1.0)
            page.screenshot(path="reddit_comments_new.png")

            comments_data = page.evaluate("""() => {
                const list = [];
                const seenBody = new Set();
                const units = document.querySelectorAll('[data-testid="search-sdui-comment-unit"]');
                units.forEach(u => {
                    let sub = '';
                    let postTitle = '';
                    const trackers = u.querySelectorAll('search-telemetry-tracker[data-faceplate-tracking-context]');
                    trackers.forEach(tr => {
                        try {
                            const ctx = JSON.parse(tr.getAttribute('data-faceplate-tracking-context') || '{}');
                            if (ctx.subreddit && ctx.subreddit.name && !sub) sub = 'r/' + ctx.subreddit.name;
                            if (ctx.post && ctx.post.title && !postTitle) postTitle = ctx.post.title;
                        } catch (e) {}
                    });

                    const userEl = u.querySelector('a[href^="/user/"]');
                    let author = userEl ? userEl.innerText.trim() : '';
                    if (!author && userEl) {
                        const m = (userEl.getAttribute('href') || '').match(/\\/user\\/([^/]+)/);
                        if (m) author = m[1];
                    }
                    if (author.toLowerCase() === 'automoderator') return;

                    const timeEls = u.querySelectorAll('faceplate-timeago, time');
                    const ts = timeEls.length > 0 ? (timeEls[timeEls.length - 1].getAttribute('ts') || '') : '';

                    const bodyEl = u.querySelector('.i18n-search-comment-content, [data-testid="search-comment-content"]');
                    let body = bodyEl ? bodyEl.innerText.trim().replace(/\\s+/g, ' ') : '';
                    if (!body || body.length < 20) return;
                    if (body.includes('check out the rules') || body.includes('I am a bot')) return;

                    const numEl = u.querySelector('faceplate-number');
                    const votes = numEl ? (numEl.getAttribute('number') || numEl.innerText.trim() || '1') : '1';

                    const linkEl = u.querySelector('a[href*="/comments/"]');
                    const href = linkEl ? (linkEl.getAttribute('href') || '') : '';
                    const url = href.startsWith('/') ? 'https://www.reddit.com' + href : href;

                    const normKey = body.slice(0, 120).toLowerCase();
                    if (!seenBody.has(normKey)) {
                        seenBody.add(normKey);
                        list.push({
                            sub: sub || 'r/reddit',
                            postTitle: postTitle || 'Diskusi Reddit',
                            author: author || 'redditor',
                            ts,
                            votes,
                            body: body.slice(0, 360),
                            url
                        });
                    }
                });
                return list.slice(0, 8);
            }""")
            print(f"Total unique live comments collected: {len(comments_data)} (verified sort={comments_state.get('searchSort')})")
        except Exception as ce:
            print(f"Warning comment extraction: {ce}")

    if posts_data or comments_data:
        sort_badge = final_state.get("searchSort") or "NEW"
        if posts_data:
            post_lines = []
            for idx, p in enumerate(posts_data[:8], 1):
                wib_str = format_iso_to_wib(p.get("ts", ""))
                sub_prefix = f"[{p['sub']}] " if p.get("sub") else ""
                line = (
                    f"{idx}. 📌 {sub_prefix}{p['title']}\n"
                    f"   🕒 {wib_str} | 👤 u/{p['author']} | ⬆️ {p['score']} | 💬 {p['comments']}\n"
                )
                if p.get("snippet"):
                    line += f"   📝 \"{p['snippet']}...\"\n"
                line += f"   🔗 {p['url']}"
                post_lines.append(line)

            msg_posts = (
                f"🔥 Postingan TERBARU di {label} (Terverifikasi DOM sort={sort_badge} | {len(post_lines)} Thread):\n\n"
                + "\n\n───────────────────\n\n".join(post_lines)
            )
            if len(msg_posts) > 3900:
                send_telegram(msg_posts[:3900])
            else:
                send_telegram(msg_posts)
            time.sleep(0.5)

        if comments_data:
            comm_sort_badge = (comments_state or {}).get("searchSort") or "NEW"
            comm_lines = []
            for idx, c in enumerate(comments_data[:8], 1):
                wib_str = format_iso_to_wib(c.get("ts", ""))
                line = (
                    f"{idx}. 💬 [{c['sub']}] u/{c['author']} • 🕒 {wib_str} (⬆️ {c['votes']})\n"
                    f"   🧵 Thread: {c['postTitle'][:80]}\n"
                    f"   🗣️ \"{c['body']}\"\n"
                    f"   🔗 {c['url']}"
                )
                comm_lines.append(line)

            msg_comms = (
                f"⚡ Opini & Komentar LIVE TERBARU Reddit '{target}' (Terverifikasi DOM sort={comm_sort_badge} | {len(comm_lines)} Komentar):\n\n"
                + "\n\n───────────────────\n\n".join(comm_lines)
            )
            if len(msg_comms) > 3900:
                mid = len(comm_lines) // 2
                send_telegram(
                    f"⚡ Opini & Komentar LIVE TERBARU Reddit '{target}' (Bagian 1 | sort={comm_sort_badge}):\n\n"
                    + "\n\n───────────────────\n\n".join(comm_lines[:mid])
                )
                time.sleep(0.5)
                send_telegram(
                    f"⚡ Lanjutan Komentar LIVE Reddit '{target}' (Bagian 2 | sort={comm_sort_badge}):\n\n"
                    + "\n\n───────────────────\n\n".join(comm_lines[mid:])
                )
            else:
                send_telegram(msg_comms)

        send_telegram_photo(
            "reddit_snapshot.png",
            f"📸 Bukti Layar Posts: {label} (DOM sort={sort_badge} | user-logged-in={final_state['userLoggedInAttr']})"
        )
        if os.path.exists("reddit_comments_new.png") and comments_data:
            send_telegram_photo(
                "reddit_comments_new.png",
                f"📸 Bukti Layar Komentar Live: '{target}' (DOM sort={(comments_state or {}).get('searchSort')})"
            )
        return "SUCCESS"
    else:
        send_telegram_photo("reddit_snapshot.png", f"⚠️ Posisi: {final_state['state']} | URL: {final_state['url']} | Tidak ada hasil yang ditemukan.")
        return "NO_POSTS"

def login_and_search_reddit(target="Barca", mode="sub"):
    send_telegram(f"🔴 [Reddit Relay] Menjalankan Reddit Pulse Engine untuk '{target}' (Mode: {mode})...")
    # Prioritas 1: Karena sudah punya cookie reddit_session resmi, coba Direct IP lebih dulu (jauh lebih cepat & tidak kena rotasi IP kotor),
    # jika kena blokir baru fallback ke Residential Proxy.
    res = run_session_workflow(target, mode, None)
    if res in ("BLOCKED_WITH_SESSION", "BLOCKED_NO_SESSION"):
        proxy_cfg = get_proxy_config()
        if proxy_cfg:
            print("Fallback ke Residential Proxy...")
            run_session_workflow(target, mode, proxy_cfg)

if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "sub"
    target_arg = sys.argv[2] if len(sys.argv) > 2 else "Barca"
    login_and_search_reddit(target_arg, mode_arg)

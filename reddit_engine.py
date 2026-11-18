import sys
import os
import time
import requests
from camoufox.sync_api import Camoufox

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TELEGRAM_TOKEN_PROTECTED")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1936436999")

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

def search_reddit(target, mode="search"):
    """
    mode: 'search' (cari topik di seluruh reddit) atau 'sub' (buka subreddit r/<target>/new)
    """
    if mode == "sub":
        sub_name = target.replace("r/", "").strip()
        url = f"https://www.reddit.com/r/{sub_name}/new/"
        label = f"r/{sub_name} (Newest Posts)"
    else:
        url = f"https://www.reddit.com/search/?q={target}&sort=new"
        label = f"Reddit Search '{target}' (Sort: New)"

    send_telegram(f"🔴 [Reddit Relay] Menjelajahi {label} via Camoufox Stealth Engine...")
    
    with Camoufox(headless=True, i_know_what_im_doing=True) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        
        print(f"Navigating to {url}...")
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(5)
        except Exception as e:
            print(f"Navigation notice: {e}")
            
        # Scroll bertahap untuk memicu react lazy load postingan Reddit
        for _ in range(4):
            page.mouse.wheel(0, 800)
            time.sleep(1.5)
            
        page.screenshot(path="reddit_snapshot.png")
        
        # Ekstraksi postingan Reddit (dukung modern shreddit-post & article selector)
        posts_data = []
        
        # Coba selector shreddit-post (Reddit modern 2024-2026)
        shreddit_posts = page.locator("shreddit-post").all()
        if shreddit_posts:
            print(f"Detected {len(shreddit_posts)} shreddit-post elements!")
            for p in shreddit_posts[:15]:
                try:
                    title = p.get_attribute("post-title") or p.locator("a[slot='title']").inner_text().strip()
                except Exception:
                    title = "Untitled Post"
                try:
                    author = p.get_attribute("author") or "anonymous"
                except Exception:
                    author = "anonymous"
                try:
                    score = p.get_attribute("score") or "0"
                except Exception:
                    score = "0"
                try:
                    comments = p.get_attribute("comment-count") or "0"
                except Exception:
                    comments = "0"
                try:
                    permalink = p.get_attribute("permalink") or ""
                    post_url = f"https://reddit.com{permalink}" if permalink.startswith("/") else permalink
                except Exception:
                    post_url = ""

                posts_data.append({
                    "title": title,
                    "author": author,
                    "score": score,
                    "comments": comments,
                    "url": post_url
                })
        else:
            # Fallback selector standard
            print("Fallback to standard post link selectors...")
            post_links = page.locator("a[data-testid='post-title'], a[href*='/comments/']").all()
            seen_titles = set()
            for a in post_links:
                try:
                    txt = a.inner_text().strip()
                    href = a.get_attribute("href") or ""
                    if txt and len(txt) > 5 and txt not in seen_titles:
                        seen_titles.add(txt)
                        post_url = f"https://reddit.com{href}" if href.startswith("/") else href
                        posts_data.append({
                            "title": txt,
                            "author": "Reddit User",
                            "score": "-",
                            "comments": "-",
                            "url": post_url
                        })
                except Exception:
                    pass
                if len(posts_data) >= 15:
                    break

        print(f"Extracted {len(posts_data)} Reddit posts!")
        
        if posts_data:
            results_text = []
            for idx, p in enumerate(posts_data[:12], 1):
                item = f"{idx}. 📌 {p['title']}\n   👤 u/{p['author']} | ⬆️ {p['score']} | 💬 {p['comments']} komentar\n   🔗 {p['url']}"
                results_text.append(item)
            
            report = f"🔥 Postingan Terhangat di {label}:\n\n" + "\n\n───────────────────\n\n".join(results_text)
            
            # Message chunking jika mendekati batas 4096 karakter
            if len(report) > 3800:
                mid = len(results_text) // 2
                chunk1 = f"🔥 Postingan Terhangat di {label} (Bagian 1):\n\n" + "\n\n───────────────────\n\n".join(results_text[:mid])
                chunk2 = f"🔥 Lanjutan {label} (Bagian 2):\n\n" + "\n\n───────────────────\n\n".join(results_text[mid:])
                send_telegram(chunk1)
                time.sleep(0.5)
                send_telegram(chunk2)
            else:
                send_telegram(report)
                
            send_telegram_photo("reddit_snapshot.png", f"📸 Bukti Reddit: {label}")
        else:
            send_telegram(f"⚠️ Tidak ada postingan yang berhasil ditarik dari {label}. Periksa screenshot.")
            send_telegram_photo("reddit_snapshot.png", f"Snapshot {label}")

if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "search"
    target_arg = sys.argv[2] if len(sys.argv) > 2 else "Barca"
    search_reddit(target_arg, mode_arg)

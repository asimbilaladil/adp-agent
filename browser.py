"""
browser.py - ADP Browser Automation
=====================================
ADPAgent handles:
  - Browser lifecycle (start / stop)
  - Login + 2FA (Gmail code + security question)
  - Candidate search
  - Resume download
  - Screenshot helpers
"""
import time, os, glob, shutil, re, logging, urllib.parse
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    import sys; sys.exit("Run: pip install playwright && playwright install chromium")

from config import (
    ADP_LOGIN_URL, ADP_RECRUITMENT_URL,
    ADP_USERNAME, ADP_PASSWORD,
    GMAIL_ADDRESS, GMAIL_PASSWORD,
    SECURITY_QUESTIONS,
    EXTENSION_PATH,
    BROWSER_PROFILE_DIR, RESUME_DOWNLOAD_DIR, SCREENSHOT_DIR,
    WAIT_AFTER_LOGIN, WAIT_AFTER_NAV,
)

log = logging.getLogger("adp_agent")


class ADPAgent:

    def __init__(self):
        self.pw = self.context = self.page = None

    # ═══════════════════════════════════════════════════════════
    # Browser lifecycle
    # ═══════════════════════════════════════════════════════════

    def start(self):
        log.info("Launching browser...")
        self.pw = sync_playwright().start()
        os.makedirs(RESUME_DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)

        args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1366,768",
            "--lang=en-US,en",
        ]
        if EXTENSION_PATH and os.path.isdir(EXTENSION_PATH):
            args += [f"--load-extension={EXTENSION_PATH}",
                     f"--disable-extensions-except={EXTENSION_PATH}"]

        launch_kwargs = dict(
            headless=True,
            args=args,
            viewport={"width": 1366, "height": 768},
            #proxy={"server": "http://23.95.150.145:6114", "username": "hobbrzyi", "password": "xnzemea2ibi6"},
            slow_mo=200,
            accept_downloads=True,
            downloads_path=RESUME_DOWNLOAD_DIR,
            timeout=60000,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ignore_https_errors=True,
            bypass_csp=True,
        )

        for attempt in range(1, 3):
            try:
                if attempt == 2:
                    log.info("Retrying with fresh profile...")
                    shutil.rmtree(BROWSER_PROFILE_DIR, ignore_errors=True)
                    os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
                self.context = self.pw.chromium.launch_persistent_context(
                    user_data_dir=BROWSER_PROFILE_DIR, **launch_kwargs)
                break
            except Exception as e:
                if attempt == 2: raise
                log.error(f"Browser launch failed: {e}")

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

        # Mask automation fingerprint
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
        """)

        log.info("Browser ready.")

    def stop(self):
        try:
            if self.context: self.context.close()
            if self.pw:      self.pw.stop()
        except Exception:
            pass
        log.info("Browser closed.")

    # ═══════════════════════════════════════════════════════════
    # Login
    # ═══════════════════════════════════════════════════════════

    def login(self):
        log.info(f"Opening: {ADP_LOGIN_URL}")
        self.page.goto(ADP_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        # ── Username ──
        username_field = self._wait_for_first([
            "#user-id", "#USER", "#userID", "#userId",
            "input[name='user']", "input[name='USER']",
            "input[name='username']", "input[name='userId']",
            "input[placeholder*='User' i]", "input[aria-label*='User' i]",
            "input[type='text']:visible", "input[id*='user' i]",
        ], timeout=15000)
        if not username_field:
            log.error("[X] Username field not found!")
            self.screenshot("error_login_username"); return False

        username_field.fill(ADP_USERNAME)
        log.info("  Username entered")

        next_btn = self._wait_for_first([
            "#verifUserid498", "button:has-text('Next')",
            "sdf-button:has-text('Next')", "button:has-text('Continue')",
            "button[type='submit']",
        ], timeout=5000)
        if next_btn: next_btn.click()
        else:        self.page.keyboard.press("Enter")

        # ── Password ──
        password_field = self._wait_for_first([
            "#password", "input[type='password']",
            "input[name='password']", "input[placeholder*='Password' i]",
        ], timeout=15000)
        if not password_field:
            log.error("[X] Password field not found!")
            self.screenshot("error_login_password"); return False

        password_field.fill(ADP_PASSWORD)
        log.info("  Password entered")

        signin_btn = self._wait_for_first([
            "#signBtn", "button:has-text('Sign In')",
            "sdf-button:has-text('Sign In')", "button[type='submit']",
        ], timeout=5000)
        if signin_btn: signin_btn.click()
        else:          self.page.keyboard.press("Enter")

        log.info("Waiting for login...")
        time.sleep(3)

        try:
            if self.page.locator("text=Verify Your Identity").first.is_visible(timeout=5000):
                log.info("  2FA detected!")
                if not self._handle_2fa(): return False
        except Exception as e:
            log.info(f"  No 2FA ({e}), continuing...")

        time.sleep(WAIT_AFTER_LOGIN)
        log.info("Login complete.")
        return True

    # ═══════════════════════════════════════════════════════════
    # 2FA
    # ═══════════════════════════════════════════════════════════

    def _handle_2fa(self):
        # Click "Send me an email"
        clicked = False
        for sel in [
            "text=Send me an email", "a:has-text('Send me an email')",
            "div:has-text('Send me an email')", "li:has-text('Send me an email')",
            "button:has-text('Send me an email')",
            "[role='option']:has-text('Send me an email')",
            "[role='listitem']:has-text('Send me an email')",
            "[class*='email']",
        ]:
            try:
                el = self.page.locator(sel).first
                if el.is_visible(timeout=3000):
                    el.click(); clicked = True
                    log.info("  Clicked 'Send me an email'"); break
            except Exception:
                continue

        if not clicked:
            try:
                self.page.evaluate("""
                    document.querySelectorAll('*').forEach(el => {
                        if (el.textContent.trim() === 'Send me an email' ||
                            el.innerText === 'Send me an email') el.click();
                    });
                """)
                log.info("  Clicked 'Send me an email' (JS)")
            except Exception:
                pass

        time.sleep(2)

        send_btn = self._wait_for_first([
            "button:has-text('Send Code')", "sdf-button:has-text('Send Code')",
            "button:has-text('Send')", "sdf-button:has-text('Send')",
            "button:has-text('Continue')", "button:has-text('Next')",
            "button[type='submit']",
        ], timeout=5000)
        if send_btn:
            send_btn.click(); log.info("  Clicked Send/Continue")

        time.sleep(3)

        log.info("  Fetching verification code from Gmail...")
        code = self._fetch_adp_code_from_gmail()
        if not code:
            log.error("[X] Could not get verification code!"); return False

        log.info(f"  Got code: {code}")

        # Enter code (JS first for Shadow DOM)
        code_entered = False
        try:
            code_entered = self.page.evaluate("""
                (code) => {
                    let inputs = document.querySelectorAll(
                        'input[type="text"], input[type="number"], input[type="tel"]');
                    for (const inp of inputs) {
                        if (inp.offsetParent !== null) {
                            inp.focus(); inp.value = code;
                            inp.dispatchEvent(new Event('input',  {bubbles:true}));
                            inp.dispatchEvent(new Event('change', {bubbles:true}));
                            return true;
                        }
                    }
                    for (const w of document.querySelectorAll(
                            'sdf-input, sdf-form-control-wrapper')) {
                        if (w.shadowRoot) {
                            const inp = w.shadowRoot.querySelector('input');
                            if (inp) {
                                inp.focus(); inp.value = code;
                                inp.dispatchEvent(new Event('input',  {bubbles:true}));
                                inp.dispatchEvent(new Event('change', {bubbles:true}));
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """, code)
        except Exception as e:
            log.error(f"  JS code entry error: {e}")

        if code_entered:
            log.info("  Code entered (JS)")
        else:
            for sel in [
                "input[type='text']:visible", "input[type='number']:visible",
                "input[type='tel']:visible", "input[placeholder*='code' i]",
                "input[aria-label*='code' i]", "input[name*='code' i]", "input[id*='code' i]",
            ]:
                try:
                    field = self.page.wait_for_selector(sel, timeout=3000)
                    if field and field.is_visible():
                        field.fill(code); code_entered = True
                        log.info(f"  Code entered ({sel})"); break
                except (PlaywrightTimeout, Exception):
                    continue

        if not code_entered:
            log.error("[X] Code input field not found!")
            self.screenshot("error_2fa_code_field"); return False

        # Click Verify
        time.sleep(1)
        verify_clicked = False
        for sel in [
            "sdf-button:has-text('Verify')", "sdf-button:has-text('Submit')",
            "sdf-button:has-text('Continue')", "button:has-text('Verify')",
            "button:has-text('Submit')", "button:has-text('Continue')",
            "button[type='submit']",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click(); verify_clicked = True
                    log.info(f"  Clicked Verify ({sel})"); break
            except Exception:
                continue

        if not verify_clicked:
            try:
                self.page.evaluate("""
                    document.querySelectorAll('sdf-button, button').forEach(b => {
                        const t = b.textContent.toLowerCase();
                        if (t.includes('verify') || t.includes('submit')) b.click();
                    });
                """)
                log.info("  Clicked Verify (JS)")
            except Exception:
                self.page.keyboard.press("Enter")

        time.sleep(5)
        self._handle_security_question()
        return True

    def _fetch_adp_code_from_gmail(self, max_wait=120):
      log.info("  Fetching verification code via IMAP...")
      import imapclient, email as emaillib
      start_time = time.time()
  
      while time.time() - start_time < max_wait:
          try:
              with imapclient.IMAPClient("imap.gmail.com", ssl=True) as client:
                  client.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
                  client.select_folder("INBOX")
  
                  # Search for ADP security email
                  messages = client.search(["FROM", "SecurityServices_NoReply@adp.com"])
                  if not messages:
                      log.info("  No ADP email yet, waiting...")
                      time.sleep(5)
                      continue
  
                  # Get the latest one
                  data = client.fetch(messages[-1], ["RFC822"])
                  raw = data[messages[-1]][b"RFC822"]
                  msg = emaillib.message_from_bytes(raw)
  
                  # Extract body
                  body = ""
                  if msg.is_multipart():
                      for part in msg.walk():
                          if part.get_content_type() == "text/plain":
                              body += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                          elif part.get_content_type() == "text/html" and not body:
                              html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                              # Strip HTML tags to get plain text
                              body = re.sub(r'<[^>]+>', ' ', html)
                  else:
                      raw_body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                      if "<html" in raw_body.lower():
                          body = re.sub(r'<[^>]+>', ' ', raw_body)
                      else:
                          body = raw_body
                  
                  # Find 6-digit code
                  code_match = re.search(r'\b(\d{6})\b', body)
                  if not code_match:
                      log.info("  No code in email yet, waiting...")
                      time.sleep(5)
                      continue
  
                  code = code_match.group(1)
                  log.info(f"  [OK] Found code via IMAP: {code}")
  
                  # Delete the email
                  try:
                      client.set_flags(messages[-1], [imapclient.DELETED])
                      client.expunge()
                      log.info("  Deleted ADP email")
                  except Exception:
                      pass
  
                  return code
  
          except Exception as e:
              log.error(f"  IMAP error: {e}")
              time.sleep(5)
  
      log.error("[X] Could not get verification code via IMAP!")
      return None
    def _delete_gmail_email(self, gmail_page):
        deleted = False
        try:
            gmail_page.keyboard.press("#"); time.sleep(1)
            deleted = True; log.info("  Deleted email (# key)")
        except Exception:
            pass

        if not deleted:
            for sel in [
                "[aria-label='Delete']", "[aria-label='Move to Trash']",
                "[data-tooltip='Delete']", "[data-tooltip='Move to Trash']",
                "button[aria-label='Delete']", "button[aria-label='Move to Trash']",
                "div[aria-label='Delete']", "div[aria-label='Move to Trash']",
            ]:
                try:
                    btn = gmail_page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(); deleted = True
                        log.info(f"  Deleted email ({sel})"); time.sleep(1); break
                except Exception:
                    continue

        if not deleted:
            for more_sel in [
                "[aria-label='More message options']",
                "button[aria-label='More message options']",
                "[data-tooltip='More']", "button[aria-label*='More']",
            ]:
                try:
                    more_btn = gmail_page.locator(more_sel).first
                    if more_btn.is_visible(timeout=2000):
                        more_btn.click(); time.sleep(2)
                        for del_sel in [
                            "[role='menuitem']:has-text('Move to Trash')",
                            "[role='menuitem']:has-text('Delete')",
                            "text=Move to Trash", "text=Delete",
                        ]:
                            try:
                                item = gmail_page.locator(del_sel).first
                                if item.is_visible(timeout=2000):
                                    item.click(); deleted = True
                                    log.info("  Deleted email (More menu)"); break
                            except Exception:
                                continue
                        if deleted: break
                except Exception:
                    continue

        if not deleted:
            log.warning("  Could not delete email - time filter will prevent reuse")

    def _handle_security_question(self):
        log.info("  Checking for security question...")
        time.sleep(5)
        self.screenshot("security_question_page")

        try:
            page_text = self.page.evaluate("""
                () => {
                    let text = document.body.innerText || '';
                    document.querySelectorAll('label').forEach(l => {
                        text += ' ' + l.textContent;
                    });
                    document.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) text += ' ' + (el.shadowRoot.textContent || '');
                    });
                    return text;
                }
            """)
        except Exception:
            try:    page_text = self.page.inner_text("body")
            except: page_text = ""

        page_lower = page_text.lower()
        if page_text:
            log.info(f"  Page text: {page_text[:300].replace(chr(10), ' ')}...")

        matched_answer = None
        for question_keywords, answer in SECURITY_QUESTIONS.items():
            if all(kw in page_lower for kw in question_keywords.lower().split()):
                matched_answer = answer
                log.info(f"  Matched: {question_keywords} -> {answer}"); break

        if not matched_answer:
            log.warning("  No security question matched (may not be required)."); return

        filled = False

        # Method 1: Direct locator
        try:
            inp = self.page.locator("input#input, sdf-input input").first
            if inp.is_visible(timeout=3000):
                inp.click(); inp.fill(matched_answer)
                filled = True; log.info("  Answer filled via locator")
        except Exception:
            pass

        # Method 2: JS / Shadow DOM
        if not filled:
            try:
                filled = self.page.evaluate("""
                    (answer) => {
                        let inputs = document.querySelectorAll(
                            'input[type="text"], input[type="password"], input:not([type])');
                        for (const inp of inputs) {
                            if (inp.offsetParent !== null && inp.id !== 'user-id') {
                                inp.focus(); inp.value = answer;
                                inp.dispatchEvent(new Event('input',  {bubbles:true}));
                                inp.dispatchEvent(new Event('change', {bubbles:true}));
                                return true;
                            }
                        }
                        for (const w of document.querySelectorAll(
                                'sdf-input, sdf-form-control-wrapper, [class*="form-control"]')) {
                            if (w.shadowRoot) {
                                const inp = w.shadowRoot.querySelector('input');
                                if (inp) {
                                    inp.focus(); inp.value = answer;
                                    inp.dispatchEvent(new Event('input',  {bubbles:true}));
                                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                """, matched_answer)
                if filled: log.info("  Answer filled via JS")
            except Exception as e:
                log.error(f"  JS fill error: {e}")

        # Method 3: Keyboard
        if not filled:
            try:
                label = self.page.locator(
                    "label:has-text('childhood'), label:has-text('nickname')").first
                if label.is_visible(timeout=2000):
                    label.click(); time.sleep(0.5)
                    self.page.keyboard.type(matched_answer)
                    filled = True; log.info("  Answer typed via keyboard")
            except Exception:
                pass

        if not filled:
            log.error("[X] Could not fill security answer!")
            self.screenshot("error_security_no_input"); return

        # Submit
        time.sleep(1)
        submit_clicked = False
        for sel in [
            "sdf-button:has-text('Submit')", "sdf-button:has-text('Verify')",
            "sdf-button:has-text('Continue')", "button:has-text('Submit')",
            "button:has-text('Verify')", "button:has-text('Continue')",
            "button[type='submit']",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click(); submit_clicked = True
                    log.info(f"  Clicked Submit ({sel})"); break
            except Exception:
                continue

        if not submit_clicked:
            try:
                self.page.evaluate("""
                    document.querySelectorAll('sdf-button, button').forEach(b => {
                        const t = b.textContent.toLowerCase();
                        if (t.includes('submit') || t.includes('verify') ||
                            t.includes('continue')) b.click();
                    });
                """)
                log.info("  Clicked Submit (JS)")
            except Exception:
                self.page.keyboard.press("Enter")

        log.info("  Security question handled!")

    # ═══════════════════════════════════════════════════════════
    # Navigation
    # ═══════════════════════════════════════════════════════════

    def go_to_candidates(self):
        log.info("Navigating to Recruitment page...")
        self.page.goto(ADP_RECRUITMENT_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(WAIT_AFTER_NAV)

        log.info("Clicking Candidates tab...")
        if not self._click([
            "text=Candidates", "a:has-text('Candidates')",
            "span:has-text('Candidates')", "li:has-text('Candidates')",
            "[role='tab']:has-text('Candidates')",
        ], "Candidates tab"):
            log.warning("  Could not click Candidates tab!")
            self.screenshot("error_candidates_tab"); return False

        time.sleep(WAIT_AFTER_NAV)

        log.info("  Waiting for Candidates list to fully load...")
        for _ in range(12):
            try:
                if self._find_search_box():
                    rows = self.page.locator("tr, [role='row']").all()
                    if len(rows) > 1:
                        log.info(f"  Candidates list ready ({len(rows)} rows)."); return True
            except Exception:
                pass
            log.info("  Still waiting..."); time.sleep(2)

        log.warning("  Candidates list may not be fully loaded - proceeding anyway.")
        self.screenshot("warn_candidates_load")
        return True

    # ═══════════════════════════════════════════════════════════
    # Search
    # ═══════════════════════════════════════════════════════════

    def search(self, candidate_name: str) -> bool:
        log.info(f"  Searching: {candidate_name}")
        search_box = self._find_search_box()
        if not search_box: return False

        search_box.click()
        search_box.fill(candidate_name)
        search_box.press("Enter")
        time.sleep(5)

        try:
            if self.page.locator("text=No results").first.is_visible(timeout=3000):
                log.warning(f"  No results for: {candidate_name}"); return False
        except Exception:
            pass

        log.info(f"  Found: {candidate_name}")
        return True

    # ═══════════════════════════════════════════════════════════
    # Resume download
    # ═══════════════════════════════════════════════════════════

    def download_resume(self, candidate_name: str, email_id: str):
        log.info(f"Downloading resume for: {candidate_name}")
        last_name  = candidate_name.strip().split()[-1]
        first_name = candidate_name.strip().split()[0]
        download_clicked = False

        # Strategy 1: Find candidate row -> click its download icon
        try:
            for row in self.page.locator("tr, [role='row']").all():
                row_text = row.inner_text()
                if (last_name.lower()  in row_text.lower() and
                    first_name.lower() in row_text.lower()):
                    log.info("  Found candidate row")
                    for icon_sel in [
                        "button[title*='Download' i]", "button[title*='Attachment' i]",
                        "a[title*='Download' i]", "a[title*='Attachment' i]",
                        "img[title*='Download' i]", "img[alt*='Download' i]",
                        "[aria-label*='Download' i]", "[aria-label*='Attachment' i]",
                        "[data-action*='download' i]", "[data-action*='attachment' i]",
                    ]:
                        try:
                            icon = row.locator(icon_sel).first
                            if icon.is_visible(timeout=2000):
                                icon.click(); download_clicked = True
                                log.info(f"  Clicked download icon: {icon_sel}"); break
                        except Exception:
                            continue
                    if download_clicked: break
        except Exception as e:
            log.error(f"  Row search error: {e}")

        # Strategy 2: First download icon on page
        if not download_clicked:
            for sel in [
                "button[title*='Download' i]", "button[title*='Attachment' i]",
                "[aria-label*='Download' i]", "[aria-label*='Attachment' i]",
                "td button:has(svg)", "td button:has(img)",
            ]:
                try:
                    icons = self.page.locator(sel).all()
                    if icons:
                        icons[0].click(); download_clicked = True
                        log.info(f"  Clicked first icon: {sel}"); break
                except Exception:
                    continue

        if not download_clicked:
            log.error("[X] Could not find download icon!")
            self.screenshot("error_no_download_icon"); return None

        # Wait for download modal
        time.sleep(2)
        modal_found = False
        for sel in [
            "text=Download Attachments",
            "[role='dialog']:has-text('Download')",
            "[class*='modal']:has-text('Download')",
        ]:
            try:
                if self.page.wait_for_selector(sel, timeout=5000):
                    modal_found = True; log.info("  Download modal appeared"); break
            except PlaywrightTimeout:
                continue

        if not modal_found:
            log.error("[X] Download modal did not appear!")
            self.screenshot("error_no_modal"); return None

        # Click Download button in modal
        time.sleep(1)
        btn_clicked = False
        for sel in [
            "#attachmnet_modal_download_btn",
            "sdf-button#attachmnet_modal_download_btn",
            "sdf-button[aria-label='Download']",
            "[aria-label='Download'][role='button']",
            "sdf-button:has-text('Download')",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click(); btn_clicked = True
                    log.info(f"  Clicked Download ({sel})"); break
            except Exception:
                continue

        if not btn_clicked:
            try:
                self.page.evaluate("""
                    const btn = document.querySelector('#attachmnet_modal_download_btn');
                    if (btn) btn.click();
                """)
                btn_clicked = True; log.info("  Clicked Download (JS)")
            except Exception:
                pass

        if not btn_clicked:
            log.error("[X] Could not click Download button!")
            self.screenshot("error_no_download_btn"); return None

        log.info("  Waiting for download to complete...")
        time.sleep(8)
        save_path = self._find_and_save_download(candidate_name, email_id)
        self._close_modal()
        return save_path

    def _find_and_save_download(self, candidate_name, email_id):
        safe_name     = candidate_name.replace(" ", "_").replace(",", "")
        safe_email_id = str(email_id).strip()
        search_dirs   = [
            RESUME_DOWNLOAD_DIR,
            os.path.expanduser("~/Downloads"),
            os.path.join(BROWSER_PROFILE_DIR, "Default", "Downloads"),
            os.path.join(BROWSER_PROFILE_DIR, "Downloads"),
        ]
        now = time.time()
        best_file, best_time = None, 0

        for d in search_dirs:
            if not os.path.isdir(d): continue
            for f in glob.glob(os.path.join(d, "*")):
                if not os.path.isfile(f): continue
                mtime = os.path.getmtime(f)
                if (now - mtime < 30 and mtime > best_time
                        and "_Resume" not in os.path.basename(f)):
                    best_file, best_time = f, mtime

        if not best_file:
            log.warning("  No file in last 30s, retrying with 60s window...")
            time.sleep(3)
            for d in search_dirs:
                if not os.path.isdir(d): continue
                for f in glob.glob(os.path.join(d, "*")):
                    if (os.path.isfile(f)
                            and (time.time() - os.path.getmtime(f)) < 60
                            and "_Resume" not in os.path.basename(f)):
                        best_file = f; break
                if best_file: break

        if not best_file:
            log.error("[X] Could not find downloaded file!"); return None

        ext       = os.path.splitext(best_file)[1] or ".pdf"
        save_path = os.path.join(RESUME_DOWNLOAD_DIR,
                                 f"{safe_name}_{safe_email_id}_Resume{ext}")
        try:
            shutil.move(best_file, save_path)
            log.info(f"  [OK] Saved: {save_path}")
        except Exception:
            try:
                shutil.copy2(best_file, save_path)
                log.info(f"  [OK] Copied: {save_path}")
            except Exception as e:
                log.error(f"  Save error: {e}"); return None
        return save_path

    def _close_modal(self):
        try:
            if not self.page.locator(
                    "text=Download Attachments").first.is_visible(timeout=2000):
                log.info("  Modal already closed."); return
        except Exception:
            return

        log.info("  Closing modal...")
        for sel in [
            "button:has-text('Cancel')", "sdf-button:has-text('Cancel')",
            "[aria-label='Cancel']", "button[aria-label='Close']",
            "button[aria-label='close']", "[aria-label='Close dialog']",
            "[class*='close']", "button:has-text('×')",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click(); log.info(f"  Modal closed ({sel})")
                    time.sleep(1); return
            except Exception:
                continue

        try:
            self.page.keyboard.press("Escape")
            log.info("  Modal closed (Escape)"); time.sleep(1)
        except Exception:
            pass

    def clear_search(self):
        try:
            for sel in [
                "button[aria-label*='clear' i]", "button[title*='clear' i]",
                "[class*='clear']", ".search-clear",
            ]:
                try:
                    btn = self.page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(); log.info("  Cleared search")
                        time.sleep(1); return
                except Exception:
                    continue
            box = self._find_search_box()
            if box:
                box.fill(""); box.press("Enter")
                time.sleep(2); log.info("  Cleared search (manual)")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════

    def _wait_for_first(self, selectors, timeout=5000):
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            for sel in selectors:
                try:
                    el = self.page.wait_for_selector(sel, timeout=1000)
                    if el and el.is_visible():
                        log.info(f"  Found: {sel}"); return el
                except (PlaywrightTimeout, Exception):
                    continue
        return None

    def _find_search_box(self):
        # Strategy 1: Input near Filters button
        try:
            filters = self.page.locator("text=Filters").first
            if filters.is_visible(timeout=3000):
                for levels in ["../..", "../../..", "../../../.."]:
                    try:
                        parent = filters.locator(f"xpath={levels}")
                        search = parent.locator("input[placeholder*='Search' i]").first
                        if search.is_visible(timeout=1000):
                            log.info("  Found search box near Filters"); return search
                    except Exception:
                        continue
        except Exception:
            pass

        # Strategy 2: Non-header search input
        try:
            all_inputs = self.page.locator("input[placeholder*='Search' i]").all()
            log.info(f"  Found {len(all_inputs)} search input(s)")
            for inp in all_inputs:
                try:
                    if not inp.is_visible(): continue
                    is_header = inp.evaluate("""
                        (el) => {
                            let p = el;
                            while (p) {
                                const tag = (p.tagName || '').toLowerCase();
                                const cls = (p.className || '').toLowerCase();
                                if (['header','nav'].includes(tag) ||
                                    ['header','top-bar','navbar','banner','globalSearch']
                                    .some(c => cls.includes(c))) return true;
                                p = p.parentElement;
                            }
                            return false;
                        }
                    """)
                    if not is_header:
                        log.info("  Found candidates search (non-header)"); return inp
                except Exception:
                    continue

            if len(all_inputs) >= 2:
                el = all_inputs[-1]
                if el.is_visible():
                    log.info("  Using last search input (fallback)"); return el
        except Exception:
            pass

        # Strategy 3: By vertical position
        for sel in ["input[placeholder='Search...']", "input[placeholder='Search']"]:
            try:
                for inp in self.page.locator(sel).all():
                    if inp.is_visible():
                        box = inp.bounding_box()
                        if box and box['y'] > 400:
                            log.info(f"  Found search by position (y={box['y']})"); return inp
            except Exception:
                continue

        log.error("  Search box not found!")
        self.screenshot("error_no_search"); return None

    def _click(self, selectors, label):
        for sel in selectors:
            try:
                el = self.page.wait_for_selector(sel, timeout=5000)
                if el and el.is_visible():
                    el.click(); log.info(f"  Clicked: {label}"); return True
            except (PlaywrightTimeout, Exception):
                continue
        log.error(f"  [X] Not found: {label}")
        self.screenshot(f"error_{label}"); return False

    def screenshot(self, name="screen"):
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        ts   = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{name}_{ts}.png")
        try:
            self.page.screenshot(path=path); log.info(f"  Screenshot: {path}")
        except Exception:
            pass

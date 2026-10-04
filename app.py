from datetime import datetime, timedelta
import io
import random
import re
import time
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
import streamlit as st
from bs4 import BeautifulSoup
import urllib3
from urllib3.util.retry import Retry

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 頁面基本設定
st.set_page_config(
    page_title="Pachinko 手動切換 IP 批次擷取工具",
    page_icon="🎰",
    layout="centered",
)

st.title("🎰 Pachinko 數據自動擷取工具 v2.2 (手動 Proxy 切換版)")

# ================= 輔助解析函式 =================
def extract_led_number(element):
    """解析數字或圖片 LED 數字"""
    if not element:
        return "-"
    imgs = element.find_all("img")
    if imgs:
        digits = []
        for img in imgs:
            src = img.get("src", "").lower()
            alt = img.get("alt", "")
            if "blank" in src:
                continue
            if alt == "/" or "slash" in src:
                digits.append("/")
            elif alt.isdigit():
                digits.append(alt)
            else:
                filename = src.split("/")[-1]
                match = re.search(r"(\d+)(?=\.[a-z]+$)", filename) or re.search(
                    r"(\d+)", filename
                )
                if match:
                    digits.append(match.group(1))
        if digits:
            return "".join(digits)
    text = element.get_text(strip=True)
    clean = re.sub(r"[^\d/.-]", "", text)
    return clean if clean else "-"


# ================= UI 設定區塊 =================

# 1. 手動 Proxy 輸入區塊
with st.expander("🌐 手動 Proxy IP 設定 (每批次可更換)", expanded=True):
    proxy_input = st.text_input(
        "請貼上目前的 Proxy IP:",
        placeholder="例如 123.45.67.89:8080 或 http://123.45.67.89:8080",
        help="留空則使用 Streamlit Cloud 預設 IP (極易被擋)。",
    )

# 2. Cookie 與 URL 區塊
cookie_input = st.text_input(
    "請貼上最新 Cookie:",
    type="password",
    help="直接貼上即可，開頭如果有 'Cookie:' 程式會自動過濾清除。",
)
base_url = st.text_input(
    "請貼上店鋪網址 (或任意該店之頁面 URL):",
    value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=228",
)

# 3. 台號區域 (建議每批設定 50~100 台)
col1, col2 = st.columns(2)
with col1:
    start_num = st.number_input("起始台號:", min_value=1, max_value=9999, value=1)
with col2:
    end_num = st.number_input("結束台號:", min_value=1, max_value=9999, value=100)

# 4. 日期區域 (雙欄)
today = datetime.now().date()
col3, col4 = st.columns(2)
with col3:
    selected_start_date = st.date_input("起始日期:", value=today)
with col4:
    selected_end_date = st.date_input("結束日期:", value=today)

# ================= 執行邏輯 =================

if st.button("🚀 開始擷取本批次數據", type="primary", use_container_width=True):
    clean_cookie = re.sub(
        r"^cookie:\s*", "", cookie_input.strip(), flags=re.IGNORECASE
    )
    clean_proxy = proxy_input.strip()

    # 自動格式化 Proxy 字串
    proxies_config = None
    if clean_proxy:
        if not clean_proxy.startswith("http://") and not clean_proxy.startswith("https://"):
            formatted_proxy = f"http://{clean_proxy}"
        else:
            formatted_proxy = clean_proxy
        proxies_config = {
            "http": formatted_proxy,
            "https": formatted_proxy,
        }

    # 表單驗證
    if not clean_cookie:
        st.warning("⚠️ 請先填寫 Cookie！")
    elif not base_url:
        st.warning("⚠️ 請填寫店鋪或頁面 URL！")
    elif start_num > end_num:
        st.error("❌ 起始台號不可以大於結束台號！")
    elif selected_start_date > selected_end_date:
        st.error("❌ 起始日期不可以大於結束日期！")
    else:
        status_container = st.status("任務啟動中...", expanded=True)
        log_box = st.empty()
        log_messages = []

        def log(msg):
            log_messages.append(msg)
            log_box.code("\n".join(log_messages[-15:]), language="text")

        if proxies_config:
            log(f"🌐 目前使用 Proxy: {formatted_proxy}")
        else:
            log("⚠️ 未設定 Proxy，將使用預設 Cloud IP 嘗試直連...")

        log(f"開始掃描台號範圍：{start_num} ~ {end_num}")
        log(f"篩選日期範圍：{selected_start_date} 至 {selected_end_date}")

        if "id=" in base_url:
            url_template = re.sub(r"id=\d+", "id={}", base_url)
        else:
            url_template = (
                base_url + "&id={}" if "?" in base_url else base_url + "?id={}"
            )

        session = requests.Session()
        retries = Retry(
            total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; SM-S938U Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/110.0.5481.154 Mobile Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "X-Requested-With": "com.dmm.ptown",
            "Referer": "https://sunpo-to.a.p-moba.net/",
            "Cookie": clean_cookie,
            "Connection": "close",
        }

        machine_ids = list(range(start_num, end_num + 1))
        results = []
        base_date = datetime.now()

        date_mapping = [
            ("今日", base_date),
            ("昨日", base_date - timedelta(days=1)),
            ("2日前", base_date - timedelta(days=2)),
            ("3日前", base_date - timedelta(days=3)),
            ("4日前", base_date - timedelta(days=4)),
            ("5日前", base_date - timedelta(days=5)),
            ("6日前", base_date - timedelta(days=6)),
        ]

        pachinko_count = 0
        is_blocked = False
        consecutive_failures = 0  # 失敗計數器

        for idx, m_id in enumerate(machine_ids, start=1):
            url = url_template.format(m_id)

            if idx > 1 and idx % 35 == 0:
                pause_time = random.uniform(5, 10)
                log(f"☕ 已連續掃描 {idx} 台，暫停 {pause_time:.1f} 秒...")
                time.sleep(pause_time)

            try:
                resp = session.get(
                    url,
                    headers=headers,
                    proxies=proxies_config,
                    timeout=10,
                    verify=False,
                )
                if resp.status_code != 200:
                    log(f"✕ 台號 {m_id} 回傳狀態碼 {resp.status_code}")
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        log("⚠️️ 連續 5 次請求失敗，Proxy 可能已失效！")
                        break
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                title = soup.title.string.strip() if soup.title else ""

                if "遊技データをご覧のお客様へ" in title:
                    log(f"❌ 台號 {m_id} 被驗證頁面攔截！目前的 Proxy 已被封鎖或 Cookie 過期。")
                    is_blocked = True
                    break

                clean_title = (
                    title.split("|")[0].strip() if "|" in title else title
                )
                items = soup.find_all(
                    "div",
                    class_=lambda c: c
                    and ("c-data-pachinko__item" in c or "item" in c),
                )

                if not items:
                    continue

                if (
                    clean_title.startswith("S")
                    or "スロット" in clean_title
                    or "パチスロ" in clean_title
                ):
                    if not clean_title.startswith("P"):
                        time.sleep(0.2)
                        continue

                full_text = soup.get_text()
                if "スロット" in full_text and "パチンコ" not in full_text:
                    time.sleep(0.2)
                    continue

                rate_match = re.search(r"(\d+(?:\.\d+)?)\s*円", full_text)
                rate_str = f"{rate_match.group(1)}円" if rate_match else "-"

                pachinko_count += 1
                consecutive_failures = 0  # 成功時歸零
                day_idx = 0
                raw_date, real_date = date_mapping[day_idx]

                current_data = {
                    "台號": m_id,
                    "玩法費率": rate_str,
                    "機種名稱": clean_title,
                    "西元日期": real_date.strftime("%Y-%m-%d"),
                    "_date_obj": real_date.date(),
                }

                for item in items:
                    text_div = item.find("div", class_=lambda c: c and "text" in c)
                    if not text_div:
                        continue

                    label = text_div.get_text(strip=True)
                    img_div = item.find(
                        "div",
                        class_=lambda c: c and ("images" in c or "img" in c),
                    )
                    val = extract_led_number(img_div if img_div else item)

                    if label in current_data:
                        if (
                            selected_start_date
                            <= current_data["_date_obj"]
                            <= selected_end_date
                        ):
                            results.append(current_data)

                        day_idx += 1
                        if day_idx < len(date_mapping):
                            raw_date, real_date = date_mapping[day_idx]
                        else:
                            raw_date, real_date = (
                                f"第{day_idx+1}天",
                                base_date - timedelta(days=day_idx),
                            )

                        current_data = {
                            "台號": m_id,
                            "玩法費率": rate_str,
                            "機種名稱": clean_title,
                            "西元日期": real_date.strftime("%Y-%m-%d"),
                            "_date_obj": real_date.date(),
                        }
                    current_data[label] = val

                if current_data and len(current_data) > 5:
                    if (
                        selected_start_date
                        <= current_data["_date_obj"]
                        <= selected_end_date
                    ):
                        results.append(current_data)

                log(f"台號 {m_id:3d}: [P] [{rate_str}] 解析成功 ({clean_title})")

            except Exception as e:
                log(f"✕ 抓取失敗 {m_id}: {e}")
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    log("❌ 連續連線失敗 5 次，目前的 Proxy 無法連線！請換一個 Proxy。")
                    break

            time.sleep(random.uniform(0.8, 1.5))

        # 完成數據處理與導出
        if results:
            df = pd.DataFrame(results)
            if "_date_obj" in df.columns:
                df = df.drop(columns=["_date_obj"])

            base_cols = ["台號", "玩法費率", "機種名稱", "西元日期"]
            other_cols = [c for c in df.columns if c not in base_cols]
            df = df[base_cols + other_cols]

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Data")
            excel_data = output.getvalue()

            filename = f"pachinko_{start_num}_{end_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

            status_container.update(
                label=f"🎉 本批次抓取完成！共取得 {pachinko_count} 台數據",
                state="complete",
                expanded=False,
            )
            st.success(f"✅ 台號 {start_num} ~ {end_num} 處理完畢，請下載 Excel！")

            st.download_button(
                label=f"📥 下載批次檔 ({start_num}~{end_num})",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

            st.dataframe(df.head(10), use_container_width=True)

        elif is_blocked:
            status_container.update(
                label="❌ 中斷：目前的 Proxy/IP 被驗證頁面攔截，請輸入新的日本 Proxy IP！",
                state="error",
            )
        else:
            status_container.update(
                label="⚠️ 批次終止：未取得數據或 Proxy 連線逾時，請替換 Proxy 後重試。",
                state="error",
            )

import re
import time
import random
from datetime import datetime, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import urllib3
import streamlit as st

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="Pachinko 數據自動擷取工具",
    page_icon="🎰",
    layout="centered",
)

st.title("🎰 Pachinko 數據自動擷取工具")
st.caption("iPad / iPhone / 電腦皆可使用的 Streamlit 網頁版")

# -----------------------------
# 工具函式
# -----------------------------
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
                match = (
                    re.search(r"(\d+)(?=\.[a-z]+$)", filename)
                    or re.search(r"(\d+)", filename)
                )
                if match:
                    digits.append(match.group(1))

        if digits:
            return "".join(digits)

    text = element.get_text(strip=True)
    clean = re.sub(r"[^\d/.-]", "", text)
    return clean if clean else "-"


def make_url_template(base_url):
    """把 URL 裡的 id 轉成可替換的 {}"""
    if "id=" in base_url:
        return re.sub(r"id=\d+", "id={}", base_url)

    if "?" in base_url:
        return base_url + "&id={}"

    return base_url + "?id={}"


def build_session():
    """建立 Requests Session + Retry"""
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def run_scraper(cookie, base_url, start_num, end_num, selected_start_date, selected_end_date):
    """
    執行抓取。
    回傳：
        df, logs, pachinko_count
    """

    logs = []

    def log(message):
        logs.append(message)

    if start_num > end_num:
        raise ValueError("起始台號不能大於結束台號。")

    if selected_start_date > selected_end_date:
        raise ValueError("起始日期不能大於結束日期。")

    if not cookie:
        raise ValueError("請先填寫 Cookie。")

    if not base_url:
        raise ValueError("請填寫店鋪或頁面 URL。")

    url_template = make_url_template(base_url)

    session = build_session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; SM-S938U Build/V417IR; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "X-Requested-With": "com.dmm.ptown",
        "Referer": "https://sunpo-to.a.p-moba.net/",
        "Cookie": cookie,
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

    log("=" * 50)
    log(f"開始掃描台號範圍：{start_num} ~ {end_num}")
    log(f"篩選日期範圍：{selected_start_date} 至 {selected_end_date}")

    for idx, m_id in enumerate(machine_ids, start=1):
        url = url_template.format(m_id)

        # 每 35 台休息，保留原本程式的節奏
        if idx > 1 and idx % 35 == 0:
            pause_time = random.uniform(8, 15)
            log(f"☕ 已連續掃描 {idx} 台，自動暫停 {pause_time:.1f} 秒...")
            time.sleep(pause_time)

        try:
            resp = session.get(
                url,
                headers=headers,
                timeout=12,
                verify=False,
            )

            if resp.status_code != 200:
                log(
                    f"✕ 台號 {m_id} 回傳狀態碼 "
                    f"{resp.status_code}，跳過"
                )
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            title = soup.title.string.strip() if soup.title else ""

            # 驗證頁面
            if "遊技データをご覧のお客様へ" in title:
                log("")
                log("❌ 被驗證頁面攔截！")
                log("請替換最新 Cookie。")
                break

            clean_title = (
                title.split("|")[0].strip()
                if "|" in title
                else title
            )

            items = soup.find_all(
                "div",
                class_=lambda c: c and (
                    "c-data-pachinko__item" in c
                    or "item" in c
                ),
            )

            if not items:
                log(f"台號 {m_id:3d}: 沒找到資料，跳過")
                continue

            # 排除 SLOT
            if clean_title.startswith("S") or "スロット" in clean_title or "パチスロ" in clean_title:
                if not clean_title.startswith("P"):
                    time.sleep(0.3)
                    continue

            full_text = soup.get_text()

            if "スロット" in full_text and "パチンコ" not in full_text:
                time.sleep(0.3)
                continue

            rate_match = re.search(
                r"(\d+(?:\.\d+)?)\s*円",
                full_text,
            )

            rate_str = (
                f"{rate_match.group(1)}円"
                if rate_match
                else "-"
            )

            pachinko_count += 1

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
                text_div = item.find(
                    "div",
                    class_=lambda c: c and "text" in c,
                )

                if not text_div:
                    continue

                label = text_div.get_text(strip=True)

                img_div = item.find(
                    "div",
                    class_=lambda c: c and (
                        "images" in c or "img" in c
                    ),
                )

                val = extract_led_number(
                    img_div if img_div else item
                )

                if label in current_data:
                    # 日期切換
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
                        raw_date = f"第{day_idx + 1}天"
                        real_date = (
                            base_date
                            - timedelta(days=day_idx)
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

            log(
                f"台號 {m_id:3d}: [P] [{rate_str}] "
                f"解析成功 ({clean_title})"
            )

        except Exception as e:
            log(f"✕ 抓取失敗 {m_id}: {e}")

        # 保留原程式的請求間隔
        time.sleep(random.uniform(1.0, 1.8))

    if not results:
        log("=" * 50)
        log("❌ 未取得符合選取日期範圍的數據，請確認 Cookie、URL、日期設定。")
        return pd.DataFrame(), logs, pachinko_count

    df = pd.DataFrame(results)

    if "_date_obj" in df.columns:
        df = df.drop(columns=["_date_obj"])

    base_cols = [
        "台號",
        "玩法費率",
        "機種名稱",
        "西元日期",
    ]

    other_cols = [
        c for c in df.columns
        if c not in base_cols
    ]

    df = df[base_cols + other_cols]

    log("=" * 50)
    log(f"🎉 抓取完成！共取得 {pachinko_count} 台數據")
    log(f"📊 共產生 {len(df)} 筆日期資料")

    return df, logs, pachinko_count


# -----------------------------
# Streamlit UI
# -----------------------------
st.subheader("1️⃣ Cookie")

cookie = st.text_area(
    "請貼上最新 Cookie",
    height=100,
    placeholder="把瀏覽器 / App 抓到的 Cookie 貼在這裡",
)

st.subheader("2️⃣ 店鋪網址")

base_url = st.text_input(
    "請貼上店鋪或該店任意頁面的 URL",
    value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=228",
)

st.subheader("3️⃣ 台號範圍")

col1, col2 = st.columns(2)

with col1:
    start_num = st.number_input(
        "起始台號",
        min_value=1,
        max_value=9999,
        value=1,
        step=1,
    )

with col2:
    end_num = st.number_input(
        "結束台號",
        min_value=1,
        max_value=9999,
        value=100,
        step=1,
    )

st.subheader("4️⃣ 日期範圍")

today = datetime.now().date()

col3, col4 = st.columns(2)

with col3:
    selected_start_date = st.date_input(
        "起始日期",
        value=today,
    )

with col4:
    selected_end_date = st.date_input(
        "結束日期",
        value=today,
    )

st.info(
    "注意：目前程式原本只提供「今日～6日前」的網站資料，"
    "所以日期選擇範圍不要超過可取得的歷史資料。"
)

st.subheader("5️⃣ 開始擷取")

start_button = st.button(
    "🚀 開始擷取數據",
    type="primary",
    use_container_width=True,
)

if start_button:

    if not cookie.strip():
        st.error("❌ 請先貼上 Cookie")
        st.stop()

    if not base_url.strip():
        st.error("❌ 請輸入 URL")
        st.stop()

    if start_num > end_num:
        st.error("❌ 起始台號不能大於結束台號")
        st.stop()

    if selected_start_date > selected_end_date:
        st.error("❌ 起始日期不能大於結束日期")
        st.stop()

    total = int(end_num - start_num + 1)

    st.write(
        f"正在掃描 **{start_num} ~ {end_num}**，"
        f"共 **{total} 台**。"
    )

    progress = st.progress(0)

    status = st.status(
        "🚀 任務執行中...",
        expanded=True,
    )

    log_box = st.empty()

    try:
        # 注意：
        # 這裡沿用原本抓取邏輯。
        # Streamlit 版本不使用 Tkinter / threading。
        df, logs, pachinko_count = run_scraper(
            cookie=cookie.strip(),
            base_url=base_url.strip(),
            start_num=int(start_num),
            end_num=int(end_num),
            selected_start_date=selected_start_date,
            selected_end_date=selected_end_date,
        )

        # 顯示完整 Log
        log_box.text_area(
            "執行進度與日誌",
            "\n".join(logs),
            height=400,
        )

        # 讓進度條在完成時變成 100%
        progress.progress(100)

        if df.empty:
            status.update(
                label="❌ 沒有取得資料",
                state="error",
            )
            st.warning(
                "沒有符合日期範圍的資料。"
                "請確認 Cookie 是否有效，以及 URL / 台號範圍是否正確。"
            )
            st.stop()

        status.update(
            label="✅ 抓取完成",
            state="complete",
        )

        st.success(
            f"🎉 完成！取得 {pachinko_count} 台，"
            f"共 {len(df)} 筆資料。"
        )

        st.subheader("📊 資料預覽")

        st.dataframe(
            df,
            use_container_width=True,
            height=500,
        )

        # Excel 寫入記憶體，不需要在伺服器建立本地檔案
        from io import BytesIO

        output = BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl",
        ) as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="PachinkoData",
            )

        output.seek(0)

        filename = (
            "pachinko_data_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".xlsx"
        )

        st.download_button(
            label="📥 下載 Excel",
            data=output.getvalue(),
            file_name=filename,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    except Exception as e:
        status.update(
            label="❌ 執行發生錯誤",
            state="error",
        )

        st.error(f"錯誤：{e}")

# -----------------------------
# 使用說明
# -----------------------------
with st.expander("📱 iPad 使用方式"):
    st.markdown(
        """
### 方法 A：電腦執行，iPad 操作（推薦）

1. 在 Windows 電腦安裝 Python。
2. 安裝套件：
   `pip install streamlit pandas requests beautifulsoup4 openpyxl urllib3`
3. 將這個檔案命名為 `app.py`
4. 在 CMD 執行：

```bash
streamlit run app.py --server.address 0.0.0.0
```

5. 電腦與 iPad 連到同一個 Wi-Fi。
6. iPad Safari 開：

```text
http://你的電腦IP:8501
```

例如：

```text
http://192.168.1.100:8501
```

### 方法 B：放到雲端

也可以把 Streamlit 程式部署到雲端，iPad 直接開網址。

但你的程式需要 Cookie，而且請求是從雲端伺服器送出，
因此實際使用時我比較建議先用「Windows 電腦 + iPad 同 Wi-Fi」。
"""
    )

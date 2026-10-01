import re
import time
import random
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from curl_cffi import requests

# 頁面基本設定
st.set_page_config(page_title="Pachinko 數據自動擷取工具 v2.0", page_icon="🎰", layout="centered")

st.title("🎰 Pachinko 數據自動擷取工具 v2.0")
st.caption("支援 iPad / 行動裝置 PWA 操作 (Powered by curl_cffi)")

# 1. 參數設定區塊
st.header("⚙️ 參數設定")

cookie_input = st.text_area(
    "請貼上最新 Cookie:",
    height=100,
    placeholder="例：_gcl_au=1.1.xxx; _pubcid=xxx...",
    help="請從瀏覽器的 F12 開發者工具中複製完整的 Cookie 字串（勿包含 'Cookie: ' 前綴）"
)

base_url = st.text_input(
    "請貼上店鋪網址 (或任意該店之頁面 URL):",
    value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=228"
)

col_num1, col_num2 = st.columns(2)
with col_num1:
    start_num = st.number_input("起始台號:", min_value=1, max_value=9999, value=1, step=1)
with col_num2:
    end_num = st.number_input("結束台號:", min_value=1, max_value=9999, value=100, step=1)

col_date1, col_date2 = st.columns(2)
today = datetime.now().date()
with col_date1:
    selected_start_date = st.date_input("起始日期:", value=today)
with col_date2:
    selected_end_date = st.date_input("結束日期:", value=today)

btn_start = st.button("🚀 開始擷取數據", use_container_width=True)

# 2. 輔助解析函式
def clean_cookie(raw_cookie):
    """自動清除可能誤貼的 'Cookie: ' 前綴"""
    if not raw_cookie:
        return ""
    cookie_str = raw_cookie.strip()
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()
    return cookie_str

def extract_led_number(element):
    """解析數字或圖片 LED 數字 (複製自原 EXE 邏輯)"""
    if not element:
        return "-"
    imgs = element.find_all('img')
    if imgs:
        digits = []
        for img in imgs:
            src = img.get('src', '').lower()
            alt = img.get('alt', '')
            if 'blank' in src:
                continue
            if alt == '/' or 'slash' in src:
                digits.append('/')
            elif alt.isdigit():
                digits.append(alt)
            else:
                filename = src.split('/')[-1]
                match = re.search(r'(\d+)(?=\.[a-z]+$)', filename) or re.search(r'(\d+)', filename)
                if match:
                    digits.append(match.group(1))
        if digits:
            return "".join(digits)
    text = element.get_text(strip=True)
    clean = re.sub(r'[^\d/.-]', '', text)
    return clean if clean else "-"

# 3. 執行擷取邏輯
if btn_start:
    cleaned_cookie = clean_cookie(cookie_input)

    if not cleaned_cookie:
        st.error("❌ 請先填寫 Cookie！")
    elif not base_url:
        st.error("❌ 請填寫店鋪或頁面 URL！")
    elif selected_start_date > selected_end_date:
        st.error("❌ 起始日期不可以大於結束日期！")
    elif start_num > end_num:
        st.error("❌ 起始台號不可以大於結束台號！")
    else:
        st.info("⏳ 任務啟動中...")

        # 替換 URL 中的 id 參數基礎格式
        if "id=" in base_url:
            url_template = re.sub(r'id=\d+', 'id={}', base_url)
        else:
            url_template = base_url + "&id={}" if "?" in base_url else base_url + "?id={}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-S938U Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'X-Requested-With': 'com.dmm.ptown',
            'Referer': 'https://sunpo-to.a.p-moba.net/',
            'Cookie': cleaned_cookie
        }

        machine_ids = list(range(int(start_num), int(end_num) + 1))
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
        total_machines = len(machine_ids)

        progress_bar = st.progress(0)
        status_text = st.empty()
        log_expander = st.expander("📄 執行日誌", expanded=True)
        log_box = log_expander.empty()
        log_messages = [f"開始掃描台號範圍：{start_num} ~ {end_num}", f"篩選日期範圍：{selected_start_date} 至 {selected_end_date}"]
        log_box.text("\n".join(log_messages))

        for idx, m_id in enumerate(machine_ids, start=1):
            url = url_template.format(m_id)

            # 更新進度條與狀態
            progress = idx / total_machines
            progress_bar.progress(progress)
            status_text.text(f"正在擷取台號 {m_id} ({idx}/{total_machines})...")

            # 防封鎖休眠
            if idx > 1 and idx % 35 == 0:
                pause_time = random.uniform(8, 15)
                msg = f"☕ 已連續掃描 {idx} 台，自動暫停 {pause_time:.1f} 秒..."
                log_messages.append(msg)
                log_box.text("\n".join(log_messages[-15:]))
                time.sleep(pause_time)

            try:
                # 使用 curl_cffi 模擬 Chrome 發送請求
                resp = requests.get(url, headers=headers, timeout=15, impersonate="chrome120")

                if resp.status_code != 200:
                    log_messages.append(f"  ✕ 台號 {m_id} 回傳狀態碼 {resp.status_code}，跳過")
                    log_box.text("\n".join(log_messages[-15:]))
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                title = soup.title.string.strip() if soup.title else ""

                if "遊技データをご覧のお客様へ" in title:
                    log_messages.append(f"\n  ❌ 台號 {m_id} 被驗證頁面攔截！請替換最新 Cookie。")
                    log_box.text("\n".join(log_messages[-15:]))
                    st.error(f"台號 {m_id} 被驗證頁面攔截！請替換最新 Cookie。")
                    break

                clean_title = title.split('|')[0].strip() if '|' in title else title
                items = soup.find_all('div', class_=lambda c: c and ('c-data-pachinko__item' in c or 'item' in c))

                if not items:
                    continue

                if clean_title.startswith('S') or "スロット" in clean_title or "パチスロ" in clean_title:
                    if not clean_title.startswith('P'):
                        time.sleep(0.3)
                        continue

                full_text = soup.get_text()
                if "スロット" in full_text and "パチンコ" not in full_text:
                    time.sleep(0.3)
                    continue

                rate_match = re.search(r'(\d+(?:\.\d+)?)\s*円', full_text)
                rate_str = f"{rate_match.group(1)}円" if rate_match else "-"

                pachinko_count += 1
                day_idx = 0
                raw_date, real_datetime = date_mapping[day_idx]
                real_date_obj = real_datetime.date()

                current_data = {
                    '台號': m_id,
                    '玩法費率': rate_str,
                    '機種名稱': clean_title,
                    '西元日期': real_date_obj.strftime("%Y-%m-%d"),
                    '_date_obj': real_date_obj
                }

                for item in items:
                    text_div = item.find('div', class_=lambda c: c and 'text' in c)
                    if not text_div:
                        continue

                    label = text_div.get_text(strip=True)
                    img_div = item.find('div', class_=lambda c: c and ('images' in c or 'img' in c))
                    val = extract_led_number(img_div if img_div else item)

                    if label in current_data:
                        # 判斷上一天資料是否在範圍內
                        if selected_start_date <= current_data['_date_obj'] <= selected_end_date:
                            results.append(current_data)

                        day_idx += 1
                        if day_idx < len(date_mapping):
                            raw_date, real_datetime = date_mapping[day_idx]
                            real_date_obj = real_datetime.date()
                        else:
                            real_date_obj = (base_date - timedelta(days=day_idx)).date()

                        current_data = {
                            '台號': m_id,
                            '玩法費率': rate_str,
                            '機種名稱': clean_title,
                            '西元日期': real_date_obj.strftime("%Y-%m-%d"),
                            '_date_obj': real_date_obj
                        }
                    current_data[label] = val

                # 處理最後一天資料
                if current_data and len(current_data) > 5:
                    if selected_start_date <= current_data['_date_obj'] <= selected_end_date:
                        results.append(current_data)

                log_messages.append(f"台號 {m_id:3d}: [P] [{rate_str}] 解析成功 ({clean_title})")
                log_box.text("\n".join(log_messages[-15:]))

            except Exception as e:
                log_messages.append(f"  ✕ 抓取失敗 {m_id}: {e}")
                log_box.text("\n".join(log_messages[-15:]))

            time.sleep(random.uniform(1.0, 1.8))

        # 完成與數據展現
        if results:
            df = pd.DataFrame(results)
            if '_date_obj' in df.columns:
                df = df.drop(columns=['_date_obj'])

            base_cols = ['台號', '玩法費率', '機種名稱', '西元日期']
            other_cols = [c for c in df.columns if c not in base_cols]
            df = df[base_cols + other_cols]

            st.success(f"🎉 抓取完成！共取得 {pachinko_count} 台數據")
            st.dataframe(df)

            # Excel 下載
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)

            excel_filename = f"pachinko_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            st.download_button(
                label="📥 下載 Excel 試算表 (.xlsx)",
                data=buffer,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("❌ 未取得符合選取日期範圍的數據，請確認日期與 Cookie 設定。")

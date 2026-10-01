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
    value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=1"
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

ignore_date_filter = st.checkbox("⚠️ 忽略日期篩選（匯出畫面上擷取到的所有數據）", value=True)

btn_start = st.button("🚀 開始擷取數據", use_container_width=True)

# 2. 輔助解析函式
def clean_cookie(raw_cookie):
    if not raw_cookie:
        return ""
    cookie_str = raw_cookie.strip()
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()
    return cookie_str

def extract_led_number(element):
    """解析 LED 數字 (含圖片與文字)"""
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

        # 確保網址格式正確
        if "id=" in base_url:
            url_template = re.sub(r'id=\d+', 'id={}', base_url)
        else:
            url_template = base_url + "&id={}" if "?" in base_url else base_url + "?id={}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'X-Requested-With': 'com.dmm.ptown',
            'Referer': 'https://sunpo-to.a.p-moba.net/',
            'Cookie': cleaned_cookie
        }

        machine_ids = list(range(int(start_num), int(end_num) + 1))
        results = []
        base_date = datetime.now().date()

        total_machines = len(machine_ids)

        progress_bar = st.progress(0)
        status_text = st.empty()
        log_expander = st.expander("📄 執行日誌", expanded=True)
        log_box = log_expander.empty()
        log_messages = [f"開始掃描台號範圍：{start_num} ~ {end_num}"]
        log_box.text("\n".join(log_messages))

        for idx, m_id in enumerate(machine_ids, start=1):
            url = url_template.format(m_id)

            progress = idx / total_machines
            progress_bar.progress(progress)
            status_text.text(f"正在擷取台號 {m_id} ({idx}/{total_machines})...")

            if idx > 1 and idx % 35 == 0:
                pause_time = random.uniform(8, 15)
                msg = f"☕ 已連續掃描 {idx} 台，自動暫停 {pause_time:.1f} 秒..."
                log_messages.append(msg)
                log_box.text("\n".join(log_messages[-15:]))
                time.sleep(pause_time)

            try:
                resp = requests.get(url, headers=headers, timeout=15, impersonate="chrome120")

                if resp.status_code != 200:
                    log_messages.append(f"  ✕ 台號 {m_id} HTTP 狀態碼：{resp.status_code}")
                    log_box.text("\n".join(log_messages[-15:]))
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                full_text = soup.get_text()

                if "遊技データをご覧のお客様へ" in full_text:
                    log_messages.append(f"\n  ❌ 台號 {m_id} 被驗證頁面攔截！請更新 Cookie。")
                    log_box.text("\n".join(log_messages[-15:]))
                    st.error(f"台號 {m_id} 被驗證頁面攔截！請替換最新 Cookie。")
                    break

                # 解析機種名稱
                title_tag = soup.find('div', class_=lambda c: c and 'machine-name' in str(c)) or soup.title
                clean_title = title_tag.get_text(strip=True) if title_tag else "未知機種"
                clean_title = clean_title.split('|')[0].strip()

                # 解析費率 (例如 0.562円パチンコ 或 4円)
                rate_match = re.search(r'(\d+(?:\.\d+)?)\s*円', full_text)
                rate_str = f"{rate_match.group(1)}円" if rate_match else "-"

                # 針對 P-Moba「左右雙欄 (今日/昨日)」結構做區域拆分
                # 尋找所有包含數據區塊的包裹容器
                columns = soup.find_all('div', class_=lambda c: c and any(k in str(c) for k in ['data-block', 'day-data', 'data_box', 'flex-1', 'col']))
                
                if not columns or len(columns) < 2:
                    # 備用：若無特定 col 包裹，直接搜尋大當區塊
                    columns = soup.find_all('div', class_=lambda c: c and 'item' in str(c))

                # 建立兩天數據容器：[今日(0天前), 昨日(1天前)]
                day_data_list = [
                    {'台號': m_id, '玩法費率': rate_str, '機種名稱': clean_title, '西元日期': (base_date).strftime("%Y-%m-%d"), '_date': base_date},
                    {'台號': m_id, '玩法費率': rate_str, '機種名稱': clean_title, '西元日期': (base_date - timedelta(days=1)).strftime("%Y-%m-%d"), '_date': base_date - timedelta(days=1)}
                ]

                # 抓取頁面上所有 item 項目
                items = soup.find_all('div', class_=lambda c: c and 'item' in str(c))

                items_extracted = 0
                for item in items:
                    text_div = item.find('div', class_=lambda c: c and ('text' in str(c) or 'label' in str(c)))
                    if not text_div:
                        continue
                    label = text_div.get_text(strip=True)

                    img_div = item.find('div', class_=lambda c: c and ('images' in str(c) or 'img' in str(c)))
                    val = extract_led_number(img_div if img_div else item)

                    if not label or val == "-":
                        continue

                    # 如果「今日」還沒填過這個標籤，填入今日；若填過了，填入「昨日」
                    if label not in day_data_list[0]:
                        day_data_list[0][label] = val
                        items_extracted += 1
                    elif label not in day_data_list[1]:
                        day_data_list[1][label] = val
                        items_extracted += 1

                # 驗證並儲存符合條件的資料
                for d in day_data_list:
                    if len(d) > 5: # 確定有抓到 LED 數值欄位
                        if ignore_date_filter or (selected_start_date <= d['_date'] <= selected_end_date):
                            results.append(d)

                log_messages.append(f"台號 {m_id:3d}: [P] [{rate_str}] 解析成功！(擷取到 {items_extracted} 個數據項目)")
                log_box.text("\n".join(log_messages[-15:]))

            except Exception as e:
                log_messages.append(f"  ✕ 抓取失敗 {m_id}: {e}")
                log_box.text("\n".join(log_messages[-15:]))

            time.sleep(random.uniform(1.0, 1.8))

        # 完成與數據展現
        if results:
            df = pd.DataFrame(results)
            if '_date' in df.columns:
                df = df.drop(columns=['_date'])

            base_cols = ['台號', '玩法費率', '機種名稱', '西元日期']
            existing_base = [c for c in base_cols if c in df.columns]
            other_cols = [c for c in df.columns if c not in existing_base]
            df = df[existing_base + other_cols]

            st.success(f"🎉 抓取完成！共取得 {len(results)} 筆歷史數據")
            st.dataframe(df)

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
            st.error("❌ 依然未取得數據，請確認 Cookie 是否過期。")

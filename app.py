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
import io

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------------------------------------------------------
# 頁面基本配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Pachinko 數據自動擷取工具 (Streamlit版)",
    page_icon="🎰",
    layout="wide"
)

st.title("🎰 Pachinko 數據自動擷取工具 v2.1 (Cloud 最佳化版)")
st.caption("支援在 Streamlit Cloud 執行；若遭 403 阻擋，可於側邊欄輸入 Proxy/代理 IP。")

# -----------------------------------------------------------------------------
# 側邊欄：代理伺服器 (Proxy) 與進階設定
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 網路與代理設定 (防 403 關鍵)")
proxy_url = st.sidebar.text_input(
    "Proxy 網址 (必填/選填)", 
    value="",
    placeholder="http://username:password@proxy_ip:port",
    help="由於 Streamlit Cloud 使用 AWS 機房 IP，直連 DMM 常會遇到 403。請在此貼上代理伺服器網址 (如 Tinyproxy: http://IP:3128)。"
)

# 預設使用真實 Android WebView UA，並確保無前綴
default_ua = "Mozilla/5.0 (Linux; Android 12; SM-S938U Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36"
custom_user_agent = st.sidebar.text_input(
    "User-Agent",
    value=default_ua
)

# -----------------------------------------------------------------------------
# 核心邏輯函式
# -----------------------------------------------------------------------------
def extract_led_number(element):
    """解析數字或圖片 LED 數字"""
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

def run_scraping(cookie, base_url, start_num, end_num, selected_start_date, selected_end_date, proxy_str, user_agent_str, status_container, log_container):
    """執行爬蟲核心任務"""
    
    # 清洗 User-Agent 防止包含 "User-Agent:" 前綴
    clean_ua = re.sub(r'^user-agent:\s*', '', user_agent_str.strip(), flags=re.IGNORECASE)

    # 替換 URL 中的 id 參數基礎格式
    if "id=" in base_url:
        url_template = re.sub(r'id=\d+', 'id={}', base_url)
    else:
        url_template = base_url + "&id={}" if "?" in base_url else base_url + "?id={}"

    # 建立 Requests Session
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    # 如果有設定 Proxy，則加入 Session
    if proxy_str.strip():
        proxies_config = {
            "http": proxy_str.strip(),
            "https": proxy_str.strip()
        }
        session.proxies.update(proxies_config)
        log_container.info(f"🌐 已啟用 Proxy 代理：{proxy_str.split('@')[-1] if '@' in proxy_str else proxy_str}")

    # 完整的擬真 Headers（補齊防爬關鍵 Header）
    headers = {
        'Host': 'sunpo-to.a.p-moba.net',
        'User-Agent': clean_ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'X-Requested-With': 'com.dmm.ptown',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Dest': 'document',
        'Referer': 'https://sunpo-to.a.p-moba.net/',
        'Cookie': cookie.strip()
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
    total_machines = len(machine_ids)

    log_messages = []
    def append_log(msg):
        log_messages.append(msg)
        log_container.code("\n".join(log_messages[-15:])) # 畫面上即時顯示最新 15 條日誌

    append_log(f"開始掃描台號範圍：{start_num} ~ {end_num}")
    append_log(f"篩選日期範圍：{selected_start_date} 至 {selected_end_date}")

    progress_bar = st.progress(0)

    for idx, m_id in enumerate(machine_ids, start=1):
        url = url_template.format(m_id)
        progress_bar.progress(idx / total_machines, text=f"進度：{idx}/{total_machines} (台號 {m_id})")
        
        # 防封鎖休眠（隨機化）
        if idx > 1 and idx % 25 == 0:
            pause_time = random.uniform(10, 18)
            append_log(f"☕ 已連續掃描 {idx} 台，自動暫停 {pause_time:.1f} 秒...")
            time.sleep(pause_time)

        try:
            resp = session.get(url, headers=headers, timeout=15, verify=False)
            
            if resp.status_code != 200:
                append_log(f"✕ 台號 {m_id} 回傳狀態碼 {resp.status_code} (可能遭阻擋/驗證)")
                if resp.status_code == 403:
                    st.error(f"台號 {m_id} 遭遇 403 被拒絕存取，請檢查 Cookie 或 Proxy 設定。")
                    break
                continue
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else ""
            
            if "遊技データをご覧のお客様へ" in title or "安全な接続" in resp.text:
                append_log(f"❌ 台號 {m_id} 被驗證頁面攔截！請替換最新 Cookie 或檢視 Proxy。")
                st.error("驗證頁面攔截！任務提前終止，請更換 Cookie。")
                break

            clean_title = title.split('|')[0].strip() if '|' in title else title
            items = soup.find_all('div', class_=lambda c: c and ('c-data-pachinko__item' in c or 'item' in c))

            if not items:
                append_log(f"⚠️ 台號 {m_id}: 無數據或機台未開機/不存在")
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
            raw_date, real_date = date_mapping[day_idx]

            current_data = {
                '台號': m_id,
                '玩法費率': rate_str,
                '機種名稱': clean_title,
                '西元日期': real_date.strftime("%Y-%m-%d"),
                '_date_obj': real_date.date()
            }

            for item in items:
                text_div = item.find('div', class_=lambda c: c and 'text' in c)
                if not text_div:
                    continue
                
                label = text_div.get_text(strip=True)
                img_div = item.find('div', class_=lambda c: c and ('images' in c or 'img' in c))
                val = extract_led_number(img_div if img_div else item)
                
                if label in current_data:
                    if selected_start_date <= current_data['_date_obj'] <= selected_end_date:
                        results.append(current_data)
                    
                    day_idx += 1
                    if day_idx < len(date_mapping):
                        raw_date, real_date = date_mapping[day_idx]
                    else:
                        raw_date, real_date = f"第{day_idx+1}天", base_date - timedelta(days=day_idx)
                        
                    current_data = {
                        '台號': m_id,
                        '玩法費率': rate_str,
                        '機種名稱': clean_title,
                        '西元日期': real_date.strftime("%Y-%m-%d"),
                        '_date_obj': real_date.date()
                    }
                current_data[label] = val

            if current_data and len(current_data) > 5:
                if selected_start_date <= current_data['_date_obj'] <= selected_end_date:
                    results.append(current_data)

            append_log(f"台號 {m_id:3d}: [P] [{rate_str}] 解析成功 ({clean_title})")

        except Exception as e:
            append_log(f"✕ 抓取失敗 {m_id}: {e}")
            
        # 安全請求間隔 (1.5 ~ 3.0 秒)
        time.sleep(random.uniform(1.5, 3.0))

    return results, pachinko_count

# -----------------------------------------------------------------------------
# 主介面 UI 配置
# -----------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    cookie = st.text_area("1. 請貼上最新 Cookie:", height=100)
    base_url = st.text_input(
        "2. 請貼上店鋪網址 (或任意該店之頁面 URL):",
        value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=228"
    )

with col2:
    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        start_num = st.number_input("起始台號", min_value=1, max_value=9999, value=1)
        start_date = st.date_input("起始日期", value=datetime.now())
    with sub_col2:
        end_num = st.number_input("結束台號", min_value=1, max_value=9999, value=100)
        end_date = st.date_input("結束日期", value=datetime.now())

st.divider()

# 執行區域
btn_start = st.button("🚀 開始擷取數據", use_container_width=True, type="primary")

status_container = st.container()
log_container = st.empty()

if btn_start:
    if not cookie.strip():
        st.warning("⚠️ 請先填寫 Cookie！")
    elif not base_url.strip():
        st.warning("⚠️ 請填寫店鋪網址！")
    elif start_date > end_date:
        st.error("❌ 起始日期不可以大於結束日期！")
    elif start_num > end_num:
        st.error("❌ 起始台號不可以大於結束台號！")
    else:
        st.info("任務執行中，請勿關閉網頁...")
        results, count = run_scraping(
            cookie.strip(),
            base_url.strip(),
            int(start_num),
            int(end_num),
            start_date,
            end_date,
            proxy_url,
            custom_user_agent,
            status_container,
            log_container
        )

        if results:
            df = pd.DataFrame(results)
            if '_date_obj' in df.columns:
                df = df.drop(columns=['_date_obj'])

            base_cols = ['台號', '玩法費率', '機種名稱', '西元日期']
            other_cols = [c for c in df.columns if c not in base_cols]
            df = df[base_cols + other_cols]

            st.success(f"🎉 抓取完成！共取得 {count} 台數據，共 {len(df)} 筆紀錄。")
            st.dataframe(df, use_container_width=True)

            # 下載 Excel 按鈕
            excel_filename = f"pachinko_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)

            st.download_button(
                label="📥 下載 Excel 檔案",
                data=buffer,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("❌ 未取得符合條件的數據。若回傳狀態皆為 403，代表目前 IP 已遭 DMM 封鎖，請於左側設定 Proxy。")

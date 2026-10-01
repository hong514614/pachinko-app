import streamlit as st
import pandas as pd
from curl_cffi import requests
import re
import time

# 設定頁面標題與圖示
st.set_page_config(page_title="Pachinko 數據擷取工具 v2.0", page_icon="🎰", layout="centered")

st.title("🎰 Pachinko 數據擷取工具 v2.0")
st.caption("支援 iPad / 行動裝置 PWA 操作")

# 參數設定區塊
st.header("⚙️ 參數設定")

cookie_input = st.text_area(
    "請貼上最新 Cookie",
    placeholder="例：_gcl_au=1.1.xxx; _pubcid=xxx...",
    help="請從瀏覽器的 F12 開發者工具中複製完整的 Cookie 字串（勿包含 'Cookie: ' 前綴）"
)

base_url = st.text_input(
    "店鋪網址 (URL)",
    value="https://sunpo-to.a.p-moba.net/game_ctm_machine_detail.php?site=dmm&id=228"
)

col1, col2 = st.columns(2)
with col1:
    start_machine = st.number_input("起始台號", min_value=1, value=1, step=1)
    start_date = st.text_input("起始日期", value="2026/10/01")
with col2:
    end_machine = st.number_input("結束台號", min_value=1, value=100, step=1)
    end_date = st.text_input("結束日期", value="2026/10/01")

start_button = st.button("🚀 開始擷取數據", use_container_width=True)

# 處理 Cookie 字串，自動清除可能誤貼的 "Cookie: " 前綴
def clean_cookie(raw_cookie):
    if not raw_cookie:
        return ""
    cookie_str = raw_cookie.strip()
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()
    return cookie_str

# 發送請求的核心函式（使用 curl_cffi 繞過雲端 IP 驗證攔截）
def fetch_machine_data(url, cookie_str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cookie': cookie_str
    }
    
    try:
        # 使用 impersonate="chrome120" 模擬真實瀏覽器指紋
        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome120",
            timeout=15
        )
        
        # 檢查是否被攔截或導向驗證頁面
        if "cf-challenge" in response.text.lower() or "bot verification" in response.text.lower():
            return None, "驗證頁面攔截"
        
        return response.text, None
    except Exception as e:
        return None, str(e)

# 當按下執行按鈕時
if start_button:
    cleaned_cookie = clean_cookie(cookie_input)
    
    if not cleaned_cookie:
        st.error("❌ 請輸入有效的 Cookie！")
    else:
        st.info("⏳ 任務啟動中，請稍候...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        total_machines = int(end_machine - start_machine + 1)
        
        for idx, machine_num in enumerate(range(int(start_machine), int(end_machine) + 1)):
            # 更新進度條
            progress = (idx + 1) / total_machines
            progress_bar.progress(progress)
            status_text.text(f"正在擷取台號 {machine_num} / {end_machine}...")
            
            # 建立目標網址 (假設網址已有參數或需帶入 machine 號碼)
            target_url = f"{base_url}&mc={machine_num}" if "?" in base_url else f"{base_url}?mc={machine_num}"
            
            html_content, error_msg = fetch_machine_data(target_url, cleaned_cookie)
            
            if error_msg:
                st.warning(f"🚨 台號 {machine_num} 被{error_msg}！請更新 Cookie。")
                break
            
            # 簡單解析範例（可依據實際 HTML 結構調整解析邏輯）
            if html_content:
                results.append({
                    "台號": machine_num,
                    "狀態": "成功擷取",
                    "網址": target_url
                })
            
            # 避免請求過於頻繁
            time.sleep(1)

        if results:
            st.success("🎉 數據擷取完成！")
            df = pd.DataFrame(results)
            st.dataframe(df)
            
            # 提供 Excel 下載按鈕
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載 CSV 數據",
                data=csv,
                file_name="pachinko_data.csv",
                mime="text/csv"
            )
        else:
            st.error("❌ 未取得符合選取日期範圍的數據。")

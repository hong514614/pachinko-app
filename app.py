import io
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup

# 關閉 SSL 驗證警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定 Streamlit 頁面標題與佈局
st.set_page_config(page_title="Pachinko 數據自動擷取工具", page_icon="🎰", layout="centered")


def sanitize_filename(filename):
    """清除作業系統不允許在檔名中使用的字元"""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()


def extract_shop_name(title_text):
    """從標題中解析店名"""
    if not title_text:
        return ""

    if "：" in title_text or ":" in title_text:
        after_colon = re.split(r"[：:]", title_text)[-1]
        shop = re.split(r"[｜|]", after_colon)[0].strip()
        if shop:
            return sanitize_filename(shop)

    if "｜" in title_text or "|" in title_text:
        parts = re.split(r"[｜|]", title_text)
        for part in reversed(parts):
            p = part.strip()
            if p and "設置台" not in p and "詳細" not in p:
                return sanitize_filename(p)

    return ""


def build_machine_url(base_url, target_machine_id):
    """自動解析並替換/插入 id 參數 (台號)"""
    parsed = urlparse(base_url)
    path = parsed.path
    if "game_machine_list.php" in path:
        path = path.replace("game_machine_list.php", "game_machine_detail.php")
    elif not path.endswith("game_machine_detail.php"):
        if path.endswith("/"):
            path += "game_machine_detail.php"
        else:
            path = path.rsplit("/", 1)[0] + "/game_machine_detail.php"

    query_params = parse_qs(parsed.query)
    query_params["id"] = [str(target_machine_id)]

    new_query = urlencode(query_params, doseq=True)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def run_crawler(
    raw_cookie,
    base_url,
    start_date,
    end_date,
    start_machine,
    end_machine,
    status_container,
    log_area,
):
    """執行爬蟲的主邏輯"""
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; SM-S938U Build/V417IR; wv)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0"
                " Chrome/110.0.5481.154 Mobile Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "X-Requested-With": "com.dmm.ptown",
            "Referer": base_url,
            "Cookie": raw_cookie,
        }
    )

    today_date = date.today()
    machine_ids = list(range(start_machine, end_machine + 1))
    all_results = []
    shop_name = ""

    current_dt = start_date
    date_list = []
    while current_dt <= end_date:
        date_list.append(current_dt)
        current_dt += timedelta(days=1)

    log_messages = []

    def write_log(msg):
        log_messages.append(msg)
        log_area.text_area(
            "執行進度與日誌",
            value="\n".join(log_messages),
            height=300,
            key=f"log_{len(log_messages)}",
        )

    write_log(
        f"🚀 開始執行爬蟲：台號 [{start_machine} ~ {end_machine}]，共"
        f" {len(machine_ids)} 台；日期區間共 {len(date_list)} 天..."
    )

    cookie_expired = False

    for target_date in date_list:
        delta_days = (today_date - target_date).days
        date_str = target_date.strftime("%Y-%m-%d")

        if delta_days < 0:
            write_log(f"⚠️ 跳過未來的日期: {date_str}")
            continue

        write_log(f"\n==========================================")
        write_log(f"📅 開始擷取日期：{date_str} (相差 {delta_days} 天)")
        write_log(f"==========================================")

        for m_id in machine_ids:
            status_container.update(
                label=f"正在擷取 {date_str} - 台號 {m_id}...", state="running"
            )
            url = build_machine_url(base_url, m_id)
            try:
                resp = session.get(url, timeout=10, verify=False)
                soup = BeautifulSoup(resp.text, "html.parser")

                title = soup.title.string.strip() if soup.title else ""
                if "遊技データをご覧のお客様へ" in title:
                    write_log(
                        f"✕ 台號 {m_id} 被攔截（Cookie 已過期，請更換"
                        " Cookie）"
                    )
                    cookie_expired = True
                    break

                if not shop_name:
                    shop_name = extract_shop_name(title)
                    if not shop_name:
                        shop_tag = soup.find(
                            "span", class_=lambda c: c and "shop" in c.lower()
                        ) or soup.find("h1")
                        if shop_tag and shop_tag.get_text(strip=True):
                            shop_name = sanitize_filename(
                                shop_tag.get_text(strip=True)
                            )
                    if not shop_name:
                        shop_name = "Pachinko"
                    else:
                        write_log(f"🏪 成功辨識店名：[{shop_name}]")

                full_text = soup.get_text()

                clean_title = (
                    re.split(r"[：:]", title)[0].strip()
                    if ("：" in title or ":" in title)
                    else title
                )
                clean_title = re.split(r"[｜|]", clean_title)[0].strip()

                is_pachinko = False
                is_slot = False
                rate_tag = soup.find(
                    class_=lambda c: c
                    and any(k in c for k in ["rate", "tag", "type", "machine"])
                )
                rate_text = rate_tag.get_text() if rate_tag else ""

                if (
                    "スロット" in rate_text
                    or "スロット" in full_text
                    or "パチスロ" in full_text
                    or "枚" in full_text
                ):
                    is_slot = True
                elif (
                    "パチンコ" in rate_text
                    or "パチンコ" in full_text
                    or "円パチンコ" in full_text
                ):
                    is_pachinko = True

                if not is_pachinko and not is_slot:
                    if clean_title.startswith("P") or "P" in rate_text:
                        is_pachinko = True
                    elif clean_title.startswith("S") or "S" in rate_text:
                        is_slot = True

                if is_slot or not is_pachinko:
                    time.sleep(0.05)
                    continue

                rate_match = re.search(r"(\d+(?:\.\d+)?)\s*円", full_text)
                rate_str = f"{rate_match.group(1)}円" if rate_match else "-"

                items = soup.find_all(
                    "div", class_=lambda c: c and "c-data-pachinko__item" in c
                )
                if not items:
                    continue

                current_day_idx = 0
                current_data = {
                    "台號": m_id,
                    "玩法費率": rate_str,
                    "機種名稱": clean_title,
                    "目標日期": date_str,
                }
                seen_labels = set()

                for item in items:
                    text_div = item.find(
                        "div", class_="c-data-pachinko__item-text"
                    )
                    if not text_div:
                        continue

                    label = text_div.get_text(strip=True)
                    img_div = item.find(
                        "div", class_="c-data-pachinko__item-images"
                    )

                    val = "-"
                    if img_div or item:
                        target_elem = img_div if img_div else item
                        imgs = target_elem.find_all("img")
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
                                    fn = src.split("/")[-1]
                                    m = re.search(
                                        r"(\d+)(?=\.[a-z]+$)", fn
                                    ) or re.search(r"(\d+)", fn)
                                    if m:
                                        digits.append(m.group(1))
                            if digits:
                                val = "".join(digits)
                        if val == "-":
                            txt = target_elem.get_text(strip=True)
                            cln = re.sub(r"[^\d/.-]", "", txt)
                            if cln:
                                val = cln

                    if label in seen_labels:
                        current_day_idx += 1
                        seen_labels.clear()
                        if current_day_idx > delta_days:
                            break
                    seen_labels.add(label)

                    if current_day_idx == delta_days:
                        current_data[label] = val

                if len(current_data) > 4:
                    all_results.append(current_data)
                    write_log(
                        f"[{date_str}] 台號 {m_id:3d}:"
                        f" 解析成功！({clean_title})"
                    )

            except Exception as e:
                write_log(f"✕ 台號 {m_id} 失敗: {e}")

            time.sleep(random.uniform(0.3, 0.6))

        if cookie_expired:
            break

    if all_results:
        df = pd.DataFrame(all_results)
        base_cols = ["台號", "玩法費率", "機種名稱", "目標日期"]
        other_cols = [c for c in df.columns if c not in base_cols]
        df = df[base_cols + other_cols]
        df = df.sort_values(by=["目標日期", "台號"])

        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")
        date_part = (
            start_date_str
            if start_date_str == end_date_str
            else f"{start_date_str}-{end_date_str}"
        )
        machine_part = f"{start_machine}號-{end_machine}號"
        file_name = f"{shop_name}_{date_part}_{machine_part}.xlsx"

        # 使用 io.BytesIO 在記憶體中生成 Excel，供 Streamlit 下載
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        output.seek(0)

        write_log(f"\n✅ 全部數據已擷取完畢！準備下載：{file_name}")
        status_container.update(
            label="🎉 任務完成！請點擊下方按鈕下載檔案。",
            state="complete",
        )
        return output, file_name, df
    else:
        status_container.update(
            label="⚠️ 未能擷取到數據，請確認 Cookie 與 URL 是否有效。",
            state="error",
        )
        return None, None, None


# ===== GUI 主介面 =====
st.title("🎰 Pachinko 數據擷取工具")

with st.form("crawler_form"):
    cookie_input = st.text_input(
        "最新 Cookie:",
        placeholder="PHPSESSID=...; sunpo-to_acc=...",
        help="貼上抓包獲取的完整 Cookie",
    )
    url_input = st.text_input(
        "店鋪網址 (或任意頁面 URL):",
        value=(
            "https://ruxornagoespace.a.p-moba.net/game_machine_list.php?site=dmm&id=P20007800&kid=1"
        ),
    )

    col1, col2 = st.columns(2)
    with col1:
        start_machine = st.number_input(
            "起始台號", min_value=1, max_value=9999, value=1
        )
        start_date = st.date_input("起始日期", value=date.today())
    with col2:
        end_machine = st.number_input(
            "結束台號", min_value=1, max_value=9999, value=558
        )
        end_date = st.date_input("結束日期", value=date.today())

    submit_button = st.form_submit_button("🚀 開始擷取數據")

log_area = st.empty()

if submit_button:
    if not cookie_input.strip():
        st.error("請先輸入 Cookie！")
    elif not url_input.strip() or not url_input.startswith("http"):
        st.error("請輸入有效的店鋪 URL (須包含 http:// 或 https://)！")
    elif start_machine > end_machine:
        st.error("起始台號不能大於結束台號！")
    elif start_date > end_date:
        st.error("起始日期不能大於結束日期！")
    else:
        status_container = st.status("正在初始化爬蟲...", expanded=True)
        excel_data, filename, result_df = run_crawler(
            cookie_input.strip(),
            url_input.strip(),
            start_date,
            end_date,
            int(start_machine),
            int(end_machine),
            status_container,
            log_area,
        )

        if excel_data:
            st.download_button(
                label="📥 下載 Excel 試算表",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.subheader("數據預覽")
            st.dataframe(result_df.head(20))

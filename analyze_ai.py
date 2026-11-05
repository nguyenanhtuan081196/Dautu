import os
import time
import requests
import re
import json
import argparse

SCREENER_FILE = "screener_results.json"
DATA_FILE = "data.json"

ALIBABA_API_KEY = os.getenv("ALIBABA_API_KEY", "").strip()
INPUT_SYMBOLS = os.getenv("INPUT_SYMBOLS", "").strip()
API_URL = "https://ws-8lcqaxwxdv0h9xzy.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"

RESUME_DAYS = 7

SECTOR_MAPPING = {
    "NGAN_HANG": [
        "ACB", "BID", "CTG", "TCB", "MBB", "STB", "VPB", "HDB", "VIB", "TPB",
        "SHB", "SSB", "LPB", "MSB", "OCB", "EIB", "VCB"
    ],
    "CHUNG_KHOAN": [
        "SSI", "VCI", "HCM", "VIX", "MBS", "FTS", "BSI", "CTS", "ORS"
    ],
    "BAT_DONG_SAN": [
        "VHM", "VIC", "VRE", "NVL", "PDR", "DIG", "NLG", "KDH", "CEO", "DXG",
        "TCH", "HDG", "KBC", "IDC", "SZC", "BCM", "PHR", "SJS", "VPI"
    ],
    "CONG_NGHE_BAN_LE": [
        "FPT", "MWG", "PNJ", "FRT", "DGW"
    ],
    "DIEN_NUOC_HA_TANG": [
        "POW", "REE", "PC1", "NT2", "GAS", "GEG", "BWE", "TDM"
    ],
    "NGUYEN_VAT_LIEU_CHU_KY": [
        "HPG", "HSG", "NKG", "DGC", "DCM", "DPM", "GVR", "PHR", "DHC"
    ],
    "SAN_XUAT_TIEU_DUNG_PHONG_THU": [
        "VNM", "MSN", "SAB", "VHC", "ANV", "BVH", "PLX", "PVD", "PVS", "BSR",
        "GMD", "HAH", "PVT", "VJC", "HVN", "APH", "ASM", "DBC", "KDC", "MSH",
        "PAN", "SBT", "DRC", "CSM", "BMP", "DHG", "CTD", "VCG", "HHV", "GEX"
    ]
}

TOP_PER_SECTOR = 5  # số mã top đầu mỗi ngành (giống logic cũ)


def get_sector(symbol):
    for sector, symbols in SECTOR_MAPPING.items():
        if symbol in symbols:
            return sector
    return "SAN_XUAT_TIEU_DUNG_PHONG_THU"


def is_recently_analyzed(stock_metrics, days=RESUME_DAYS):
    ts_str = stock_metrics.get("ai_updated_at", "")
    if not ts_str:
        return False
    try:
        ts = time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return False
    return (time.time() - ts) < days * 24 * 3600


def analyze_stock_with_ai(symbol, stock_metrics, screener_item, sector):
    if not ALIBABA_API_KEY:
        print(f"❌ LỖI: Biến môi trường ALIBABA_API_KEY đang trống!")
        return None

    close_price = stock_metrics.get('close', stock_metrics.get('close_price', 0))
    pe = stock_metrics.get('pe', 0)
    pb = stock_metrics.get('pb', 0)
    roe = stock_metrics.get('roe', 0)
    eps = stock_metrics.get('eps', 0)
    dividend_yield = stock_metrics.get('dividend_yield', 0)
    roa = stock_metrics.get('roa', 0)
    cfo_latest = stock_metrics.get('cfo_latest', 0)
    debt_to_equity = stock_metrics.get('debt_to_equity', 0)
    gross_margin = stock_metrics.get('gross_margin', 0)
    net_profit_ttm = stock_metrics.get('net_profit_ttm', 0)
    growth_yoy = screener_item.get('profit_growth_yoy', 0)
    total_score = screener_item.get('total_score', 0)
    fund_notes = screener_item.get('fundamental_notes', '')

    sector_guidance = ""
    if sector == "NGAN_HANG":
        sector_guidance = (
            "ĐẶC THÙ NGÂN HÀNG: Cần đánh giá linh hoạt. "
            "1. KHÔNG đánh giá D/E cao là xấu, vì nợ phải trả chủ yếu là tiền gửi huy động khách hàng. "
            "2. Dòng tiền kinh doanh (CFO) âm trong các kỳ mở rộng tín dụng là bản chất bình thường của ngân hàng. "
            "3. Tập trung vào tăng trưởng tín dụng, NIM, chất lượng tài sản (nợ xấu/LLR) và ROE/ROA."
        )
    elif sector == "CHUNG_KHOAN":
        sector_guidance = (
            "ĐẶC THÙ CHỨNG KHOÁN: Cần đánh giá linh hoạt. "
            "1. Nhạy bén theo chu kỳ thanh khoản thị trường và danh mục tự doanh. "
            "2. Đòn bẩy tài chính và dòng tiền hoạt động phụ thuộc vào quy mô cho vay margin. "
            "3. Trọng tâm đánh giá ROE, thị phần môi giới và năng lực quản trị rủi ro."
        )
    elif sector == "BAT_DONG_SAN":
        sector_guidance = (
            "ĐẶC THÙ BẤT ĐỘNG SẢN: "
            "Thẩm định quỹ đất sạch, pháp lý dự án, người mua trả tiền trước, cơ cấu nợ vay và tiến độ ghi nhận doanh thu từ các dự án gối đầu."
        )
    elif sector == "CONG_NGHE_BAN_LE":
        sector_guidance = (
            "ĐẶC THÙ CÔNG NGHỆ & BÁN LẺ: "
            "Trọng tâm tốc độ tăng trưởng doanh thu cốt lõi, biên lợi nhuận gộp, vòng quay tài sản và năng lực tối ưu hóa chi phí vận hành chuỗi."
        )
    elif sector == "DIEN_NUOC_HA_TANG":
        sector_guidance = (
            "ĐẶC THÙ TIỆN ÍCH / HẠ TẦNG: "
            "Dòng tiền phòng thủ ổn định, khấu hao tài sản cố định lớn làm giảm lợi nhuận kế toán ngắn hạn nhưng dòng tiền thực tế thường rất đều đặn để chi trả cổ tức."
        )
    elif sector == "NGUYEN_VAT_LIEU_CHU_KY":
        sector_guidance = (
            "ĐẶC THÙ VẬT LIỆU CHU KỲ (Thép, Hóa chất...): "
            "Đánh giá qua lăng kính chu kỳ giá hàng hóa (commodity cycle), biên lợi nhuận gộp theo từng quý và định giá P/B tại vùng đỉnh/đáy chu kỳ."
        )
    else:
        sector_guidance = (
            "ĐẶC THÙ SẢN XUẤT & TIÊU DÙNG: "
            "Đánh giá sức mạnh thương hiệu (Economic Moat), thị phần, hiệu quả chuỗi cung ứng (ROA) và sự khỏe mạnh của dòng tiền kinh doanh (CFO) so với lợi nhuận."
        )

    prompt = f"""
    Bạn là một Chuyên gia Đầu tư Giá trị & Tăng trưởng kỳ cựu theo trường phái Graham, Buffett & Fisher.
    Hãy thực hiện một bản **đánh giá tích sản dài hạn chuyên sâu, khắt khe và linh hoạt theo đúng đặc thù ngành** cho mã cổ phiếu: {symbol} thuộc nhóm ngành: {sector}.

    --- HƯỚNG DẪN ĐÁNH GIÁ THEO ĐẶC THÙ NGÀNH ---
    {sector_guidance}

    --- DỮ LIỆU TÀI CHÍNH & ĐỊNH LƯỢNG ---
    - Mã CK: {symbol} | Điểm chất lượng tổng hợp: {total_score}/100 ({fund_notes})
    - Giá thị trường: {close_price:,.0f} VNĐ
    - Định giá: P/E = {pe} | P/B = {pb}
    - Hiệu quả sinh lời: ROE = {roe}% | ROA = {roa}% | EPS = {eps:,.0f} VNĐ | Cổ tức = {dividend_yield}%/năm
    - Sức khỏe tài chính & Dòng tiền: Lợi nhuận trượt 4 quý (TTM) = {net_profit_ttm:,.0f} Tỷ | Dòng tiền kinh doanh (CFO) = {cfo_latest:,.0f} Tỷ | Tỷ lệ Nợ/VCSH (D/E) = {debt_to_equity} | Biên lợi nhuận gộp = {gross_margin}%
    - Tăng trưởng gần nhất: Tăng trưởng LNST YoY = {growth_yoy}%
    --------------------------------------------------------------------------------------------------------------------------------

    YÊU CẦU TRẢ VỀ JSON THUẦN TÚY (TUYỆT ĐỐI KHÔNG DÙNG ```json):
    1. "bctc": [MỤC TRỌNG TÂM - PHÂN TÍCH SỨC KHỎE TÀI CHÍNH]: Phân tích chuyên sâu bức tranh BCTC dựa trên dữ liệu thực tế. **LƯU Ý QUAN TRỌNG:** Phải áp dụng góc nhìn đánh giá linh hoạt theo đặc thù ngành đã nêu ở trên. Phân tích rõ hiệu suất sinh lời (ROE, ROA), biên gộp (nếu áp dụng được) và chất lượng dòng tiền (8-10 câu).
    2. "catalyst": Xác định lợi thế cạnh tranh dài hạn (Economic Moat) và động lực tăng trưởng nội tại trong 2-3 năm tới (4-5 câu).
    3. "risks": Chỉ trích thẳng thắn các rủi ro trọng yếu thực tế phù hợp với ngành (3-4 câu).
    4. "outlook": Đánh giá biên an toàn (Margin of Safety) của mức định giá hiện tại (P/E {pe}, P/B {pb}) kết hợp triển vọng dài hạn (4-5 câu).
    5. "recommendation": Khuyến nghị hành động tích sản sắc bén kèm tỷ trọng giải ngân (Ví dụ: "Tích sản dài hạn - Tỷ trọng 15-20%").
    6. "price_zone": Vạch rõ chiến lược tích sản dạng văn bản liền mạch (Ví dụ: "Vùng gom giá trị: dưới 20k, Vùng chặn lỗ: thủng 18k, Kỳ vọng dài hạn: tăng trưởng 25%"). TUYỆT ĐỐI KHÔNG TRẢ VỀ DẠNG DICTIONARY/OBJECT.
    7. "macro_view": Phân tích chu kỳ ngành và vĩ mô tác động đến hoạt động kinh doanh của doanh nghiệp (5-6 câu).

    BẮT BUỘC KHÓA JSON ĐẦY ĐỦ: "bctc", "catalyst", "risks", "outlook", "recommendation", "price_zone", "macro_view".
    """

    headers = {
        "Authorization": f"Bearer {ALIBABA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3.7-max",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"].strip()
                content = re.sub(r"^```json\s*", "", content)
                content = re.sub(r"^```\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                parsed_data = json.loads(content)

                raw_pz = parsed_data.get("price_zone", "")
                if isinstance(raw_pz, dict):
                    parsed_data["price_zone"] = " | ".join([f"{k}: {v}" for k, v in raw_pz.items()])
                elif isinstance(raw_pz, list):
                    parsed_data["price_zone"] = " - ".join([str(i) for i in raw_pz])
                else:
                    parsed_data["price_zone"] = str(raw_pz)

                return parsed_data
            else:
                print(f"[{symbol}] Lỗi HTTP {response.status_code}")
                break
        except requests.exceptions.Timeout:
            print(f"[{symbol}] ⏳ Timeout lần {attempt + 1}/3, thử lại...")
            time.sleep(3)
        except Exception as e:
            print(f"[{symbol}] Lỗi AI: {e}")
            break

    return None


def build_target_lists(screener_map):
    """
    Trả về (top_symbols, remaining_symbols):
    - top_symbols: dict symbol -> sector, các mã top đầu mỗi ngành (chạy không chia batch)
    - remaining_symbols: dict symbol -> sector, phần còn lại (chia batch)
    """
    industry_groups = {}
    for symbol, item in screener_map.items():
        sector = get_sector(symbol)
        item['sector'] = sector
        industry_groups.setdefault(sector, []).append(item)

    top_symbols = {}
    for sector, items in industry_groups.items():
        items_sorted = sorted(
            items,
            key=lambda x: (
                x.get('fundamental_score', 0),
                x.get('dividend_yield', 0),
                x.get('roe', 0)
            ),
            reverse=True
        )
        for itm in items_sorted[:TOP_PER_SECTOR]:
            top_symbols[itm['symbol']] = sector
        print(f"📌 Nhóm ngành [{sector}] - Top {TOP_PER_SECTOR}: {[i['symbol'] for i in items_sorted[:TOP_PER_SECTOR]]}")

    remaining_symbols = {}
    for symbol, sector in industry_groups.items():
        for item in sector:
            pass
    # xây remaining: tất cả mã trong screener_map mà không nằm trong top
    for symbol, item in screener_map.items():
        if symbol not in top_symbols:
            remaining_symbols[symbol] = get_sector(symbol)

    return top_symbols, remaining_symbols


def save_db(stock_db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(stock_db, f, ensure_ascii=False, indent=4)


def run_group(symbols_dict, label, stock_db, screener_map, sleep_time):
    """Chạy AI cho một nhóm mã và ghi kết quả ngay sau mỗi mã."""
    if not symbols_dict:
        print(f"⚠️ Nhóm [{label}] rỗng, bỏ qua.")
        return 0

    # Sắp xếp ổn định
    symbols_sorted = sorted(symbols_dict.keys())
    total = len(symbols_sorted)
    count = 0

    print(f"\n🚀 Nhóm [{label}]: {total} mã")
    print(f"   Danh sách: {symbols_sorted}\n")

    for idx, symbol in enumerate(symbols_sorted, 1):
        sector = symbols_dict[symbol]
        if symbol not in stock_db:
            stock_db[symbol] = {}
        if symbol not in screener_map:
            continue

        stock_metrics = stock_db[symbol]
        screener_item = screener_map[symbol]

        print(f"[{idx}/{total}] 🔍 [{sector}] {symbol}...")
        ai_result = analyze_stock_with_ai(symbol, stock_metrics, screener_item, sector)

        if ai_result:
            stock_metrics["bctc"] = ai_result.get("bctc", "")
            stock_metrics["catalyst"] = ai_result.get("catalyst", "")
            stock_metrics["risks"] = ai_result.get("risks", "")
            stock_metrics["outlook"] = ai_result.get("outlook", "")
            stock_metrics["ai_recommendation"] = ai_result.get("recommendation", "")
            stock_metrics["ai_price_zone"] = ai_result.get("price_zone", "")
            stock_metrics["macro_view"] = ai_result.get("macro_view", "")
            stock_metrics["ai_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            count += 1
            print(f"  -> ✅ OK ({count}/{total})")
        else:
            print(f"  -> ❌ Lỗi AI")

        # Ghi ngay sau mỗi mã để tránh mất dữ liệu khi bị ngắt
        save_db(stock_db)
        time.sleep(sleep_time)

    return count


def main():
    parser = argparse.ArgumentParser(description="AI analysis: top đầu chạy 1 lần, còn lại chia batch")
    parser.add_argument("--mode", choices=["top", "rest", "all"], default="top",
                        help="top: chỉ chạy top đầu (không chia batch); rest: chạy phần còn lại theo batch; all: chạy cả hai.")
    parser.add_argument("--batch", type=int, default=1,
                        help="Batch hiện tại cho phần 'rest' (1-based). Mặc định 1.")
    parser.add_argument("--total-batches", type=int, default=1,
                        help="Tổng số batch cho phần 'rest'. Mặc định 1 = chạy hết.")
    parser.add_argument("--resume-days", type=int, default=RESUME_DAYS,
                        help=f"Bỏ qua mã đã phân tích trong N ngày gần đây. Mặc định {RESUME_DAYS}.")
    parser.add_argument("--force", action="store_true",
                        help="Bỏ qua cơ chế resume.")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Thời gian nghỉ giữa các mã (giây). Mặc định 3.")
    args = parser.parse_args()

    if not os.path.exists(SCREENER_FILE) or not os.path.exists(DATA_FILE):
        print(f"❌ Không tìm thấy file dữ liệu đầu vào!")
        return

    with open(SCREENER_FILE, "r", encoding="utf-8") as f:
        screener_data = json.load(f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        stock_db = json.load(f)

    screener_map = {item.get('symbol'): item for item in screener_data if item.get('close_price', 0) > 0}

    # Nếu có INPUT_SYMBOLS, dùng nó làm danh sách top và bỏ qua phần còn lại
    if INPUT_SYMBOLS:
        custom_list = [s.strip().upper() for s in INPUT_SYMBOLS.split(",") if s.strip()]
        print(f"🎯 INPUT_SYMBOLS: {custom_list}")
        custom_map = {s: get_sector(s) for s in custom_list if s in screener_map}
        count = run_group(custom_map, "INPUT_SYMBOLS", stock_db, screener_map, args.sleep)
        print(f"\n🎉 Hoàn thành: {count} mã.")
        return

    # Xác định top và remaining
    print("=" * 60)
    print("PHÂN LOẠI MÃ: TOP ĐẦU MỖI NGÀNH vs PHẦN CÒN LẠI")
    print("=" * 60)
    top_symbols, remaining_symbols = build_target_lists(screener_map)

    print(f"\n🔝 Top đầu: {len(top_symbols)} mã")
    print(f"📦 Còn lại: {len(remaining_symbols)} mã")

    # Lọc resume
    if not args.force and args.resume_days > 0:
        top_before = len(top_symbols)
        top_symbols = {s: sec for s, sec in top_symbols.items()
                       if not is_recently_analyzed(stock_db.get(s, {}), args.resume_days)}
        rem_before = len(remaining_symbols)
        remaining_symbols = {s: sec for s, sec in remaining_symbols.items()
                              if not is_recently_analyzed(stock_db.get(s, {}), args.resume_days)}
        print(f"\n⏭️  Resume ({args.resume_days} ngày):")
        print(f"   - Top: bỏ qua {top_before - len(top_symbols)} mã")
        print(f"   - Còn lại: bỏ qua {rem_before - len(remaining_symbols)} mã")

    total_count = 0

    if args.mode in ("top", "all"):
        if top_symbols:
            total_count += run_group(top_symbols, "TOP", stock_db, screener_map, args.sleep)
        else:
            print("✅ Top đầu: đã phân tích gần đây, bỏ qua.")

    if args.mode in ("rest", "all"):
        if remaining_symbols:
            # Chia batch phần còn lại
            remaining_sorted = sorted(remaining_symbols.keys())
            total_rem = len(remaining_sorted)

            total_batches = args.total_batches if args.total_batches >= 1 else 1
            per_batch = (total_rem + total_batches - 1) // total_batches
            start_idx = (args.batch - 1) * per_batch
            end_idx = min(start_idx + per_batch, total_rem)
            batch_symbols = remaining_sorted[start_idx:end_idx]

            if not batch_symbols:
                print(f"⚠️ Batch {args.batch}/{total_batches} rỗng.")
            else:
                batch_map = {s: remaining_symbols[s] for s in batch_symbols}
                print(f"\n📦 Batch {args.batch}/{total_batches} của phần CÒN LẠI: "
                      f"{len(batch_map)}/{total_rem} mã")
                total_count += run_group(batch_map, f"REST-{args.batch}/{total_batches}",
                                         stock_db, screener_map, args.sleep)
        else:
            print("✅ Phần còn lại: đã phân tích gần đây, bỏ qua.")

    print(f"\n🎉 Hoàn thành: cập nhật {total_count} mã vào {DATA_FILE}.")


if __name__ == "__main__":
    main()

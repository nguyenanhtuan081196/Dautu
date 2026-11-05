import os
import json
import pandas as pd
import numpy as np

DATA_FILE = "data.json"
OUTPUT_JSON = "screener_results.json"
OUTPUT_CSV = "screener_summary.csv"

# Phân nhóm ngành chuẩn chi tiết cho VN100 (7 Nhóm ngành)
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
        "GMD", "HAH", "PVT", "HVN", "APH", "ASM", "DBC", "KDC", "MSH", 
        "PAN", "SBT", "DRC", "CSM", "BMP", "DHG", "CTD", "VCG", "HHV", "GEX"
    ]
}

def get_sector(symbol):
    for sector, symbols in SECTOR_MAPPING.items():
        if symbol in symbols:
            return sector
    return "SAN_XUAT_TIEU_DUNG_PHONG_THU"

def evaluate_stock(symbol, data):
    sector = get_sector(symbol)
    pe = data.get("pe", 0)
    pb = data.get("pb", 0)
    roe = data.get("roe", 0)
    roa = data.get("roa", 0)
    dividend_yield = data.get("dividend_yield", 0)
    recommendation = data.get("recommendation", "")
    close_price = data.get("close", 0)
    
    # Các chỉ số nâng cao lấy từ data.json (đồng bộ với bctc_data đã tối ưu)
    cfo_latest = data.get("cfo_latest", 0)
    net_profit_ttm = data.get("net_profit_ttm", 0)
    debt_to_equity = data.get("debt_to_equity", 0)
    gross_margin = data.get("gross_margin", 0)

    bctc_history = data.get("bctc_history", [])
    if not bctc_history:
        return None
        
    latest = bctc_history[0]
    profit_growth_yoy = latest.get("profit_growth_yoy", 0)
    credit_growth_yoy = latest.get("credit_growth_yoy", 0)

    # =========================================================================
    # 1. CHẤM ĐIỂM CƠ BẢN (50 điểm) - ĐA TIÊU CHÍ & CHUẨN ĐẶC THÙ 7 NGÀNH
    # =========================================================================
    fundamental_score = 0
    fund_notes = []

    # --- TIÊU CHÍ RIÊNG THEO NGÀNH (35 điểm) ---
    if sector == "NGAN_HANG":
        if credit_growth_yoy >= 12: 
            fundamental_score += 18; fund_notes.append("Tín dụng mạnh (>=12%)")
        elif credit_growth_yoy >= 8:
            fundamental_score += 10; fund_notes.append("Tín dụng khá")
            
        if roe >= 18: 
            fundamental_score += 17; fund_notes.append("ROE xuất sắc (>=18%)")
        elif roe >= 14: 
            fundamental_score += 10; fund_notes.append("ROE tốt (>=14%)")

    elif sector == "CHUNG_KHOAN":
        if profit_growth_yoy >= 20: 
            fundamental_score += 20; fund_notes.append("LN tăng trưởng mạnh (>=20%)")
        elif profit_growth_yoy >= 10:
            fundamental_score += 10; fund_notes.append("LN hồi phục tốt")
            
        if roe >= 15: 
            fundamental_score += 15; fund_notes.append("ROE ngành CK cao (>=15%)")
        elif roe >= 10:
            fundamental_score += 8; fund_notes.append("ROE ổn định")

    elif sector == "BAT_DONG_SAN":
        if profit_growth_yoy >= 10: 
            fundamental_score += 15; fund_notes.append("LN duy trì tăng trưởng")
        if roe >= 12: 
            fundamental_score += 20; fund_notes.append("ROE BĐS đạt chuẩn (>=12%)")
        elif roe > 0:
            fundamental_score += 10; fund_notes.append("Có lãi dương")

    elif sector == "CONG_NGHE_BAN_LE":
        if profit_growth_yoy >= 20: 
            fundamental_score += 18; fund_notes.append("Tăng trưởng lõi mạnh (>=20%)")
        elif profit_growth_yoy >= 10:
            fundamental_score += 10; fund_notes.append("Tăng trưởng ổn định")
            
        if roe >= 18: 
            fundamental_score += 17; fund_notes.append("ROE xuất sắc")
        elif roe >= 12:
            fundamental_score += 10; fund_notes.append("ROE tốt")

    elif sector == "DIEN_NUOC_HA_TANG":
        if dividend_yield >= 6.0:
            fundamental_score += 20; fund_notes.append(f"Cổ tức hạ tầng hấp dẫn ({dividend_yield}%)")
        elif dividend_yield > 0:
            fundamental_score += 10; fund_notes.append(f"Có chia cổ tức ({dividend_yield}%)")
            
        if roe >= 10:
            fundamental_score += 15; fund_notes.append("ROE ổn định phòng thủ")
        else:
            fundamental_score += 8

    elif sector == "NGUYEN_VAT_LIEU_CHU_KY":
        if profit_growth_yoy >= 15:
            fundamental_score += 18; fund_notes.append("Hưởng lợi chu kỳ / LN tăng mạnh")
        elif profit_growth_yoy >= 0:
            fundamental_score += 10; fund_notes.append("Duy trì nhịp cơ bản")
            
        if roe >= 12:
            fundamental_score += 17; fund_notes.append("ROE chu kỳ tốt")
        else:
            fundamental_score += 8

    else: # SAN_XUAT_TIEU_DUNG_PHONG_THU
        if profit_growth_yoy >= 10: 
            fundamental_score += 15; fund_notes.append("LN tăng trưởng tốt")
        elif profit_growth_yoy >= 0:
            fundamental_score += 8; fund_notes.append("LN ổn định")

        if roe >= 14: 
            fundamental_score += 20; fund_notes.append("ROE sản xuất cao (>=14%)")
        elif roe >= 10:
            fundamental_score += 10; fund_notes.append("ROE khá")

    # --- TIÊU CHÍ CHUNG BỔ SUNG NÂNG CAO (15 điểm) ---
    if roa >= 5.0:
        fundamental_score += 5; fund_notes.append(f"ROA rất cao ({roa}%)")
    elif roa >= 2.5:
        fundamental_score += 3; fund_notes.append(f"ROA tốt ({roa}%)")

    # Xử lý kiểm chứng đặc thù: Ngân hàng không áp dụng bộ lọc CFO và D/E khắt khe như doanh nghiệp sản xuất
    if sector not in ["NGAN_HANG", "CHUNG_KHOAN"]:
        if cfo_latest > 0 and (net_profit_ttm <= 0 or cfo_latest >= net_profit_ttm * 0.8):
            fundamental_score += 5; fund_notes.append("Dòng tiền kinh doanh (CFO) mạnh mẽ")
        elif cfo_latest < 0:
            fundamental_score -= 5; fund_notes.append("⚠️ Cảnh báo: CFO âm")

        if 0 < debt_to_equity <= 1.0:
            fundamental_score += 5; fund_notes.append(f"Cấu trúc tài chính an toàn (D/E: {debt_to_equity})")
        elif debt_to_equity > 2.5:
            fundamental_score -= 5; fund_notes.append(f"⚠️ Cảnh báo: Đòn bẩy nợ cao (D/E: {debt_to_equity})")
    else:
        # Đối với ngân hàng, đánh giá cao nếu duy trì cổ tức hoặc khả năng sinh lời trên tổng tài sản tốt
        if dividend_yield >= 4.0:
            fundamental_score += 5; fund_notes.append(f"Cổ tức tiền mặt tốt ({dividend_yield}%)")
        else:
            fundamental_score += 5; fund_notes.append("Ngân hàng tối ưu giữ vốn mở rộng")

    # =========================================================================
    # 2. CHẤM ĐIỂM KỸ THUẬT (20 điểm) - DÒNG TIỀN & XUNG LỰC QUANT
    # =========================================================================
    technical_score = 0
    tech_notes = []
    rec_upper = recommendation.upper()

    if "BREAKOUT" in rec_upper or "VƯỢT ĐỈNH" in rec_upper or "BỨT PHÁ" in rec_upper:
        technical_score += 20
        tech_notes.append("Breakout / Vượt đỉnh mạnh")
    elif "CẠN CUNG" in rec_upper or "TÍCH LŨY" in rec_upper or "BASE" in rec_upper:
        technical_score += 17
        tech_notes.append("Tích lũy cạn cung (Rủi ro thấp)")
    elif "MUA" in rec_upper or "HẤP DẪN" in rec_upper or "GOM" in rec_upper:
        technical_score += 14
        tech_notes.append("Dòng tiền gom hàng")
    elif "CHỜ" in rec_upper or "GIẰNG CO" in rec_upper:
        technical_score += 9
        tech_notes.append("Đang giằng co / Sideway")
    else:
        technical_score += 5
        tech_notes.append("Xu hướng trung tính / Yếu")

    # =========================================================================
    # 3. ĐÁNH GIÁ ĐỊNH GIÁ AN TOÀN (30 điểm) - P/E, P/B & BIÊN AN TOÀN
    # =========================================================================
    valuation_score = 0
    if 0 < pe < 15 and 0 < pb < 2.2:
        valuation_score += 30
    elif 0 < pe < 20 and 0 < pb < 3.2:
        valuation_score += 18
    else:
        valuation_score += 6

    total_score = fundamental_score + technical_score + valuation_score

    potential_zone = "THEO DÕI THÊM"
    if total_score >= 75:
        potential_zone = "VÙNG TÍCH SẢN ĐẦU TƯ (A+)"
    elif total_score >= 60:
        potential_zone = "VÙNG MUA AN TOÀN (B)"

    return {
        "symbol": symbol,
        "sector": sector,
        "close_price": close_price,
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "roa": roa,
        "dividend_yield": dividend_yield,
        "profit_growth_yoy": profit_growth_yoy,
        "cfo_latest": cfo_latest,
        "debt_to_equity": debt_to_equity,
        "gross_margin": gross_margin,
        "fundamental_score": fundamental_score,
        "technical_score": technical_score,
        "valuation_score": valuation_score,
        "total_score": total_score,
        "potential_zone": potential_zone,
        "technical_status": recommendation,
        "technical_notes": " | ".join(tech_notes),
        "fundamental_notes": " | ".join(fund_notes)
    }

def main():
    print("🚀 Chạy bộ lọc định lượng đa tiêu chí - Đồng bộ hoàn chỉnh với BCTC chuẩn...")
    
    if not os.path.exists(DATA_FILE):
        print(f"⚠️ Không tìm thấy file {DATA_FILE}")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        stock_db = json.load(f)

    results = []
    for symbol, data in stock_db.items():
        res = evaluate_stock(symbol, data)
        if res:
            results.append(res)

    if not results:
        return

    results = sorted(results, key=lambda x: (x.get('fundamental_score', 0), x.get('roe', 0)), reverse=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as jf:
        json.dump(results, jf, ensure_ascii=False, indent=4)
        
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    industry_groups = {}
    for item in results:
        sec = item['sector']
        if sec not in industry_groups:
            industry_groups[sec] = []
        industry_groups[sec].append(item)

    for sector, items in industry_groups.items():
        limit_count = 5
        top_items = items[:limit_count]
        
        print(f"\n📌 NHÓM NGÀNH: [{sector}] - TOP {limit_count} TIÊU BIỂU:")
        print("=" * 140)
        df_sector = pd.DataFrame(top_items)
        print(df_sector[['symbol', 'dividend_yield', 'pe', 'roe', 'cfo_latest', 'debt_to_equity', 'fundamental_score', 'technical_score', 'total_score', 'potential_zone']].to_string(index=False))
        print("=" * 140)

if __name__ == "__main__":
    main()

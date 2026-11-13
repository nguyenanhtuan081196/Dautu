import os
import datetime
import time
import random
import argparse
from app.database.job_io import database, load_stocks, load_history, load_financial_reports, save_stock, save_last_update
from app.database.repositories import upsert_history
import numpy as np
from financial_metrics import extract_advanced_metrics_from_bctc
import requests
from vnstock import Market

VN100_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "VCI", "HCM", "VIX", "MBS", "FTS", "BSI", "CTS", "ORS", "NVL", "PDR",
    "DIG", "NLG", "KDH", "CEO", "DXG", "TCH", "HDG", "KBC", "IDC", "SZC",
    "PHR", "HSG", "NKG", "CTD", "VCG", "HHV", "PNJ", "FRT", "PVD", "PVS",
    "BSR", "REE", "PC1", "NT2", "GMD", "HAH", "PVT", "HVN", "VHC", "ANV",
    "APH", "ASM", "DBC", "DCM", "DPM", "GEX", "KDC", "LIG", "MSH", "PAN",
    "SBT", "TCD", "TLG", "VDP", "VPG", "VTO", "DHC", "IMP", "SBA", "SJS",
    "TID", "VPI", "DRC", "CSM", "BMP", "NTC", "DHG", "VOS", "HAG"
]
VN100_SYMBOLS = sorted(list(set(VN100_SYMBOLS)))

COMPANY_NAMES = {
    "ACB": "Ngân hàng TMCP Á Châu",
    "BCM": "Tổng Công ty Đầu tư và Phát triển Công nghiệp - CTCP (Becamex IDC)",
    "BID": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam (BIDV)",
    "BVH": "Tập đoàn Bảo Việt",
    "CTG": "Ngân hàng TMCP Công Thương Việt Nam (VietinBank)",
    "FPT": "Công ty Cổ phần FPT",
    "GAS": "Tổng Công ty Khí Việt Nam - CTCP (PV GAS)",
    "GVR": "Tập đoàn Công nghiệp Cao su Việt Nam",
    "HDB": "Ngân hàng TMCP Phát triển TP.HCM (HDBank)",
    "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát",
    "MBB": "Ngân hàng TMCP Quân Đội (MB Bank)",
    "MSN": "Công ty Cổ phần Tập đoàn Masan",
    "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động",
    "PLX": "Tập đoàn Xăng dầu Việt Nam (Petrolimex)",
    "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP (PV Power)",
    "SAB": "Tổng Công ty Cổ phần Bia - Rượu - Nước giải khát Sài Gòn (Sabeco)",
    "SHB": "Ngân hàng TMCP Sài Gòn - Hà Nội (SHB)",
    "SSB": "Ngân hàng TMCP Đông Nam Á (SeABank)",
    "SSI": "Công ty Cổ phần Chứng khoán SSI",
    "STB": "Ngân hàng TMCP Sài Gòn Thương Tín (Sacombank)",
    "TCB": "Ngân hàng TMCP Kỹ Thương Việt Nam (Techcombank)",
    "TPB": "Ngân hàng TMCP Tiên Phong (TPBank)",
    "VCB": "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)",
    "VHM": "Công ty Cổ phần Vinhomes",
    "VIB": "Ngân hàng TMCP Quốc tế Việt Nam (VIB)",
    "VIC": "Tập đoàn Vingroup - Công ty Cổ phần",
    "VJC": "Công ty Cổ phần Hàng không Vietjet",
    "VNM": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
    "VPB": "Ngân hàng TMCP Việt Nam Thịnh Vượng (VPBank)",
    "VRE": "Công ty Cổ phần Vincom Retail",
    "VCI": "Công ty Cổ phần Chứng khoán Vietcap",
    "HCM": "Công ty Cổ phần Chứng khoán TP.HCM (HSC)",
    "VIX": "Công ty Cổ phần Chứng khoán VIX",
    "MBS": "Công ty Cổ phần Chứng khoán MB (MBS)",
    "FTS": "Công ty Cổ phần Chứng khoán FPT",
    "BSI": "Công ty Cổ phần Chứng khoán BIDV (BSC)",
    "CTS": "Công ty Cổ phần Chứng khoán VietinBank",
    "ORS": "Công ty Cổ phần Chứng khoán Tiên Phong",
    "NVL": "Công ty Cổ phần Tập đoàn Địa ốc No Va (Novaland)",
    "PDR": "Công ty Cổ phần Phát triển Bất động sản Phát Đạt",
    "DIG": "Tổng Công ty Cổ phần Đầu tư Phát triển Xây dựng (DIC Corp)",
    "NLG": "Công ty Cổ phần Đầu tư Nam Long",
    "KDH": "Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền",
    "CEO": "Công ty Cổ phần Tập đoàn C.E.O",
    "DXG": "Công ty Cổ phần Tập đoàn Đất Xanh",
    "TCH": "Công ty Cổ phần Đầu tư Dịch vụ Tài chính Hoàng Huy",
    "HDG": "Công ty Cổ phần Tập đoàn Hà Đô",
    "KBC": "Tổng Công ty Phát triển Đô thị Kinh Bắc - CTCP",
    "IDC": "Tổng Công ty IDICO - CTCP",
    "SZC": "Công ty Cổ phần Sonadezi Châu Đức",
    "PHR": "Công ty Cổ phần Cao su Phước Hòa",
    "HSG": "Công ty Cổ phần Tập đoàn Hoa Sen",
    "NKG": "Công ty Cổ phần Thép Nam Kim",
    "CTD": "Công ty Cổ phần Xây dựng Coteccons",
    "VCG": "Tổng Công ty Cổ phần Xuất nhập khẩu và Xây dựng Việt Nam (Vinaconex)",
    "HHV": "Công ty Cổ phần Đầu tư Hạ tầng Giao thông Đèo Cả",
    "PNJ": "Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận",
    "FRT": "Công ty Cổ phần Bán lẻ Kỹ thuật số FPT",
    "PVD": "Tổng Công ty Cổ phần Khoan và Dịch vụ Khoan Dầu khí (PV Drilling)",
    "PVS": "Tổng Công ty Cổ phần Dịch vụ Kỹ thuật Dầu khí Việt Nam (PTSC)",
    "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn",
    "REE": "Công ty Cổ phần Cơ Điện Lạnh (REE)",
    "PC1": "Công ty Cổ phần Tập đoàn PC1",
    "NT2": "Công ty Cổ phần Điện lực Dầu khí Nhơn Trạch 2",
    "GMD": "Công ty Cổ phần Gemadept",
    "HAH": "Công ty Cổ phần Vận tải và Xếp dỡ Hải An",
    "PVT": "Tổng Công ty Cổ phần Vận tải Dầu khí (PVTrans)",
    "HVN": "Tổng Công ty Hàng không Việt Nam - CTCP (Vietnam Airlines)",
    "VHC": "Công ty Cổ phần Vĩnh Hoàn",
    "ANV": "Công ty Cổ phần Nam Việt (Navico)",
    "APH": "Công ty Cổ phần Tập đoàn An Phát Holdings",
    "ASM": "Công ty Cổ phần Tập đoàn Sao Mai",
    "DBC": "Công ty Cổ phần Tập đoàn Dabaco Việt Nam",
    "DCM": "Công ty Cổ phần Phân bón Dầu khí Cà Mau",
    "DPM": "Tổng Công ty Phân bón và Hóa chất Dầu khí - CTCP (PVFCCo)",
    "GEX": "Công ty Cổ phần Tập đoàn Gelex",
    "KDC": "Công ty Cổ phần Tập đoàn Kido",
    "LIG": "Công ty Cổ phần Licogi 13",
    "MSH": "Công ty Cổ phần May Sông Hồng",
    "PAN": "Công ty Cổ phần Tập đoàn PAN",
    "SBT": "Công ty Cổ phần Thành Thành Công - Biên Hòa (TTC AgriS)",
    "TCD": "Công ty Cổ phần Tập đoàn Xây dựng và Phát triển Hạ tầng",
    "TLG": "Công ty Cổ phần Tập đoàn Thiên Long",
    "VDP": "Công ty Cổ phần Thuốc thú y Trung ương I (Vinavetco)",
    "VPG": "Công ty Cổ phần Thép Việt - Ý",
    "VTO": "Công ty Cổ phần Vận tải Xăng dầu Vitaco",
    "DHC": "Công ty Cổ phần Đông Hải Bến Tre",
    "IMP": "Công ty Cổ phần Dược phẩm Imexpharm",
    "SBA": "Công ty Cổ phần Mía đường Sông Lam",
    "SJS": "Công ty Cổ phần SJ Group",
    "TID": "Công ty Cổ phần Tập đoàn Tin Việt Nam",
    "VPI": "Công ty Cổ phần Đầu tư và Phát triển Bất động sản VPI",
    "DRC": "Công ty Cổ phần Cao su Đà Nẵng",
    "CSM": "Công ty Cổ phần Cao su Sài Gòn - Cà Mau",
    "BMP": "Công ty Cổ phần Nhựa Bình Minh",
    "NTC": "Công ty Cổ phần Khu Công nghiệp Nam Tân Uyên",
    "DHG": "Công ty Cổ phần Dược Hậu Giang",
    "VOS": "Công ty Cổ phần Vận tải Biển Việt Nam",
    "HAG": "Công ty Cổ phần Hoàng Anh Gia Lai",
}

VNDIRECT_RATIOS = {
    "pe": "PRICE_TO_EARNINGS",
    "pb": "PRICE_TO_BOOK",
    "eps": "EPS_TR",
    "roe": "ROAE_TR_AVG5Q",
    "roa": "ROAA_TR_AVG5Q",
    "dividend_yield": "DIVIDEND_YIELD"
}


def get_vndirect_ratio(symbol, ratio_code):
    url = "https://api-finfo.vndirect.com.vn/v4/ratios"
    params = {"q": f"code:{symbol}~ratioCode:{ratio_code}", "size": 1, "sort": "reportDate:desc"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return float(data[0].get("value", 0) or 0)
    except Exception:
        pass
    return 0


def get_company_overview(symbol, close_price=0, *, sleep_fn=None):
    company_name = COMPANY_NAMES.get(symbol, symbol)
    total_shares = 0
    market_cap = 0

    try:
        url = "https://api-finfo.vndirect.com.vn/v4/ratios"
        params = {
            "q": f"code:{symbol}~ratioCode:SHARE_OUTSTANDING",
            "size": 1,
            "sort": "reportDate:desc"
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                total_shares = float(data[0].get("value", 0) or 0)
    except Exception as e:
        print(f"   ⚠️ VNDirect SHARE_OUTSTANDING lỗi cho {symbol}: {e}")

    # Space the fallback request even when the first endpoint returns no usable value.
    if total_shares == 0:
        jittered_sleep(0.25, sleep_fn=sleep_fn)

    if total_shares == 0:
        try:
            url = "https://api-finfo.vndirect.com.vn/v4/ratios"
            params = {
                "q": f"code:{symbol}~ratioCode:MARKET_CAP",
                "size": 1,
                "sort": "reportDate:desc"
            }
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    market_cap = float(data[0].get("value", 0) or 0)
                    if market_cap > 0 and close_price > 0:
                        total_shares = market_cap / (close_price * 1000)
        except Exception as e:
            print(f"   ⚠️ VNDirect MARKET_CAP lỗi cho {symbol}: {e}")

    if market_cap == 0 and close_price > 0 and total_shares > 0:
        market_cap = close_price * 1000 * total_shares

    return {
        "company_name": company_name,
        "market_cap": market_cap,
        "total_shares": total_shares,
    }


def aggregate_candles(data, interval):
    if not data:
        return []
    if interval == 'D1':
        return data

    groups = {}
    for bar in data:
        date = datetime.datetime.strptime(bar['time'], '%Y-%m-%d')
        if interval == 'W1':
            start_of_week = date - datetime.timedelta(days=date.weekday())
            key = start_of_week.strftime('%Y-%m-%d')
        elif interval == 'MN':
            key = date.strftime('%Y-%m-01')

        if key not in groups:
            groups[key] = {
                "time": key,
                "open": bar['open'],
                "high": bar['high'],
                "low": bar['low'],
                "close": bar['close'],
                "volume": bar['volume']
            }
        else:
            groups[key]['high'] = max(groups[key]['high'], bar['high'])
            groups[key]['low'] = min(groups[key]['low'], bar['low'])
            groups[key]['close'] = bar['close']
            groups[key]['volume'] += bar['volume']

    return sorted(list(groups.values()), key=lambda x: x['time'])


def jittered_sleep(seconds, *, sleep_fn=None, random_fn=None):
    """Sleep with +/-20% jitter to spread provider requests over time."""
    delay = max(0.0, float(seconds))
    if delay == 0:
        return
    sleeper = sleep_fn or time.sleep
    randomizer = random_fn or random.uniform
    sleeper(randomizer(delay * 0.8, delay * 1.2))


def fetch_history_with_fallback(symbol, start_date, end_date, *, sleep_fn=None):
    """Fetch D1 candles using the supported vnstock v6 Market API.

    FHSC is the default source. A second source can be configured explicitly
    through VNSTOCK_MARKET_FALLBACK_SOURCE when its credentials are available.
    """
    primary = os.getenv("VNSTOCK_MARKET_SOURCE", "fhsc").strip().lower()
    fallback = os.getenv("VNSTOCK_MARKET_FALLBACK_SOURCE", "").strip().lower()
    sources = list(dict.fromkeys(source for source in (primary, fallback) if source))

    for source in sources:
        for attempt in range(2):
            try:
                market = Market(source)
                equity = market.equity(symbol)
                df = equity.ohlcv(
                    start=start_date,
                    end=end_date,
                    interval="1D",
                )
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                print(
                    f"⚠️ vnstock v6 Market/{source} lỗi cho {symbol} "
                    f"(lần {attempt + 1}/2): {exc}"
                )
            if attempt == 0:
                # Back off after either an exception or an empty provider response.
                jittered_sleep(1, sleep_fn=sleep_fn)
        jittered_sleep(0.5, sleep_fn=sleep_fn)
    return None


def parse_bctc_history(symbol, reports=None):
    if reports is None:
        try:
            reports = load_financial_reports(database(), symbol)
        except Exception:
            return []
    data = reports or {}

    balance_sheet = data.get("balance_sheet", [])
    income_statement = data.get("income_statement", [])
    if not balance_sheet or not income_statement:
        return []

    bs_dict = {}
    for item in balance_sheet:
        p = item.get("period")
        if p is None:
            continue
        if p not in bs_dict:
            bs_dict[p] = {}
        bs_dict[p][item.get("id")] = item.get("value")

    is_dict = {}
    for item in income_statement:
        p = item.get("period")
        if p is None:
            continue
        if p not in is_dict:
            is_dict[p] = {}
        is_dict[p][item.get("id")] = item.get("value")

    periods = sorted(list(set(bs_dict.keys()).intersection(set(is_dict.keys()))), reverse=True)
    if not periods:
        return []

    bctc_records = []
    for idx, curr_p in enumerate(periods):
        if curr_p is None or "-" not in curr_p:
            continue
            
        prev_p = periods[idx + 1] if idx + 1 < len(periods) else None
        
        try:
            year, q_str = curr_p.split("-")
        except ValueError:
            continue
            
        yoy_p = f"{int(year) - 1}-{q_str}"

        total_assets = bs_dict[curr_p].get("BS_TOTAL_ASSETS", bs_dict[curr_p].get("TOTAL_ASSETS", 0)) or 0
        loans = bs_dict[curr_p].get("BS_LOANS_TO_CUSTOMERS", 0) or 0
        equity = bs_dict[curr_p].get("BS_EQUITY", bs_dict[curr_p].get("EQUITY", 0)) or 0

        nii = is_dict[curr_p].get("IS_NET_INTEREST_INCOME", 0) or 0
        pat = is_dict[curr_p].get("IS_NET_PROFIT_AFTER_TAX", is_dict[curr_p].get("NET_PROFIT_AFTER_TAX", 0)) or 0

        loans_prev = (bs_dict.get(prev_p, {}).get("BS_LOANS_TO_CUSTOMERS", 0) or 0) if prev_p else 0
        loans_yoy = bs_dict.get(yoy_p, {}).get("BS_LOANS_TO_CUSTOMERS", 0) or 0
        credit_growth_qoq = ((loans - loans_prev) / loans_prev * 100) if loans_prev else 0
        credit_growth_yoy = ((loans - loans_yoy) / loans_yoy * 100) if loans_yoy else 0

        pat_prev = (is_dict.get(prev_p, {}).get("IS_NET_PROFIT_AFTER_TAX", is_dict.get(prev_p, {}).get("NET_PROFIT_AFTER_TAX", 0)) or 0) if prev_p else 0
        pat_yoy = is_dict.get(yoy_p, {}).get("IS_NET_PROFIT_AFTER_TAX", is_dict.get(yoy_p, {}).get("NET_PROFIT_AFTER_TAX", 0)) or 0
        pat_growth_qoq = ((pat - pat_prev) / pat_prev * 100) if pat_prev else 0
        pat_growth_yoy = ((pat - pat_yoy) / pat_yoy * 100) if pat_yoy else 0

        roe_q = (pat / equity * 100) if equity else 0

        bctc_records.append({
            "period": curr_p,
            "total_assets": round(total_assets / 1e9, 2),
            "loans": round(loans / 1e9, 2),
            "equity": round(equity / 1e9, 2),
            "net_interest_income": round(nii / 1e9, 2),
            "net_profit": round(pat / 1e9, 2),
            "credit_growth_qoq": round(credit_growth_qoq, 2),
            "credit_growth_yoy": round(credit_growth_yoy, 2),
            "profit_growth_qoq": round(pat_growth_qoq, 2),
            "profit_growth_yoy": round(pat_growth_yoy, 2),
            "roe_quarter": round(roe_q, 2)
        })

    return bctc_records


def main(argv=None, *, save_fn=None, sleep_fn=None, on_symbol_saved=None):
    """Refresh prices and upsert successful symbols directly into MongoDB Atlas.

    Returns the symbols whose complete stock payload was successfully persisted.
    """
    parser = argparse.ArgumentParser(description="Fetch prices and update MongoDB Atlas")
    parser.add_argument("--symbols", default=os.getenv("INPUT_SYMBOLS", ",".join(VN100_SYMBOLS)), help="Comma-separated symbols")
    parser.add_argument("--sessions", type=int, default=int(os.getenv("PRICE_SESSIONS", "30")), help="Number of daily sessions")
    args = parser.parse_args(argv)
    save_fn = save_fn or save_stock
    target_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    num_sessions = max(1, args.sessions)
    if not target_symbols:
        parser.error("At least one symbol is required")
    primary_source = os.getenv("VNSTOCK_MARKET_SOURCE", "fhsc").strip().lower()
    if primary_source == "fhsc" and not os.getenv("FHSC_API_KEY", "").strip():
        raise RuntimeError("Missing required FHSC_API_KEY for VNstock source 'fhsc'")

    db = database()
    print(f"\n🚀 Bắt đầu cào dữ liệu cho {len(target_symbols)} mã (Lấy đúng {num_sessions} phiên giao dịch gần nhất)...")

    stock_db = load_stocks(db)

    total = len(target_symbols)
    successful_symbols = []
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    approx_days = max(num_sessions * 2, 365)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=approx_days)).strftime("%Y-%m-%d")

    for i, symbol in enumerate(target_symbols):
        print(f"[{i+1}/{total}] Đang xử lý: {symbol}...")
        try:
            closes, volumes = [], []
            close_price, volume = 0, 0
            history_d1 = []

            try:
                df = fetch_history_with_fallback(symbol, start_date, end_date, sleep_fn=sleep_fn)
                if df is not None and not df.empty:
                    df = df.tail(num_sessions)

                    closes = df['close'].tolist()
                    volumes = df['volume'].tolist()
                    close_price = closes[-1]
                    volume = volumes[-1]

                    new_history_d1 = []
                    for _, row in df.iterrows():
                        time_val = row['time']
                        time_str = time_val.strftime('%Y-%m-%d') if hasattr(time_val, 'strftime') else str(time_val)[:10]

                        new_history_d1.append({
                            "time": time_str,
                            "open": float(row.get('open', row['close'])),
                            "high": float(row.get('high', row['close'])),
                            "low": float(row.get('low', row['close'])),
                            "close": float(row['close']),
                            "volume": int(row.get('volume', 0))
                        })

                    existing_history_d1 = load_history(db, symbol, "D1")
                    merged_dict = {item['time']: item for item in existing_history_d1}
                    for item in new_history_d1:
                        merged_dict[item['time']] = item

                    history_d1 = sorted(list(merged_dict.values()), key=lambda x: x['time'])

                    closes = [bar['close'] for bar in history_d1]
                    volumes = [bar['volume'] for bar in history_d1]

            except Exception as e:
                print(f"⚠️ Lỗi xử lý lịch sử {symbol}: {e}")

            if close_price <= 0:
                print(f"⚠️ Bỏ qua {symbol} do không lấy được giá.")
                continue

            company_overview = get_company_overview(symbol, close_price, sleep_fn=sleep_fn)
            jittered_sleep(0.3, sleep_fn=sleep_fn)

            ratios = {}
            for key, code in VNDIRECT_RATIOS.items():
                ratios[key] = get_vndirect_ratio(symbol, code)
                jittered_sleep(0.2, sleep_fn=sleep_fn)

            status = "ĐANG TÍCH LŨY NỀN"
            detail = "Đang siết nền tích lũy biên độ hẹp."
            if len(closes) >= 20 and len(volumes) >= 20:
                recent_vols = volumes[-20:]
                ma_vol_20 = np.mean(recent_vols)
                vol_ratio = volume / ma_vol_20 if ma_vol_20 > 0 else 1.0
                price_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100 if closes[-2] > 0 else 0

                if vol_ratio < 0.7 and abs(price_change_pct) < 1.5:
                    status = "ĐANG TÍCH LŨY NỀN (CẠN CUNG)"
                    detail = f"Khối lượng cạn kiệt ở mức {vol_ratio:.2f}x MA20."
                elif vol_ratio > 1.5 and price_change_pct > 1.5:
                    status = "SẴN SÀNG BREAKOUT (NỔ VOL)"
                    detail = f"Khối lượng bùng nổ đạt {vol_ratio:.2f}x MA20 kèm giá tăng."
                elif closes[-1] > np.mean(closes[-20:]):
                    status = "ĐANG GOM HÀNG"
                    detail = "Dòng tiền duy trì ổn định trên MA20."

            history_w1 = aggregate_candles(history_d1, 'W1')
            history_mn = aggregate_candles(history_d1, 'MN')

            symbol_history_data = {
                "history_d1": history_d1,
                "history_w1": history_w1,
                "history_mn": history_mn
            }
            upsert_history(db, symbol, symbol_history_data)

            reports = load_financial_reports(db, symbol)
            bctc_history = parse_bctc_history(symbol, reports)
            adv_metrics = extract_advanced_metrics_from_bctc(symbol, reports=reports)
            old_data = stock_db.get(symbol, {})

            current_time_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            crawled_data = {
                "symbol": symbol,
                "company_name": company_overview["company_name"],
                "market_cap": round(company_overview["market_cap"] / 1e9, 2),
                "total_shares": int(company_overview["total_shares"]),
                "close": int(close_price * 1000),
                "volume": int(volume),
                "pe": round(ratios.get("pe", 0), 2),
                "pb": round(ratios.get("pb", 0), 2),
                "eps": int(ratios.get("eps", 0)),
                "roe": round(ratios.get("roe", 0) * 100, 1),
                "roa": round(ratios.get("roa", 0) * 100, 1),
                "dividend_yield": round(ratios.get("dividend_yield", 0) * 100, 2),
                "cfo_latest": adv_metrics["cfo_latest"],
                "cfo_ttm": adv_metrics["cfo_ttm"],
                "debt_to_equity": adv_metrics["debt_to_equity"],
                "liabilities_to_equity": adv_metrics["liabilities_to_equity"],
                "gross_margin": adv_metrics["gross_margin"],
                "net_profit_ttm": adv_metrics["net_profit_ttm"],
                "recommendation": status,
                "price_zone": detail,
                "updated_at": current_time_str,
                "bctc_history": bctc_history,
            }

            stock_db[symbol] = {**old_data, **crawled_data}
            save_fn(db, symbol, stock_db[symbol])
            successful_symbols.append(symbol)
            jittered_sleep(1.5, sleep_fn=sleep_fn)

        except Exception as exc:
            print(f"❌ Lỗi xử lý {symbol}: {type(exc).__name__}: {exc}")
            continue

    if successful_symbols:
        crawl_timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        save_last_update(db, {
            "last_update": crawl_timestamp,
            "symbols_updated": len(successful_symbols),
        })
        print(f"✅ Đã ghi dữ liệu giá và metadata trực tiếp vào MongoDB: {crawl_timestamp}")
    else:
        print("⚠️ Không có mã nào được cập nhật; giữ nguyên metadata lần cập nhật trước.")
    return successful_symbols


if __name__ == "__main__":
    main()
import os
import datetime
import time
import json
import subprocess
import numpy as np
import requests
from vnstock import Quote

DATA_FILE = "data.json"
LAST_UPDATE_FILE = "last_update.json"
HISTORY_DIR = "history"
BCTC_DIR = "bctc_data"
JS_LIB_FILE = "lightweight-charts.js"

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

# Hardcode tên công ty đầy đủ cho các mã VN100
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
                return float(data[0].get("value", 0))
    except Exception:
        pass
    return 0


def get_company_overview(symbol, close_price=0):
    """
    Lấy tên doanh nghiệp trực tiếp từ từ điển hardcode COMPANY_NAMES (không gọi API).
    Lấy số cổ phiếu và vốn hóa từ VNDirect API.
    """
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


def fetch_history_with_fallback(symbol, start_date, end_date):
    sources = ['TCBS', 'VCI']
    for src in sources:
        for attempt in range(2):
            try:
                quote = Quote(source=src, symbol=symbol)
                df = quote.history(start=start_date, end=end_date)
                if df is not None and not df.empty:
                    return df
            except Exception:
                time.sleep(1)
        time.sleep(0.5)
    return None


def parse_bctc_history(symbol):
    filepath = os.path.join(BCTC_DIR, f"{symbol}.json")
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    balance_sheet = data.get("balance_sheet", [])
    income_statement = data.get("income_statement", [])
    if not balance_sheet or not income_statement:
        return []

    bs_dict = {}
    for item in balance_sheet:
        p = item.get("period")
        if p not in bs_dict:
            bs_dict[p] = {}
        bs_dict[p][item.get("id")] = item.get("value")

    is_dict = {}
    for item in income_statement:
        p = item.get("period")
        if p not in is_dict:
            is_dict[p] = {}
        is_dict[p][item.get("id")] = item.get("value")

    periods = sorted(list(set(bs_dict.keys()).intersection(set(is_dict.keys()))), reverse=True)
    if not periods:
        return []

    bctc_records = []
    for idx, curr_p in enumerate(periods):
        prev_p = periods[idx + 1] if idx + 1 < len(periods) else None
        year, q_str = curr_p.split("-")
        yoy_p = f"{int(year) - 1}-{q_str}"

        total_assets = bs_dict[curr_p].get("BS_TOTAL_ASSETS", bs_dict[curr_p].get("TOTAL_ASSETS", 0))
        loans = bs_dict[curr_p].get("BS_LOANS_TO_CUSTOMERS", 0)
        equity = bs_dict[curr_p].get("BS_EQUITY", bs_dict[curr_p].get("EQUITY", 0))

        nii = is_dict[curr_p].get("IS_NET_INTEREST_INCOME", 0)
        pat = is_dict[curr_p].get("IS_NET_PROFIT_AFTER_TAX", is_dict[curr_p].get("NET_PROFIT_AFTER_TAX", 0))

        loans_prev = bs_dict.get(prev_p, {}).get("BS_LOANS_TO_CUSTOMERS", 0) if prev_p else 0
        loans_yoy = bs_dict.get(yoy_p, {}).get("BS_LOANS_TO_CUSTOMERS", 0)
        credit_growth_qoq = ((loans - loans_prev) / loans_prev * 100) if loans_prev else 0
        credit_growth_yoy = ((loans - loans_yoy) / loans_yoy * 100) if loans_yoy else 0

        pat_prev = is_dict.get(prev_p, {}).get("IS_NET_PROFIT_AFTER_TAX", is_dict.get(prev_p, {}).get("NET_PROFIT_AFTER_TAX", 0)) if prev_p else 0
        pat_yoy = is_dict.get(yoy_p, {}).get("IS_NET_PROFIT_AFTER_TAX", is_dict.get(yoy_p, {}).get("NET_PROFIT_AFTER_TAX", 0))
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


def extract_advanced_metrics_from_bctc(symbol):
    filepath = os.path.join(BCTC_DIR, f"{symbol}.json")
    if not os.path.exists(filepath):
        return {"cfo_latest": 0, "debt_to_equity": 0, "gross_margin": 0, "net_profit_ttm": 0}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"cfo_latest": 0, "debt_to_equity": 0, "gross_margin": 0, "net_profit_ttm": 0}

    balance_sheet = data.get("balance_sheet", [])
    cash_flow = data.get("cash_flow", [])
    income_statement = data.get("income_statement", [])

    latest_period = balance_sheet[0].get("period") if balance_sheet else None
    if not latest_period and income_statement:
        latest_period = income_statement[0].get("period")

    latest_cfo = 0
    cfo_ids = [
        "CF_NET_CASH_FLOWS_FROM_OPERATING_ACTIVITIES",
        "CF_OPERATE_CASH_FLOW",
        "CFO",
        "CF_NET_CASH"
    ]
    if cash_flow:
        for item in cash_flow:
            if latest_period and item.get("period") == latest_period and item.get("id") in cfo_ids:
                latest_cfo = item.get("value", 0)
                break
        if latest_cfo == 0:
            for item in cash_flow:
                if item.get("id") in cfo_ids:
                    latest_cfo = item.get("value", 0)
                    break

    total_liabilities = 0
    equity = 0
    if balance_sheet:
        for item in balance_sheet:
            if latest_period and item.get("period") == latest_period:
                item_id = item.get("id", "")
                val = item.get("value", 0)
                if item_id in ["BS_TOTAL_LIABILITIES", "TOTAL_LIABILITIES"]:
                    total_liabilities = val
                elif item_id in ["BS_EQUITY", "EQUITY"]:
                    equity = val

    debt_to_equity = round(total_liabilities / equity, 2) if equity > 0 else 0

    gross_profit = 0
    revenue = 0
    is_bank_or_sec = False

    if income_statement:
        for item in income_statement:
            if latest_period and item.get("period") == latest_period:
                item_id = item.get("id", "")
                val = item.get("value", 0)
                if item_id in ["IS_GROSS_PROFIT", "GROSS_PROFIT"]:
                    gross_profit = val
                elif item_id in ["IS_NET_REVENUE", "REVENUE", "NET_REVENUE", "IS_TOTAL_REVENUE"]:
                    revenue = val
                elif item_id in ["IS_NET_INTEREST_INCOME"]:
                    is_bank_or_sec = True

    if is_bank_or_sec:
        gross_margin = 0.0
    else:
        gross_margin = round((gross_profit / revenue) * 100, 1) if revenue > 0 else 0

    net_profit_ttm = 0
    pat_ids = ["IS_NET_PROFIT_AFTER_TAX", "NET_PROFIT_AFTER_TAX", "IS_PROFIT_AFTER_TAX"]
    pat_items = [item for item in income_statement if item.get("id") in pat_ids]
    if pat_items:
        pat_items = sorted(pat_items, key=lambda x: x.get("period", ""), reverse=True)
        latest_4q = pat_items[:4]
        net_profit_ttm = sum([q.get("value", 0) for q in latest_4q])

    return {
        "cfo_latest": round(latest_cfo / 1e9, 2),
        "debt_to_equity": debt_to_equity,
        "gross_margin": gross_margin,
        "net_profit_ttm": round(net_profit_ttm / 1e9, 2)
    }


def auto_git_push():
    try:
        print("🔄 Đang đồng bộ dữ liệu lên GitHub...")
        
        # 1. Fetch thông tin mới nhất từ GitHub về
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        
        # 2. Thử pull về. Nếu có conflict, tự động hủy rebase đang kẹt và ưu tiên data.json từ PC
        pull_result = subprocess.run(["git", "pull", "origin", "main", "--rebase"], capture_output=True, text=True)
        if pull_result.returncode != 0:
            print("⚠️ Phát hiện xung đột, đang xử lý ưu tiên file data.json trên PC...")
            subprocess.run(["git", "rebase", "--abort"], check=False)
            subprocess.run(["git", "checkout", "--ours", DATA_FILE], check=False)
            subprocess.run(["git", "add", DATA_FILE], check=False)

        # 3. Add lại các file thay đổi từ quá trình cào trên PC
        subprocess.run(["git", "add", DATA_FILE], check=True)
        subprocess.run(["git", "add", LAST_UPDATE_FILE], check=True)
        subprocess.run(["git", "add", HISTORY_DIR], check=True)
        if os.path.exists(BCTC_DIR):
            subprocess.run(["git", "add", BCTC_DIR], check=True)
        if os.path.exists(JS_LIB_FILE):
            subprocess.run(["git", "add", JS_LIB_FILE], check=True)

        # 4. Kiểm tra xem có thay đổi thực sự hay không
        status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("ℹ️ Không có dữ liệu thay đổi nào mới để đẩy lên.")
            return

        # 5. Commit và Push lên GitHub
        commit_msg = f"Auto update symbols data & last_update timestamp - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push", "origin", "main", "--force-with-lease"], check=True)
        print("🚀 Đẩy dữ liệu lên GitHub thành công!")
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Lỗi Git automation: {e}")
    except Exception as e:
        print(f"⚠️ Lỗi không xác định khi Git push: {e}")


def main():
    print("==================================================")
    print("        BƯỚC 1: CHỌN PHẠM VI MÃ CỔ PHIẾU        ")
    print("==================================================")
    print("1. Cào TOÀN BỘ danh sách VN100 (Mặc định)")
    print("2. Cào RIÊNG TỪNG MÃ (Tùy chọn mã cụ thể)")

    target_symbols = VN100_SYMBOLS
    mode_choice = input("Nhập lựa chọn chế độ (1/2, mặc định 1): ").strip()
    if mode_choice == '2':
        raw_input_symbols = input("Nhập mã cổ phiếu muốn cào (cách nhau bởi dấu phẩy, VD: FPT,MWG,ACB): ").strip()
        if raw_input_symbols:
            target_symbols = [s.strip().upper() for s in raw_input_symbols.split(",") if s.strip()]
            print(f"-> Đã chọn cào riêng các mã: {target_symbols}")
        else:
            print("⚠️ Không nhận được mã hợp lệ, tự động quay về cào toàn bộ VN100.")
    else:
        print("-> Đã chọn: Cào toàn bộ danh sách VN100.")

    print("\n==================================================")
    print("        BƯỚC 2: CHỌN SỐ PHIÊN GIAO DỊCH         ")
    print("==================================================")
    print("1. Gần nhất: 30 phiên giao dịch gần nhất (Mặc định)")
    print("2. Dài hạn: 10 năm gần đây (~2500 phiên)")
    print("3. Tùy chỉnh: Nhập số phiên tự do (VD: 2, 5, 100 phiên)")

    choice = input("Nhập lựa chọn số phiên (1/2/3, mặc định 1): ").strip()

    num_sessions = 30
    if choice == '2':
        num_sessions = 2500
        print("-> Đã chọn chế độ cào 10 năm dữ liệu (~2500 phiên).")
    elif choice == '3':
        try:
            custom_sessions = int(input("Nhập số phiên muốn cào (ví dụ: 2, 5, 100): ").strip())
            if custom_sessions > 0:
                num_sessions = custom_sessions
                print(f"-> Đã chọn cào tùy chỉnh: {num_sessions} phiên.")
        except ValueError:
            print("⚠️ Nhập sai định dạng, tự động quay về mặc định 30 phiên.")
    else:
        print("-> Đã chọn chế độ mặc định (30 phiên gần nhất).")

    print(f"\n🚀 Bắt đầu cào dữ liệu cho {len(target_symbols)} mã (Lấy đúng {num_sessions} phiên giao dịch gần nhất)...")

    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)

    stock_db = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                stock_db = json.load(f)
        except Exception:
            pass

    total = len(target_symbols)
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    approx_days = max(num_sessions * 2, 365)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=approx_days)).strftime("%Y-%m-%d")

    for i, symbol in enumerate(target_symbols):
        print(f"[{i+1}/{total}] Đang xử lý: {symbol}...")
        closes, volumes = [], []
        close_price, volume = 0, 0
        history_d1 = []

        try:
            df = fetch_history_with_fallback(symbol, start_date, end_date)
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

                history_file_path = os.path.join(HISTORY_DIR, f"{symbol}.json")
                existing_history_d1 = []

                if os.path.exists(history_file_path):
                    try:
                        with open(history_file_path, "r", encoding="utf-8") as sf:
                            old_history_data = json.load(sf)
                            existing_history_d1 = old_history_data.get("history_d1", [])
                    except Exception:
                        pass

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

        company_overview = get_company_overview(symbol, close_price)
        time.sleep(0.3)

        ratios = {}
        for key, code in VNDIRECT_RATIOS.items():
            ratios[key] = get_vndirect_ratio(symbol, code)
            time.sleep(0.2)

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
        with open(os.path.join(HISTORY_DIR, f"{symbol}.json"), "w", encoding="utf-8") as sf:
            json.dump(symbol_history_data, sf, ensure_ascii=False)

        bctc_history = parse_bctc_history(symbol)
        adv_metrics = extract_advanced_metrics_from_bctc(symbol)
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
            "debt_to_equity": adv_metrics["debt_to_equity"],
            "gross_margin": adv_metrics["gross_margin"],
            "net_profit_ttm": adv_metrics["net_profit_ttm"],
            "recommendation": status,
            "price_zone": detail,
            "updated_at": current_time_str,
            "bctc_history": bctc_history,
        }

        stock_db[symbol] = {**old_data, **crawled_data}

        time.sleep(1.5)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(stock_db, f, ensure_ascii=False, indent=4)

    crawl_timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(LAST_UPDATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_update": crawl_timestamp}, f, ensure_ascii=False)

    print(f"✅ Đã lưu file {LAST_UPDATE_FILE} với mốc thời gian: {crawl_timestamp}")

    auto_git_push()


if __name__ == "__main__":
    main()

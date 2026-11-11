import os
import time
import datetime
import argparse
from app.database.job_io import database, save_last_update
from app.database.repositories import upsert_financial_reports
from vnstock import Fundamental


# Danh sách chuẩn VN100
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

def fetch_financial_reports(symbol, db=None):
    try:
        fun = Fundamental()
        stock_obj = fun.equity(symbol)
        
        # 1. Cào Bảng cân đối kế toán
        df_balance = stock_obj.balance_sheet(period='quarter')
        # 2. Cào Báo cáo kết quả kinh doanh
        df_income = stock_obj.income_statement(period='quarter')
        
        # 3. Cào Báo cáo lưu chuyển tiền tệ (QUAN TRỌNG: Lấy dữ liệu Dòng tiền CFO)
        df_cashflow = None
        try:
            df_cashflow = stock_obj.cash_flow(period='quarter')
        except Exception as e:
            print(f"⚠️ Không lấy được bảng Cash Flow cho {symbol}: {e}")
        
        reports = {}
        if df_balance is not None and not df_balance.empty:
            reports['balance_sheet'] = df_balance.to_dict(orient="records")
        if df_income is not None and not df_income.empty:
            reports['income_statement'] = df_income.to_dict(orient="records")
        if df_cashflow is not None and not df_cashflow.empty:
            reports['cash_flow'] = df_cashflow.to_dict(orient="records")
            
        if not reports:
            print(f"⚠️ Không có dữ liệu BCTC cho mã: {symbol}")
            return False

        reports['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if db is None:
            db = database()
        upsert_financial_reports(db, symbol, reports)
        print(f"✅ Đã ghi BCTC trực tiếp MongoDB cho mã: {symbol}")
        return True
        
    except Exception as e:
        print(f"❌ Lỗi mã {symbol}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Crawl quarterly financial reports into MongoDB Atlas")
    parser.add_argument("--symbols", default=os.getenv("INPUT_SYMBOLS", "FPT"), help="Comma-separated symbols")
    parser.add_argument("--all-vn100", action="store_true", help="Crawl the full VN100 universe")
    parser.add_argument("--sleep", type=float, default=0.4)
    args = parser.parse_args()
    target_symbols = VN100_SYMBOLS if args.all_vn100 else [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not target_symbols:
        parser.error("Provide --symbols or --all-vn100")
    db = database()
    successful = []
    for index, symbol in enumerate(target_symbols, 1):
        print(f"[{index}/{len(target_symbols)}] Crawling BCTC: {symbol}")
        if fetch_financial_reports(symbol, db):
            successful.append(symbol)
        time.sleep(args.sleep)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_last_update(db, {"bctc_updated_at": timestamp, "successful_symbols": successful})
    print(f"Completed BCTC: {len(successful)}/{len(target_symbols)} symbols saved to MongoDB.")

if __name__ == "__main__":
    main()
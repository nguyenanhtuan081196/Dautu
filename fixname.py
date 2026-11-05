import json

DATA_FILE = "data.json"

# Từ điển tên công ty của bạn
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

try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        stock_db = json.load(f)
    
    updated_count = 0
    for symbol, info in stock_db.items():
        if symbol in COMPANY_NAMES:
            info["company_name"] = COMPANY_NAMES[symbol]
            updated_count += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(stock_db, f, ensure_ascii=False, indent=4)
        
    print(f"✅ Đã cập nhật thành công tên doanh nghiệp cho {updated_count} mã trong {DATA_FILE}!")
except Exception as e:
    print(f"❌ Lỗi: {e}")

import os
import json
from datetime import datetime
from simulator import run_complex_backtest_simulation

OUTPUT_HTML = "index.html"
LAST_UPDATE_FILE = "last_update.json"


# ============================================================
# FIREBASE CONFIG — đọc từ 1 secret duy nhất FIREBASE_CONFIG
# ============================================================
def get_firebase_config():
    """Đọc toàn bộ Firebase config từ 1 secret JSON duy nhất (env FIREBASE_CONFIG)."""
    raw = os.environ.get("FIREBASE_CONFIG", "").strip()
    if not raw:
        print("⚠️ Thiếu secret FIREBASE_CONFIG — dùng config rỗng.")
        return {}

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ FIREBASE_CONFIG không phải JSON hợp lệ: {e}")
        return {}

    required = ["apiKey", "authDomain", "projectId", "appId"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"⚠️ FIREBASE_CONFIG thiếu key: {', '.join(missing)}")

    return config


def get_last_update_string():
    """Đọc mốc thời gian cào dữ liệu thực tế từ file last_update.json"""
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            with open(LAST_UPDATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "last_update" in data:
                    return data["last_update"]
        except Exception as e:
            print(f"⚠️ Lỗi đọc file last_update.json: {e}")
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def generate_html():
    # 1) Chạy mô phỏng (giữ nguyên logic simulator của bạn)
    sim_data = run_complex_backtest_simulation()
    print("📊 Đã tính toán xong lãi suất lịch sử cho các mã cổ phiếu.")

    # 2) Lấy mốc thời gian cập nhật
    last_update_str = get_last_update_string()
    print(f"🕒 Mốc thời gian cập nhật dữ liệu: {last_update_str}")

    # 3) Lấy firebase config từ secret (env)
    firebase_config = get_firebase_config()
    firebase_config_json = json.dumps(firebase_config, ensure_ascii=False)

    # 4) Template HTML (giữ nguyên như bản gốc, chỉ 2 placeholder)
    html_template = r"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Pro Quant Screener & Investment Simulator</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

    <!-- Firebase SDK -->
    <script src="https://www.gstatic.com/firebasejs/9.22.1/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/9.22.1/firebase-auth-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/9.22.1/firebase-firestore-compat.js"></script>

    <script src="./lightweight-charts.js"></script>

    <style>
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        .spinner { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        .glow-top1 { box-shadow: 0 0 15px rgba(234, 179, 8, 0.4); border-color: #eab308; }
        .glow-top2 { box-shadow: 0 0 10px rgba(148, 163, 184, 0.3); border-color: #94a3b8; }
        .glow-top3 { box-shadow: 0 0 10px rgba(180, 83, 9, 0.3); border-color: #b45309; }

        #chart-modal-box { max-height: 96dvh; }
        #chart-modal-box.fullscreen {
            position: fixed !important; top: 0 !important; left: 0 !important;
            width: 100vw !important; height: 100dvh !important;
            max-width: none !important; max-height: none !important;
            border-radius: 0 !important; z-index: 9999 !important;
        }
        #chart-modal-box:not(.fullscreen) #tv-chart-container {
            height: calc(96dvh - 50px) !important; min-height: 380px; width: 100% !important;
        }
        #chart-modal-box.fullscreen #tv-chart-container {
            height: calc(100dvh - 45px) !important; width: 100% !important;
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans pb-10">

    <!-- MÀN HÌNH ĐĂNG NHẬP / XÁC THỰC -->
    <div id="auth-overlay" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/95 backdrop-blur-md p-4">
        <div class="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl shadow-2xl p-6 relative">
            <div class="text-center mb-6">
                <div class="inline-block bg-emerald-600 text-white p-3 rounded-xl shadow-lg shadow-emerald-500/30 mb-2">
                    <i class="fa-solid fa-scale-balanced text-xl"></i>
                </div>
                <h2 class="text-xl font-black text-white">Pro Quant Screener</h2>
                <p class="text-xs text-slate-400 mt-1">Đăng nhập để sử dụng hệ thống lọc & phân tích AI</p>
            </div>

            <div class="flex border-b border-slate-800 mb-6">
                <button type="button" onclick="switchAuthTab('login')" id="tab-login-btn" class="flex-1 pb-2 text-xs font-bold text-emerald-400 border-b-2 border-emerald-500 transition">Đăng Nhập</button>
                <button type="button" onclick="switchAuthTab('register')" id="tab-register-btn" class="flex-1 pb-2 text-xs font-bold text-slate-400 hover:text-white transition">Đăng Ký Tài Khoản</button>
            </div>

            <form id="login-form" onsubmit="handleLogin(event)" class="space-y-4">
                <div>
                    <label class="block text-[11px] font-bold text-slate-400 uppercase mb-1">Email</label>
                    <input type="email" id="login-email" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500">
                </div>
                <div>
                    <label class="block text-[11px] font-bold text-slate-400 uppercase mb-1">Mật khẩu</label>
                    <input type="password" id="login-password" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500">
                </div>
                <div id="login-error" class="text-xs text-rose-400 hidden"></div>
                <button type="submit" class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition text-sm shadow-lg shadow-emerald-600/30">
                    Đăng Nhập Ngay
                </button>
            </form>

            <form id="register-form" onsubmit="handleRegister(event)" class="space-y-4 hidden">
                <div>
                    <label class="block text-[11px] font-bold text-slate-400 uppercase mb-1">Email đăng ký</label>
                    <input type="email" id="reg-email" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500">
                </div>
                <div>
                    <label class="block text-[11px] font-bold text-slate-400 uppercase mb-1">Mật khẩu (ít nhất 6 ký tự)</label>
                    <input type="password" id="reg-password" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500">
                </div>
                <div id="register-error" class="text-xs text-rose-400 hidden"></div>
                <button type="submit" class="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-lg transition text-sm shadow-lg shadow-indigo-600/30">
                    Đăng Ký Trải Nghiệm
                </button>
            </form>
        </div>
    </div>

    <!-- MODAL THÔNG BÁO HẾT HẠN -->
    <div id="expired-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-md hidden p-4">
        <div class="bg-slate-900 border border-rose-500/40 w-full max-w-md rounded-2xl shadow-2xl p-6 text-center">
            <div class="inline-block bg-rose-500/10 text-rose-400 p-3 rounded-full mb-3 border border-rose-500/20">
                <i class="fa-solid fa-triangle-exclamation text-2xl"></i>
            </div>
            <h3 class="text-lg font-bold text-white mb-1">Tài Khoản Đã Hết Hạn Dùng Thử</h3>
            <p class="text-xs text-slate-400 mb-6">Thời gian sử dụng dịch vụ của bạn đã kết thúc. Vui lòng liên hệ Admin để gia hạn.</p>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 text-left mb-4 text-xs space-y-1">
                <div><span class="text-slate-500">Mã tài khoản (UID):</span> <span id="user-uid-text" class="text-indigo-400 font-mono">--</span></div>
            </div>
            <button type="button" onclick="handleLogout()" class="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-semibold text-xs transition">
                Đăng Xuất
            </button>
        </div>
    </div>

    <!-- MODAL ADMIN PANEL -->
    <div id="admin-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm hidden p-4">
        <div class="bg-slate-900 border border-slate-700 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90dvh]">
            <div class="bg-slate-950 px-5 py-4 border-b border-slate-800 flex justify-between items-center">
                <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-user-shield text-amber-400"></i>
                    <h3 class="text-sm font-bold text-white">Quản Trị Hệ Thống (Admin Panel)</h3>
                </div>
                <button type="button" onclick="closeAdminModal()" class="text-slate-400 hover:text-white p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="p-5 overflow-y-auto space-y-4 flex-grow">
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead>
                          <tr class="border-b border-slate-800 text-slate-400 bg-slate-950">
                           <th class="p-3">Email</th>
                           <th class="p-3">Hạn sử dụng</th>
                           <th class="p-3">Quyền</th>
                          </tr>
                         </thead>
                        <tbody id="admin-users-list" class="divide-y divide-slate-800">
                            <tr><td colspan="3" class="p-4 text-center text-slate-500">Đang tải danh sách...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="bg-slate-950 px-5 py-3 border-t border-slate-800 text-right">
                <button type="button" onclick="closeAdminModal()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold">Đóng</button>
            </div>
        </div>
    </div>

    <!-- MODAL THÔNG TIN TÀI KHOẢN CÁ NHÂN -->
    <div id="account-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm hidden p-4">
        <div class="bg-slate-900 border border-slate-700 w-full max-w-md rounded-2xl shadow-2xl overflow-hidden flex flex-col">
            <div class="bg-slate-950 px-5 py-4 border-b border-slate-800 flex justify-between items-center">
                <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-user-gear text-emerald-400"></i>
                    <h3 class="text-sm font-bold text-white">Thông Tin Tài Khoản</h3>
                </div>
                <button type="button" onclick="closeAccountModal()" class="text-slate-400 hover:text-white p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="p-5 space-y-4 text-xs">
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
                    <div class="flex justify-between"><span class="text-slate-400">Email đăng nhập:</span> <span id="acc-modal-email" class="font-semibold text-white">--</span></div>
                    <div class="flex justify-between"><span class="text-slate-400">Loại tài khoản:</span> <span id="acc-modal-role" class="font-bold text-amber-400">--</span></div>
                    <div class="flex justify-between"><span class="text-slate-400">Thời hạn sử dụng:</span> <span id="acc-modal-expire" class="font-semibold text-emerald-400">--</span></div>
                    <div class="flex justify-between"><span class="text-slate-400">Mã UID:</span> <span id="acc-modal-uid" class="font-mono text-indigo-400">--</span></div>
                </div>
            </div>
            <div class="bg-slate-950 px-5 py-3 border-t border-slate-800 flex justify-between items-center">
                <button type="button" onclick="handleLogout()" class="px-4 py-2 bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 rounded-lg font-semibold transition flex items-center gap-1.5">
                    <i class="fa-solid fa-right-from-bracket"></i> Đăng Xuất
                </button>
                <button type="button" onclick="closeAccountModal()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-semibold">Đóng</button>
            </div>
        </div>
    </div>

    <!-- HEADER CHÍNH -->
    <header class="bg-slate-900 border-b border-slate-800 sticky top-0 z-30 shadow-md">
        <div class="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center gap-4">
            <div class="flex items-center space-x-3">
                <div class="bg-emerald-600 text-white p-2 rounded-lg shadow-lg shadow-emerald-500/30">
                    <i class="fa-solid fa-scale-balanced text-lg"></i>
                </div>
                <div>
                    <h1 class="text-base md:text-lg font-bold tracking-wide text-white">Pro Quant Screener</h1>
                    <p class="text-[10px] text-slate-400">Hệ thống chấm điểm đặc thù theo Nhóm ngành | <span class="text-emerald-400 font-semibold"><i class="fa-regular fa-clock mr-1"></i>Cập nhật giá: {last_update_str}</span></p>
                </div>
            </div>

            <div class="flex items-center gap-2">
                <button type="button" onclick="loadData(true)" class="px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-white rounded-lg text-xs font-semibold transition flex items-center gap-2">
                    <i class="fa-solid fa-rotate" id="refresh-icon"></i> <span class="hidden md:inline">Làm mới</span>
                </button>
                <button type="button" id="btn-admin-panel" onclick="openAdminModal()" class="px-3 py-2 bg-amber-600/20 border border-amber-500/40 text-amber-300 rounded-lg text-xs font-semibold transition hidden items-center gap-1.5">
                    <i class="fa-solid fa-user-shield"></i> <span class="hidden md:inline">Admin</span>
                </button>
                <button type="button" onclick="openAccountModal()" class="px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300 rounded-lg text-xs font-semibold transition flex items-center gap-1.5" title="Tài khoản cá nhân">
                    <i class="fa-solid fa-user-gear text-emerald-400"></i> <span class="hidden md:inline">Tài khoản</span>
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-2 md:px-4 py-4">
        <!-- Bộ lọc -->
        <div class="bg-slate-900 p-2 md:p-3 rounded-xl border border-slate-800 shadow-sm mb-4">
            <div class="grid grid-cols-3 gap-1.5 md:gap-3">
                <div class="relative w-full">
                    <span class="absolute inset-y-0 left-0 flex items-center pl-2 md:pl-3 text-slate-400">
                        <i class="fa-solid fa-magnifying-glass text-xs md:text-sm"></i>
                    </span>
                    <input type="text" id="search-input" placeholder="Tìm mã..."
                        class="w-full pl-7 md:pl-10 pr-7 md:pr-8 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs md:text-sm text-white focus:outline-none focus:border-emerald-500 transition">
                    <button type="button" onclick="clearInput('search-input')" class="absolute inset-y-0 right-0 flex items-center pr-2 md:pr-3 text-slate-400 hover:text-white transition" title="Xóa nhanh">
                        <i class="fa-solid fa-xmark text-xs"></i>
                    </button>
                </div>

                <div class="relative w-full">
                    <span class="absolute inset-y-0 left-0 flex items-center pl-2 md:pl-3 text-slate-400">
                        <i class="fa-solid fa-filter text-xs md:text-sm"></i>
                    </span>
                    <select id="sector-filter" class="w-full pl-7 md:pl-10 pr-5 md:pr-8 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs md:text-sm text-white focus:outline-none focus:border-emerald-500 appearance-none transition truncate">
                        <option value="ALL">Tất cả ngành</option>
                        <option value="NGAN_HANG">Ngân hàng</option>
                        <option value="CHUNG_KHOAN">Chứng khoán</option>
                        <option value="BAT_DONG_SAN">Bất động sản</option>
                        <option value="CONG_NGHE_BAN_LE">Công nghệ & Bán lẻ</option>
                        <option value="DIEN_NUOC_HA_TANG">Điện, Nước & Hạ tầng</option>
                        <option value="NGUYEN_VAT_LIEU_CHU_KY">Vật liệu & Chu kỳ</option>
                        <option value="SAN_XUAT_TIEU_DUNG_PHONG_THU">Sản xuất & Tiêu dùng</option>
                    </select>
                    <span class="absolute inset-y-0 right-0 flex items-center pr-2 md:pr-3 text-slate-400 pointer-events-none">
                        <i class="fa-solid fa-chevron-down text-[10px]"></i>
                    </span>
                </div>

                <div class="relative w-full">
                    <span class="absolute inset-y-0 left-0 flex items-center pl-2 md:pl-3 text-amber-400">
                        <i class="fa-solid fa-trophy text-xs md:text-sm"></i>
                    </span>
                    <select id="ranking-filter" class="w-full pl-7 md:pl-10 pr-5 md:pr-8 py-2 bg-slate-950 border border-amber-500/50 rounded-lg text-xs md:text-sm text-amber-300 font-semibold focus:outline-none focus:border-amber-400 appearance-none transition truncate">
                        <option value="NONE">Mặc định (A-Z)</option>
                        <option value="ALL_SCORE">🏆 Sắp xếp Tổng hợp</option>
                        <option value="FUNDAMENTAL" selected>💰 Sắp xếp Cơ bản</option>
                        <option value="TECHNICAL">📈 Sắp xếp Kỹ thuật</option>
                    </select>
                    <span class="absolute inset-y-0 right-0 flex items-center pr-2 md:pr-3 text-amber-400 pointer-events-none">
                        <i class="fa-solid fa-chevron-down text-[10px]"></i>
                    </span>
                </div>
            </div>
        </div>

        <div id="stock-container" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4">
            <div class="col-span-full text-center py-12 text-slate-500">
                <i class="fa-solid fa-spinner spinner text-2xl text-emerald-500 mb-3 block"></i>
                <p>Đang tải dữ liệu...</p>
            </div>
        </div>
    </main>

    <!-- MODAL CHI TIẾT AI & GIẢ LẬP ĐẦU TƯ TỪNG MÃ -->
    <div id="ai-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm hidden p-3 md:p-4">
        <div class="bg-slate-900 border border-slate-700 w-full max-w-3xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90dvh]">
            <div class="bg-slate-950 px-4 py-3 border-b border-slate-800 flex justify-between items-center sticky top-0 z-10 gap-2">
                <div class="flex items-center space-x-1.5 md:space-x-2">
                    <button type="button" onclick="navigateModalSymbol(-1)" class="text-slate-400 hover:text-white px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition" title="Mã trước">
                        <i class="fa-solid fa-chevron-left text-xs"></i>
                    </button>

                    <div class="relative flex items-center">
                        <input type="text" id="modal-symbol-input" value="--" onchange="handleDirectSymbolInput(this.value)" class="w-20 md:w-24 text-center text-base md:text-lg font-black text-indigo-400 bg-indigo-500/10 px-2 py-1 pr-6 rounded-lg border border-indigo-500/20 uppercase focus:outline-none focus:border-emerald-500" title="Nhập mã khác và nhấn Enter">
                        <button type="button" onclick="clearInput('modal-symbol-input')" class="absolute right-1 text-slate-400 hover:text-white text-xs transition" title="Xóa nhanh">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </div>

                    <button type="button" onclick="navigateModalSymbol(1)" class="text-slate-400 hover:text-white px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition" title="Mã tiếp theo">
                        <i class="fa-solid fa-chevron-right text-xs"></i>
                    </button>
                </div>

                <div class="flex items-center gap-2">
                    <div class="text-right">
                        <span id="modal-price" class="text-sm md:text-base font-black text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">--</span>
                        <p id="modal-sector" class="text-[9px] text-slate-400 mt-0.5 text-right">--</p>
                    </div>
                    <button type="button" onclick="closeModal()" class="text-slate-400 hover:text-white p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            </div>

            <!-- TABS -->
            <div class="flex border-b border-slate-800 bg-slate-900 px-5 pt-2 gap-3">
                <button type="button" onclick="switchAiTab('eval')" id="tab-btn-eval" class="px-4 py-2 text-xs font-bold text-emerald-400 border-b-2 border-emerald-500 transition">
                    <i class="fa-solid fa-robot mr-1.5"></i> Đánh Giá & Phân Tích AI
                </button>
                <button type="button" onclick="switchAiTab('simulator')" id="tab-btn-simulator" class="px-4 py-2 text-xs font-bold text-slate-400 hover:text-white transition">
                    <i class="fa-solid fa-calculator mr-1.5 text-emerald-400"></i> Giả Lập Tích Sản (DCA)
                </button>
            </div>

            <div class="p-5 overflow-y-auto space-y-4 flex-grow">
                <!-- KHUNG THÔNG TIN TÊN CÔNG TY -->
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs">
                    <span class="text-[10px] text-slate-400 block uppercase font-semibold">Tên doanh nghiệp</span>
                    <span id="modal-company-name" class="font-bold text-white text-sm">--</span>
                </div>

                <!-- KHUNG CHỈ SỐ CƠ BẢN -->
                <div class="grid grid-cols-3 md:grid-cols-6 gap-2 bg-slate-950/50 p-3 rounded-xl border border-slate-800 text-center">
                    <div><span class="text-[10px] text-slate-500 block">P/E</span><span id="modal-pe" class="text-sm font-bold text-slate-200">--</span></div>
                    <div><span class="text-[10px] text-slate-500 block">P/B</span><span id="modal-pb" class="text-sm font-bold text-slate-200">--</span></div>
                    <div><span class="text-[10px] text-slate-500 block">EPS</span><span id="modal-eps" class="text-sm font-bold text-slate-200">--</span></div>
                    <div><span class="text-[10px] text-slate-500 block">ROE</span><span id="modal-roe" class="text-sm font-bold text-blue-400">--</span></div>
                    <div><span class="text-[10px] text-slate-500 block">ROA</span><span id="modal-roa" class="text-sm font-bold text-indigo-400">--</span></div>
                    <div><span class="text-[10px] text-slate-500 block">Cổ tức</span><span id="modal-div" class="text-sm font-bold text-amber-400">--</span></div>
                </div>

                <!-- NÚT ẨN/HIỆN CHỈ SỐ CHUYÊN NGHIỆP -->
                <div>
                    <button type="button" onclick="toggleProMetrics()" id="btn-toggle-prometrics" class="w-full py-2 bg-slate-800 hover:bg-slate-700/80 border border-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition flex items-center justify-center gap-2 shadow-sm">
                        <i class="fa-solid fa-chart-pie text-emerald-400" id="prometrics-icon"></i>
                        <span id="prometrics-text">Hiển thị thêm chỉ số chuyên nghiệp (CFO, D/E, Biên gộp, TTM)</span>
                        <i class="fa-solid fa-chevron-down text-[10px] text-slate-400 ml-1 transition-transform duration-200" id="prometrics-chevron"></i>
                    </button>

                    <div id="pro-metrics-box" class="hidden mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 bg-slate-950/80 p-3 rounded-xl border border-emerald-500/30 text-center animate-fadeIn">
                        <div>
                            <span class="text-[10px] text-slate-400 block" id="label-cfo" title="Dòng tiền hoạt động kinh doanh">Dòng tiền CFO</span>
                            <span id="modal-cfo" class="text-xs font-bold text-emerald-400">--</span>
                        </div>
                        <div>
                            <span class="text-[10px] text-slate-400 block" id="label-de" title="Nợ phải trả / Vốn chủ sở hữu">Đòn bẩy D/E</span>
                            <span id="modal-de" class="text-xs font-bold text-amber-400">--</span>
                        </div>
                        <div>
                            <span class="text-[10px] text-slate-400 block" id="label-gm" title="Biên lợi nhuận gộp">Biên gộp</span>
                            <span id="modal-gm" class="text-xs font-bold text-blue-400">--</span>
                        </div>
                        <div>
                            <span class="text-[10px] text-slate-400 block">LN TTM (4Q)</span>
                            <span id="modal-ttm" class="text-xs font-bold text-indigo-400">--</span>
                        </div>
                    </div>
                </div>

                <!-- TAB ĐÁNH GIÁ AI -->
                <div id="tab-content-eval" class="space-y-4">
                    <div id="modal-ai-rec-box" class="bg-indigo-500/10 border border-indigo-500/30 p-4 rounded-xl">
                        <h4 class="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-2"><i class="fa-solid fa-bullseye mr-1.5"></i> Khuyến nghị của AI</h4>
                        <p id="modal-ai-rec" class="text-lg font-black text-white mb-2"></p>
                        <div class="bg-slate-900/50 p-2.5 rounded border border-indigo-500/20">
                            <span class="text-[10px] text-slate-400 block mb-1">Chiến lược hành động:</span>
                            <p id="modal-ai-price" class="text-sm text-emerald-300 font-medium">--</p>
                        </div>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1"><i class="fa-solid fa-file-invoice-dollar text-emerald-500 mr-1.5"></i> Phân tích Sức khỏe Tài chính & BCTC [AI]</h4>
                        <p id="modal-bctc" class="text-sm bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 leading-relaxed">--</p>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1"><i class="fa-solid fa-chart-line text-blue-500 mr-1.5"></i> Định giá & Hành động giá [AI]</h4>
                        <p id="modal-outlook" class="text-sm bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 leading-relaxed">--</p>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1"><i class="fa-solid fa-globe text-amber-500 mr-1.5"></i> Vĩ mô & Sóng ngành [AI]</h4>
                        <p id="modal-macro" class="text-sm bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 leading-relaxed">--</p>
                    </div>
                </div>

                <!-- TAB GIẢ LẬP TÍCH SẢN DCA -->
                <div id="tab-content-simulator" class="space-y-4 hidden">
                    <div class="bg-emerald-500/10 border border-emerald-500/30 p-3 rounded-xl text-xs space-y-2">
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">Tỷ suất sinh lời lịch sử (CAGR 5 năm):</span>
                            <span id="sim-historical-rate-text" class="text-sm font-bold text-emerald-400">Đang tính toán...</span>
                        </div>
                        <div class="border-t border-emerald-500/20 pt-2 grid grid-cols-2 gap-2 text-[11px]">
                            <div class="bg-slate-950/60 p-2 rounded border border-slate-800">
                                <span class="text-slate-400 block">Quý đầu (Neo 5 năm trước):</span>
                                <span id="sim-start-quarter-info" class="font-bold text-indigo-300">--</span>
                            </div>
                            <div class="bg-slate-950/60 p-2 rounded border border-slate-800">
                                <span class="text-slate-400 block">Quý cuối (Hiện tại):</span>
                                <span id="sim-end-quarter-info" class="font-bold text-amber-300">--</span>
                            </div>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Vốn ban đầu (VNĐ)</label>
                            <input type="text" id="modal-sim-initial" value="20.000.000" oninput="formatCurrencyInput(this)" class="w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold text-xs focus:outline-none focus:border-emerald-500">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Tích sản hàng tháng (VNĐ)</label>
                            <input type="text" id="modal-sim-monthly" value="3.000.000" oninput="formatCurrencyInput(this)" class="w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold text-xs focus:outline-none focus:border-emerald-500">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Kỳ hạn đầu tư (Năm)</label>
                            <input type="number" id="modal-sim-years" value="3" min="1" max="50" step="1" class="w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold text-xs focus:outline-none focus:border-emerald-500">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Lợi nhuận áp dụng (%/năm)</label>
                            <input type="number" id="modal-sim-rate" value="15" step="0.1" class="w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-emerald-400 font-bold text-xs focus:outline-none focus:border-emerald-500">
                        </div>
                    </div>

                    <button type="button" onclick="calculateModalSimulation()" class="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold transition text-xs shadow">
                        Tính Toán Lợi Nhuận DCA
                    </button>

                    <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1.5 text-xs">
                        <div class="flex justify-between"><span class="text-slate-400">Tổng vốn gốc đầu tư:</span> <span id="modal-sim-principal" class="font-bold text-slate-200">--</span></div>
                        <div class="flex justify-between"><span class="text-slate-400">Lợi nhuận dự kiến:</span> <span id="modal-sim-profit" class="font-bold text-emerald-400">--</span></div>
                        <div class="border-t border-slate-800 pt-1.5 flex justify-between text-sm"><span class="text-slate-300 font-bold">Tổng tài sản tương lai:</span> <span id="modal-sim-total" class="font-black text-amber-400">--</span></div>
                    </div>
                </div>
            </div>

            <div class="bg-slate-950 px-5 py-3 border-t border-slate-800 flex justify-between items-center text-[10px] text-slate-500">
                <span id="modal-time">AI cập nhật: --</span>
                <button type="button" onclick="closeModal()" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition font-bold shadow">Đóng</button>
            </div>
        </div>
    </div>

    <!-- MODAL BIỂU ĐỒ -->
    <div id="chart-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm hidden p-1 md:p-3">
        <div id="chart-modal-box" class="bg-slate-900 border border-slate-700 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col transition-all duration-300">
            <div class="p-0 bg-slate-900 flex-grow relative overflow-hidden">
                <div id="chart-loading" class="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-20 text-emerald-400 text-xs hidden">
                    <i class="fa-solid fa-spinner spinner mr-2"></i> Đang tải dữ liệu biểu đồ...
                </div>

                <div id="chart-overlay-legend" class="absolute top-2 left-2 z-10 bg-slate-950/35 backdrop-blur-sm p-1.5 rounded-xl border border-slate-800/40 text-[10px] flex flex-wrap items-center gap-1.5 text-slate-300 shadow-lg max-w-[calc(100%-80px)]">
                    <button type="button" onclick="navigateSymbol(-1)" class="text-slate-400 hover:text-white px-1.5 py-0.5 rounded bg-slate-900/40 border border-slate-700/50 transition"><i class="fa-solid fa-chevron-left text-[9px]"></i></button>

                    <div class="relative">
                        <button type="button" onclick="toggleSymbolDropdown()" id="chart-modal-symbol" class="text-xs font-black text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 px-2 py-0.5 rounded-lg border border-emerald-500/20 transition flex items-center gap-1">
                            <span id="current-symbol-text">--</span> <i class="fa-solid fa-chevron-down text-[9px]"></i>
                        </button>
                        <div id="symbol-dropdown" class="absolute left-0 mt-1 w-48 bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-xl shadow-2xl hidden z-50 max-h-60 overflow-y-auto p-1.5">
                            <div class="relative mb-1">
                                <input type="text" id="dropdown-search" placeholder="Lọc mã..." oninput="filterDropdownSymbols(this.value)" class="w-full px-2.5 py-1.5 pr-6 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500">
                                <button type="button" onclick="clearInput('dropdown-search'); filterDropdownSymbols('')" class="absolute right-1.5 inset-y-0 text-slate-400 hover:text-white text-xs transition" title="Xóa nhanh">
                                    <i class="fa-solid fa-xmark"></i>
                                </button>
                            </div>
                            <div id="dropdown-symbol-list" class="space-y-0.5"></div>
                        </div>
                    </div>

                    <button type="button" onclick="navigateSymbol(1)" class="text-slate-400 hover:text-white px-1.5 py-0.5 rounded bg-slate-900/40 border border-slate-700/50 transition"><i class="fa-solid fa-chevron-right text-[9px]"></i></button>

                    <div class="flex items-center bg-slate-950/20 p-0.5 rounded-lg border border-slate-800/40 gap-0.5">
                        <button type="button" onclick="switchInterval('D1')" id="btn-d1" class="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition">D1</button>
                        <button type="button" onclick="switchInterval('W1')" id="btn-w1" class="px-1.5 py-0.5 text-[10px] font-bold rounded text-slate-400 hover:text-white transition">W1</button>
                        <button type="button" onclick="switchInterval('MN')" id="btn-mn" class="px-1.5 py-0.5 text-[10px] font-bold rounded text-slate-400 hover:text-white transition">MN</button>
                        <button type="button" onclick="toggleQuarterLines()" id="btn-ind-qlines" class="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition ml-1" title="Ẩn/Hiện đường giá quý"><i class="fa-solid fa-chart-line"></i></button>
                        <button type="button" onclick="toggleQuarterZone()" id="btn-ind-qzone" class="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition" title="Ẩn/Hiện hộp vùng giá quý"><i class="fa-solid fa-square"></i></button>
                    </div>

                    <div class="flex items-center bg-slate-950/20 p-0.5 rounded-lg border border-slate-800/40 gap-0.5">
                        <button type="button" onclick="toggleIndicator('VOLMA')" id="btn-ind-volma" class="px-1.5 py-0.5 text-[9px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition">VolMA</button>
                        <button type="button" onclick="toggleIndicator('MA20')" id="btn-ind-ma20" class="px-1.5 py-0.5 text-[9px] font-bold rounded bg-indigo-600 text-white transition">MA20</button>
                        <button type="button" onclick="toggleIndicator('MA50')" id="btn-ind-ma50" class="px-1.5 py-0.5 text-[9px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition">MA50</button>
                        <button type="button" onclick="toggleIndicator('RSI')" id="btn-ind-rsi" class="px-1.5 py-0.5 text-[9px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition">RSI</button>
                    </div>

                    <div class="flex items-center bg-slate-950/20 p-0.5 rounded-lg border border-slate-800/40 gap-0.5">
                        <button type="button" onclick="jumpToQuarter('start')" class="px-2 py-0.5 text-[10px] font-bold rounded bg-amber-600 text-white transition" title="Nhảy tới Quý đầu 5 năm trước">&lt;&lt;</button>
                        <button type="button" onclick="jumpToQuarter('end')" class="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition" title="Nhảy tới Quý cuối hiện tại">&gt;&gt;</button>
                    </div>

                    <div class="flex items-center gap-2 pl-1 border-l border-slate-800/40 text-[10px]">
                        <div><span class="text-slate-400">TG:</span> <span id="legend-time" class="font-bold text-white">--</span></div>
                        <div><span class="text-slate-400">Giá:</span> <span id="legend-close" class="font-bold">--</span></div>
                        <div><span id="legend-change" class="font-bold">--</span></div>
                        <div><span class="text-slate-400">KL:</span> <span id="legend-vol" class="font-bold text-amber-400">--</span></div>
                    </div>
                </div>

                <div class="absolute top-2 right-2 z-10 flex items-center gap-1.5 bg-slate-950/35 backdrop-blur-sm p-1 rounded-xl border border-slate-800/40 shadow-lg">
                    <button type="button" onclick="toggleFullscreen()" id="fullscreen-btn" class="text-slate-300 hover:text-white p-1.5 rounded-lg bg-slate-900/40 transition" title="Phóng to / Thu nhỏ"><i class="fa-solid fa-expand text-xs"></i></button>
                    <button type="button" onclick="closeChartModal()" class="text-slate-400 hover:text-rose-400 p-1.5 rounded-lg bg-slate-900/40 transition" title="Đóng"><i class="fa-solid fa-xmark text-xs"></i></button>
                </div>

                <div id="tv-chart-container" class="w-full h-full"></div>
            </div>

            <div class="bg-slate-950 px-3 py-2 border-t border-slate-800 flex justify-between items-center text-xs">
                <span class="text-slate-400"><i class="fa-regular fa-clock mr-1 text-emerald-400"></i> Giá cập nhật lần cuối: <strong class="text-white">{last_update_str}</strong></span>
                <div class="flex gap-2">
                    <button type="button" id="btn-view-ai" class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition font-semibold flex items-center gap-1.5">
                        <i class="fa-solid fa-robot"></i> Xem AI chi tiết
                    </button>
                    <button type="button" onclick="closeChartModal()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition font-semibold">Đóng</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 🔐 Firebase config được inject từ Python (đọc từ GitHub Secret FIREBASE_CONFIG)
        const firebaseConfig = {firebase_config_json_placeholder};

        if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
        }
        const auth = firebase.auth();
        const db = firebase.firestore();

        auth.onAuthStateChanged(async (user) => {
            const authOverlay = document.getElementById('auth-overlay');
            const expiredModal = document.getElementById('expired-modal');

            if (user) {
                try {
                    const emailKey = user.email.toLowerCase();
                    const userDocRef = db.collection('allowed_users').doc(emailKey);
                    const doc = await userDocRef.get();

                    let userData = {};
                    if (!doc.exists) {
                        const expireDate = new Date();
                        expireDate.setDate(expireDate.getDate() + 7);
                        userData = {
                            email: user.email,
                            role: 'user',
                            expiresAt: expireDate.toISOString()
                        };
                        await userDocRef.set(userData);
                    } else {
                        userData = doc.data();
                    }

                    const now = new Date();
                    const expireTime = parseDate(userData.expiresAt);

                    if (expireTime && now > expireTime && userData.role !== 'admin') {
                        authOverlay.classList.add('hidden');
                        expiredModal.classList.remove('hidden');
                        document.getElementById('user-uid-text').innerText = user.uid;
                        await auth.signOut();
                        return;
                    } else {
                        authOverlay.classList.add('hidden');
                        expiredModal.classList.add('hidden');
                    }

                    if (userData.role === 'admin') {
                        const adminBtn = document.getElementById('btn-admin-panel');
                        if (adminBtn) {
                            adminBtn.classList.remove('hidden');
                            adminBtn.classList.add('flex');
                        }
                    }
                } catch (err) {
                    console.warn("⚠️ Lỗi kiểm tra Firestore:", err);
                }

                loadData(true);

            } else {
                authOverlay.classList.remove('hidden');
                expiredModal.classList.add('hidden');
            }
        });

        function parseDate(val) {
            if (!val) return null;
            if (typeof val.toDate === 'function') return val.toDate();
            const d = new Date(val);
            return isNaN(d.getTime()) ? null : d;
        }

        function switchAuthTab(tab) {
            const loginForm = document.getElementById('login-form');
            const registerForm = document.getElementById('register-form');
            const loginBtn = document.getElementById('tab-login-btn');
            const registerBtn = document.getElementById('tab-register-btn');

            if (tab === 'login') {
                loginForm.classList.remove('hidden');
                registerForm.classList.add('hidden');
                loginBtn.className = "flex-1 pb-2 text-xs font-bold text-emerald-400 border-b-2 border-emerald-500 transition";
                registerBtn.className = "flex-1 pb-2 text-xs font-bold text-slate-400 hover:text-white transition";
            } else {
                loginForm.classList.add('hidden');
                registerForm.classList.remove('hidden');
                registerBtn.className = "flex-1 pb-2 text-xs font-bold text-indigo-400 border-b-2 border-emerald-500 transition";
                loginBtn.className = "flex-1 pb-2 text-xs font-bold text-slate-400 hover:text-white transition";
            }
        }

        async function handleLogin(e) {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const pass = document.getElementById('login-password').value;
            const errBox = document.getElementById('login-error');
            errBox.classList.add('hidden');
            try {
                await auth.signInWithEmailAndPassword(email, pass);
            } catch (err) {
                errBox.innerText = "Lỗi đăng nhập: " + err.message;
                errBox.classList.remove('hidden');
            }
        }

        async function handleRegister(e) {
            e.preventDefault();
            const email = document.getElementById('reg-email').value;
            const pass = document.getElementById('reg-password').value;
            const errBox = document.getElementById('register-error');
            errBox.classList.add('hidden');

            try {
                const cred = await auth.createUserWithEmailAndPassword(email, pass);
                const expireDate = new Date();
                expireDate.setDate(expireDate.getDate() + 7);
                await db.collection('allowed_users').doc(email.toLowerCase()).set({
                    email: email,
                    role: 'user',
                    expiresAt: expireDate.toISOString()
                });
                alert("Đăng ký thành công tài khoản trải nghiệm 7 ngày!");
            } catch (err) {
                errBox.innerText = "Lỗi đăng ký: " + err.message;
                errBox.classList.remove('hidden');
            }
        }

        async function handleLogout() {
            await auth.signOut();
            window.location.reload();
        }

        async function openAccountModal() {
            const user = auth.currentUser;
            if (!user) return;
            document.getElementById('account-modal').classList.remove('hidden');
            document.getElementById('acc-modal-email').innerText = user.email || '--';
            document.getElementById('acc-modal-uid').innerText = user.uid;
            document.getElementById('acc-modal-expire').innerText = 'Đang tải...';
            document.getElementById('acc-modal-role').innerText = 'Đang tải...';

            try {
                const doc = await db.collection('allowed_users').doc(user.email.toLowerCase()).get();
                if (doc.exists) {
                    const data = doc.data();
                    document.getElementById('acc-modal-role').innerText = (data.role || 'user').toUpperCase();
                    const expDate = parseDate(data.expiresAt);
                    document.getElementById('acc-modal-expire').innerText = expDate ? expDate.toLocaleDateString('vi-VN') : 'Vô thời hạn';
                } else {
                    document.getElementById('acc-modal-role').innerText = 'USER';
                    document.getElementById('acc-modal-expire').innerText = 'Chưa thiết lập';
                }
            } catch (err) {
                document.getElementById('acc-modal-expire').innerText = 'Không thể tải hạn dùng';
            }
        }

        function closeAccountModal() { document.getElementById('account-modal').classList.add('hidden'); }

        async function openAdminModal() {
            document.getElementById('admin-modal').classList.remove('hidden');
            const listEl = document.getElementById('admin-users-list');
            listEl.innerHTML = `<tr><td colspan="3" class="p-4 text-center text-slate-500"><i class="fa-solid fa-spinner spinner mr-2"></i>Đang tải danh sách...</td></tr>`;

            try {
                const snapshot = await db.collection('allowed_users').get();
                listEl.innerHTML = '';
                if (snapshot.empty) {
                    listEl.innerHTML = `<tr><td colspan="3" class="p-4 text-center text-slate-400">Chưa có người dùng nào.</td></tr>`;
                    return;
                }
                snapshot.forEach(doc => {
                    const data = doc.data();
                    const expDate = parseDate(data.expiresAt);
                    const tr = document.createElement('tr');
                    tr.className = "hover:bg-slate-800/50 transition";
                    tr.innerHTML = `
                        <td class="p-3 font-semibold text-white">${data.email || doc.id}</td>
                        <td class="p-3 text-slate-300">${expDate ? expDate.toLocaleDateString('vi-VN') : '—'}</td>
                        <td class="p-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${data.role === 'admin' ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-800 text-slate-300'}">${data.role || 'user'}</span></td>
                    `;
                    listEl.appendChild(tr);
                });
            } catch (err) {
                listEl.innerHTML = `<tr><td colspan="3" class="p-4 text-center text-rose-400">Không có quyền truy cập danh sách.</td></tr>`;
            }
        }

        function closeAdminModal() { document.getElementById('admin-modal').classList.add('hidden'); }

        let screenerResults = [];
        let symbolSimRates = {};
        let quarterlyMeanDetails = {};
        let currentSymbolHistory = null;
        let chartInstance = null;
        let candleSeriesInstance = null;
        let volumeSeriesInstance = null;
        let currentSymbol = null;
        let currentInterval = 'D1';
        let activeIndicators = { VOLMA: false, MA20: true, MA50: false, RSI: false, QLINES: true, QZONE: true };
        let currentActiveTab = 'eval';

        const SECTOR_NAMES = {
            "NGAN_HANG": "Ngân hàng",
            "CHUNG_KHOAN": "Chứng khoán",
            "BAT_DONG_SAN": "Bất động sản",
            "CONG_NGHE_BAN_LE": "Công nghệ & Bán lẻ",
            "DIEN_NUOC_HA_TANG": "Điện, Nước & Hạ tầng",
            "NGUYEN_VAT_LIEU_CHU_KY": "Vật liệu & Chu kỳ",
            "SAN_XUAT_TIEU_DUNG_PHONG_THU": "Sản xuất & Tiêu dùng",
            "KHAC": "Khác"
        };

        function formatNumber(num) {
            if (num === undefined || num === null || num === 0) return '—';
            let val = (num < 1000 && num > 0) ? num * 1000 : num;
            return Math.round(val).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
        }
        function formatPercent(num) {
            if (num === undefined || num === null) return '—';
            return num.toFixed(1) + '%';
        }

        function formatMarketCap(val) {
            if (!val || val === 0) return '—';
            if (val >= 1e9) return (val / 1e9).toFixed(2) + ' Tỷ';
            if (val >= 1e6) return (val / 1e6).toFixed(2) + ' Tr';
            return formatNumber(val) + ' VNĐ';
        }

        function formatCurrencyInput(input) {
            let value = input.value.replace(/\D/g, "");
            if (value === "") {
                input.value = "";
                return;
            }
            input.value = Number(value).toLocaleString("vi-VN");
        }

        function parseCleanNumber(valStr) {
            if (!valStr) return 0;
            let clean = valStr.toString().replace(/\./g, "").replace(/,/g, "");
            return parseFloat(clean) || 0;
        }

        function clearInput(elementId) {
            const inputEl = document.getElementById(elementId);
            if (inputEl) {
                inputEl.value = '';
                inputEl.focus();
                if (elementId === 'search-input') renderCards();
            }
        }

        function toggleProMetrics() {
            const box = document.getElementById('pro-metrics-box');
            const textEl = document.getElementById('prometrics-text');
            const chevron = document.getElementById('prometrics-chevron');

            if (box.classList.contains('hidden')) {
                box.classList.remove('hidden');
                textEl.innerText = "Ẩn bớt chỉ số chuyên nghiệp";
                chevron.style.transform = "rotate(180deg)";
            } else {
                box.classList.add('hidden');
                textEl.innerText = "Hiển thị thêm chỉ số chuyên nghiệp (CFO, D/E, Biên gộp, TTM)";
                chevron.style.transform = "rotate(0deg)";
            }
        }

        async function loadData(showSpinner = false) {
            const icon = document.getElementById('refresh-icon');
            if (showSpinner && icon) icon.classList.add('spinner');
            try {
                const [screenerRes, ratesRes, detailsRes] = await Promise.all([
                    fetch('screener_results.json?t=' + new Date().getTime()),
                    fetch('symbol_sim_rates.json?t=' + new Date().getTime()).catch(() => ({ ok: false })),
                    fetch('quarterly_mean_details.json?t=' + new Date().getTime()).catch(() => ({ ok: false }))
                ]);

                if (!screenerRes.ok) throw new Error('Không thể tải screener_results.json');
                let screenerData = await screenerRes.json();
                if (ratesRes.ok) symbolSimRates = await ratesRes.json();
                if (detailsRes.ok) quarterlyMeanDetails = await detailsRes.json();

                let rawStockData = {};
                try {
                    const dataRes = await fetch('data.json?t=' + new Date().getTime());
                    if (dataRes.ok) rawStockData = await dataRes.json();
                } catch (e) {}

                screenerResults = screenerData.map(item => {
                    const sym = item.symbol;
                    const extraData = rawStockData[sym] || {};
                    return {
                        ...item,
                        company_name: extraData.company_name !== undefined ? extraData.company_name : (item.company_name || extraData.organ_name || item.organ_name || ""),
                        market_cap: extraData.market_cap !== undefined ? extraData.market_cap : (item.market_cap || 0),
                        total_shares: extraData.total_shares !== undefined ? extraData.total_shares : (item.total_shares || 0),
                        eps: extraData.eps !== undefined ? extraData.eps : item.eps,
                        dividend_yield: extraData.dividend_yield !== undefined ? extraData.dividend_yield : item.dividend_yield,
                        pe: extraData.pe !== undefined ? extraData.pe : item.pe,
                        pb: extraData.pb !== undefined ? extraData.pb : item.pb,
                        roe: extraData.roe !== undefined ? extraData.roe : item.roe,
                        roa: extraData.roa !== undefined ? extraData.roa : item.roa,
                        cfo_latest: extraData.cfo_latest !== undefined ? extraData.cfo_latest : (item.cfo_latest || 0),
                        debt_to_equity: extraData.debt_to_equity !== undefined ? extraData.debt_to_equity : (item.debt_to_equity || 0),
                        gross_margin: extraData.gross_margin !== undefined ? extraData.gross_margin : (item.gross_margin || 0),
                        net_profit_ttm: extraData.net_profit_ttm !== undefined ? extraData.net_profit_ttm : (item.net_profit_ttm || 0),
                        close_price: extraData.close !== undefined ? extraData.close : item.close_price,

                        bctc: extraData.bctc_evaluation || extraData.bctc || item.bctc_evaluation || item.bctc || "",
                        bctc_evaluation: extraData.bctc_evaluation || extraData.bctc || item.bctc_evaluation || item.bctc || "",
                        outlook: extraData.outlook !== undefined ? extraData.outlook : item.outlook,
                        ai_recommendation: extraData.ai_recommendation !== undefined ? extraData.ai_recommendation : item.ai_recommendation,
                        ai_price_zone: extraData.ai_price_zone !== undefined ? extraData.ai_price_zone : item.ai_price_zone,
                        macro_view: extraData.macro_view !== undefined ? extraData.macro_view : item.macro_view,
                        ai_updated_at: extraData.ai_updated_at !== undefined ? extraData.ai_updated_at : item.ai_updated_at
                    };
                });
                renderCards();
            } catch (error) {
                const container = document.getElementById('stock-container');
                if (container && showSpinner) {
                    container.innerHTML = `<div class="col-span-full text-center py-8 text-rose-400 font-semibold bg-rose-500/10 rounded-xl border border-rose-500/30">⚠️ Chưa có file screener_results.json hoặc data.json!</div>`;
                }
            } finally {
                if (showSpinner && icon) icon.classList.remove('spinner');
            }
        }

        function renderCards() {
            const container = document.getElementById('stock-container');
            if (!container) return;

            const searchTerm = document.getElementById('search-input').value.toUpperCase();
            const selectedSector = document.getElementById('sector-filter').value;
            const rankingMode = document.getElementById('ranking-filter').value;

            let filtered = screenerResults.filter(item => {
                let matchSearch = item.symbol.includes(searchTerm) || (item.company_name && item.company_name.toUpperCase().includes(searchTerm));
                let matchSector = (selectedSector === "ALL") ? true : (item.sector === selectedSector);
                return matchSearch && matchSector;
            });

            if (rankingMode === "FUNDAMENTAL" || rankingMode === "NONE") filtered.sort((a, b) => b.fundamental_score - a.fundamental_score);
            else if (rankingMode === "TECHNICAL") filtered.sort((a, b) => b.technical_score - a.technical_score);
            else if (rankingMode === "ALL_SCORE") filtered.sort((a, b) => b.total_score - a.total_score);
            else filtered.sort((a, b) => a.symbol.localeCompare(b.symbol));

            if (filtered.length === 0) {
                container.innerHTML = `<div class="col-span-full text-center py-8 text-slate-500">Không tìm thấy mã nào phù hợp.</div>`;
                return;
            }

            container.innerHTML = '';
            filtered.forEach((item, index) => {
                let statusColor = "text-slate-400 bg-slate-800";
                let borderColor = "border-slate-700";
                let displayRec = item.technical_status || "Tích lũy";
                if (displayRec.includes("MUA") || displayRec.includes("BREAKOUT") || displayRec.includes("GOM")) {
                    statusColor = "text-emerald-400 bg-emerald-500/10";
                    borderColor = "border-emerald-500/30";
                } else if (displayRec.includes("CHỜ") || displayRec.includes("TÍCH LŨY") || displayRec.includes("CẠN CUNG")) {
                    statusColor = "text-amber-400 bg-amber-500/10";
                    borderColor = "border-amber-500/30";
                }

                let topBadge = "";
                let cardGlow = "";
                if (rankingMode !== "NONE") {
                    if (index === 0) { topBadge = `<span class="absolute -top-3 -left-2 bg-yellow-500 text-black text-xs font-black px-2 py-1 rounded shadow">#1</span>`; cardGlow = "glow-top1"; }
                    else if (index === 1) { topBadge = `<span class="absolute -top-3 -left-2 bg-slate-300 text-black text-xs font-black px-2 py-1 rounded shadow">#2</span>`; cardGlow = "glow-top2"; }
                    else if (index === 2) { topBadge = `<span class="absolute -top-3 -left-2 bg-amber-700 text-white text-xs font-black px-2 py-1 rounded shadow">#3</span>`; cardGlow = "glow-top3"; }
                    else { topBadge = `<span class="absolute -top-3 -left-2 bg-indigo-600 text-white text-xs font-black px-2 py-1 rounded shadow">#${index + 1}</span>`; }
                }

                let scoreHtml = "";
                if (rankingMode !== "NONE") {
                    let label = "Điểm Tổng hợp";
                    let valScore = item.total_score;
                    if (rankingMode === "FUNDAMENTAL") { label = "Điểm Cơ bản"; valScore = item.fundamental_score; }
                    else if (rankingMode === "TECHNICAL") { label = "Điểm Kỹ thuật"; valScore = item.technical_score; }

                    scoreHtml = `<div class="text-[10px] text-center mb-1 bg-indigo-500/10 text-indigo-300 rounded py-1 border border-indigo-500/20">${label}: <strong>${valScore}/100</strong></div>`;
                }

                const card = document.createElement('div');
                card.className = `relative bg-slate-900 rounded-xl border ${borderColor} ${cardGlow} p-4 shadow-lg hover:bg-slate-800/80 transition w-full flex flex-col justify-between mt-2 cursor-pointer`;
                card.onclick = () => openChartModal(item.symbol);

                card.innerHTML = `
                    ${topBadge}
                    <div>
                        <div class="flex justify-between items-start mb-3">
                            <div class="flex flex-col">
                                <div class="flex items-center gap-2">
                                    <span class="text-xl font-black text-white">${item.symbol}</span>
                                    <button type="button" onclick="event.stopPropagation(); openModal('${item.symbol}')" class="text-indigo-400 bg-indigo-500/10 hover:bg-indigo-500/20 px-2 py-1 rounded-md border border-indigo-500/20 text-xs transition flex items-center gap-1" title="Xem chi tiết">
                                        <i class="fa-solid fa-robot"></i> <span class="hidden sm:inline">Quant [AI]</span>
                                    </button>
                                    <span class="text-[10px] px-2 py-1 rounded font-bold ${statusColor}">${displayRec}</span>
                                </div>
                                <div class="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
                                    <span><i class="fa-solid fa-tag mr-1"></i>${SECTOR_NAMES[item.sector] || item.sector}</span>
                                    ${item.company_name ? `<span class="text-slate-500">•</span> <span class="text-slate-300 font-medium truncate max-w-[180px] sm:max-w-[220px]" title="${item.company_name}">${item.company_name}</span>` : ''}
                                </div>
                            </div>
                            <div class="text-right">
                                <span class="block text-lg font-bold text-emerald-400">${formatNumber(item.close_price)}</span>
                                <span class="text-[10px] text-slate-500">Vốn hóa: ${formatMarketCap(item.market_cap)}</span>
                            </div>
                        </div>

                        <div class="grid grid-cols-4 gap-2 mb-2 bg-slate-950/50 p-2 rounded-lg border border-slate-800/50 text-center">
                            <div><span class="block text-[10px] text-slate-500 mb-0.5">P/E</span><span class="text-xs font-semibold text-slate-200">${item.pe > 0 ? item.pe.toFixed(1) : '—'}</span></div>
                            <div class="border-l border-slate-800"><span class="block text-[10px] text-slate-500 mb-0.5">P/B</span><span class="text-xs font-semibold text-slate-200">${item.pb > 0 ? item.pb.toFixed(1) : '—'}</span></div>
                            <div class="border-l border-slate-800"><span class="block text-[10px] text-slate-500 mb-0.5">ROE</span><span class="text-xs font-semibold text-blue-400">${formatPercent(item.roe)}</span></div>
                            <div class="border-l border-slate-800"><span class="block text-[10px] text-slate-500 mb-0.5">Điểm</span><span class="text-xs font-semibold text-amber-400">${item.total_score}đ</span></div>
                        </div>
                    </div>
                    ${scoreHtml}
                `;
                container.appendChild(card);
            });
        }

        function switchAiTab(tabName) {
            currentActiveTab = tabName;
            ['eval', 'simulator'].forEach(t => {
                const contentEl = document.getElementById(`tab-content-${t}`);
                const btnEl = document.getElementById(`tab-btn-${t}`);
                if (contentEl) contentEl.classList.add('hidden');
                if (btnEl) btnEl.className = "px-4 py-2 text-xs font-bold text-slate-400 hover:text-white transition";
            });

            const activeContent = document.getElementById(`tab-content-${tabName}`);
            const activeBtn = document.getElementById(`tab-btn-${tabName}`);
            if (activeContent) activeContent.classList.remove('hidden');
            if (activeBtn) activeBtn.className = "px-4 py-2 text-xs font-bold text-emerald-400 border-b-2 border-emerald-500 transition";

            if (tabName === 'simulator') {
                calculateModalSimulation();
            }
        }

        function openModal(symbol) {
            currentSymbol = symbol;
            const item = screenerResults.find(s => s.symbol === symbol);
            if (!item) return;

            switchAiTab(currentActiveTab);

            document.getElementById('modal-symbol-input').value = item.symbol;
            document.getElementById('modal-sector').innerText = `Ngành: ${SECTOR_NAMES[item.sector] || item.sector}`;
            document.getElementById('modal-price').innerText = formatNumber(item.close_price || item.close);

            document.getElementById('modal-company-name').innerText = item.company_name || '—';

            document.getElementById('modal-pe').innerText = item.pe > 0 ? item.pe.toFixed(1) : '—';
            document.getElementById('modal-pb').innerText = item.pb > 0 ? item.pb.toFixed(1) : '—';
            document.getElementById('modal-eps').innerText = item.eps ? formatNumber(item.eps) : '—';
            document.getElementById('modal-roe').innerText = item.roe ? formatPercent(item.roe) : '—';
            document.getElementById('modal-roa').innerText = item.roa ? formatPercent(item.roa) : '—';
            document.getElementById('modal-div').innerText = item.dividend_yield ? item.dividend_yield + '%' : '—';

            const isBankOrSec = (item.sector === "NGAN_HANG" || item.sector === "CHUNG_KHOAN");

            document.getElementById('modal-cfo').innerText = (item.cfo_latest !== undefined && item.cfo_latest !== null) ? item.cfo_latest + ' Tỷ' : '—';
            document.getElementById('modal-ttm').innerText = (item.net_profit_ttm !== undefined && item.net_profit_ttm !== null) ? item.net_profit_ttm + ' Tỷ' : '—';

            const deLabel = document.getElementById('label-de');
            const deVal = document.getElementById('modal-de');
            if (isBankOrSec) {
                deLabel.innerText = "Hệ số T.Sản/VCSH";
                deLabel.title = "Đòn bẩy đặc thù Ngân hàng/Chứng khoán";
                deVal.innerText = (item.debt_to_equity !== undefined && item.debt_to_equity !== null) ? item.debt_to_equity + 'x (Nợ/VCSH)' : '—';
            } else {
                deLabel.innerText = "Đòn bẩy D/E";
                deLabel.title = "Nợ phải trả / Vốn chủ sở hữu";
                deVal.innerText = (item.debt_to_equity !== undefined && item.debt_to_equity !== null) ? item.debt_to_equity : '—';
            }

            const gmLabel = document.getElementById('label-gm');
            const gmVal = document.getElementById('modal-gm');
            if (isBankOrSec) {
                gmLabel.innerText = "Đặc thù ngành";
                gmLabel.title = "Ngân hàng/Chứng khoán không tính biên gộp truyền thống";
                gmVal.innerText = "N/A (Ngành tài chính)";
            } else {
                gmLabel.innerText = "Biên gộp";
                gmLabel.title = "Biên lợi nhuận gộp";
                gmVal.innerText = (item.gross_margin !== undefined && item.gross_margin !== null) ? item.gross_margin + '%' : '—';
            }

            document.getElementById('modal-ai-rec').innerText = item.ai_recommendation || item.technical_status || 'Tích lũy';
            let priceZoneText = item.ai_price_zone;
            if (typeof priceZoneText === 'object' && priceZoneText !== null) {
                priceZoneText = priceZoneText.text || priceZoneText.detail || priceZoneText.strategy || JSON.stringify(priceZoneText);
            }
            document.getElementById('modal-ai-price').innerText = priceZoneText || item.potential_zone || '—';

            document.getElementById('modal-bctc').innerText = item.bctc_evaluation || item.bctc || "Chưa có đánh giá chi tiết về sức khỏe BCTC từ AI.";
            document.getElementById('modal-outlook').innerText = item.outlook || "Chưa có đánh giá triển vọng và định giá từ AI.";

            document.getElementById('modal-macro').innerText = item.macro_view || "Chưa có góc nhìn vĩ mô từ AI.";
            document.getElementById('modal-time').innerText = `AI cập nhật lúc: ${item.ai_updated_at || 'Hệ thống tự động'}`;

            let histRate = 15;
            if (symbolSimRates[symbol] && symbolSimRates[symbol].annual_rate_percent !== undefined) {
                histRate = symbolSimRates[symbol].annual_rate_percent;
                document.getElementById('sim-historical-rate-text').innerText = histRate + "% / năm (Quá khứ thực tế)";
            } else {
                document.getElementById('sim-historical-rate-text').innerText = "15% / năm (Mức chuẩn cơ sở)";
            }

            const details = quarterlyMeanDetails[symbol];
            if (details) {
                document.getElementById('sim-start-quarter-info').innerText = `${details.start_quarter}: ${details.start_price_mean.toLocaleString('vi-VN')} đ`;
                document.getElementById('sim-end-quarter-info').innerText = `${details.end_quarter}: ${details.end_price_mean.toLocaleString('vi-VN')} đ`;
            } else {
                document.getElementById('sim-start-quarter-info').innerText = "Không có dữ liệu";
                document.getElementById('sim-end-quarter-info').innerText = "Không có dữ liệu";
            }

            document.getElementById('modal-sim-rate').value = histRate;
            document.getElementById('modal-sim-initial').value = "20.000.000";
            document.getElementById('modal-sim-monthly').value = "3.000.000";
            document.getElementById('modal-sim-years').value = "3";

            document.getElementById('ai-modal').classList.remove('hidden');
        }

        function closeModal() { document.getElementById('ai-modal').classList.add('hidden'); }

        function navigateModalSymbol(direction) {
            const symbols = screenerResults.map(s => s.symbol).sort();
            const currentIndex = symbols.indexOf(currentSymbol);
            if (currentIndex !== -1) {
                let newIndex = currentIndex + direction;
                if (newIndex < 0) newIndex = symbols.length - 1;
                if (newIndex >= symbols.length) newIndex = 0;
                openModal(symbols[newIndex]);
            }
        }

        function handleDirectSymbolInput(val) {
            const cleanSymbol = val.trim().toUpperCase();
            const found = screenerResults.find(s => s.symbol === cleanSymbol);
            if (found) {
                openModal(cleanSymbol);
            } else {
                alert("Không tìm thấy mã cổ phiếu: " + cleanSymbol);
                document.getElementById('modal-symbol-input').value = currentSymbol;
            }
        }

        function calculateModalSimulation() {
            let p0 = parseCleanNumber(document.getElementById('modal-sim-initial').value);
            let pMonthly = parseCleanNumber(document.getElementById('modal-sim-monthly').value);
            let years = parseFloat(document.getElementById('modal-sim-years').value) || 1;
            let rate = (parseFloat(document.getElementById('modal-sim-rate').value) || 15) / 100;

            let totalPrincipal = p0 + (pMonthly * 12 * years);
            let futureVal = p0 * Math.pow(1 + rate, years);
            let monthlyRate = rate / 12;
            let totalMonths = years * 12;

            for (let i = 1; i <= totalMonths; i++) {
                futureVal += pMonthly * Math.pow(1 + monthlyRate, totalMonths - i + 1);
            }
            let profit = futureVal - totalPrincipal;

            document.getElementById('modal-sim-principal').innerText = Math.round(totalPrincipal).toLocaleString("vi-VN") + " VNĐ";
            document.getElementById('modal-sim-profit').innerText = "+" + Math.round(profit).toLocaleString("vi-VN") + " VNĐ";
            document.getElementById('modal-sim-total').innerText = Math.round(futureVal).toLocaleString("vi-VN") + " VNĐ";
        }

        function navigateSymbol(direction) {
            const symbols = screenerResults.map(s => s.symbol).sort();
            const currentIndex = symbols.indexOf(currentSymbol);
            if (currentIndex !== -1) {
                let newIndex = currentIndex + direction;
                if (newIndex < 0) newIndex = symbols.length - 1;
                if (newIndex >= symbols.length) newIndex = 0;
                openChartModal(symbols[newIndex]);
            }
        }

        function toggleSymbolDropdown() {
            const dropdown = document.getElementById('symbol-dropdown');
            dropdown.classList.toggle('hidden');
            if (!dropdown.classList.contains('hidden')) {
                document.getElementById('dropdown-search').value = '';
                renderDropdownSymbolList(screenerResults.map(s => s.symbol));
                document.getElementById('dropdown-search').focus();
            }
        }

        function renderDropdownSymbolList(symbols) {
            const listContainer = document.getElementById('dropdown-symbol-list');
            listContainer.innerHTML = '';
            symbols.sort().forEach(sym => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = `w-full text-left px-2 py-1 rounded-lg text-xs font-bold transition flex justify-between items-center ${sym === currentSymbol ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`;
                item.innerHTML = `<span>${sym}</span>`;
                item.onclick = (e) => {
                    e.stopPropagation();
                    document.getElementById('symbol-dropdown').classList.add('hidden');
                    openChartModal(sym);
                };
                listContainer.appendChild(item);
            });
        }

        function filterDropdownSymbols(keyword) {
            const upper = keyword.toUpperCase();
            const matched = screenerResults.map(s => s.symbol).filter(sym => sym.includes(upper));
            renderDropdownSymbolList(matched);
        }

        window.addEventListener('click', (e) => {
            const dropdown = document.getElementById('symbol-dropdown');
            const symbolBtn = document.getElementById('chart-modal-symbol');
            if (dropdown && !dropdown.contains(e.target) && !symbolBtn.contains(e.target)) {
                dropdown.classList.add('hidden');
            }
        });

        function switchInterval(interval) {
            currentInterval = interval;
            ['d1', 'w1', 'mn'].forEach(i => {
                const btn = document.getElementById(`btn-${i}`);
                if (btn) {
                    btn.className = i === interval.toLowerCase()
                        ? "px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition"
                        : "px-1.5 py-0.5 text-[10px] font-bold rounded text-slate-400 hover:text-white transition";
                }
            });
            if (currentSymbolHistory) renderChartInstance(currentSymbolHistory);
        }

        function toggleIndicator(name) {
            activeIndicators[name] = !activeIndicators[name];
            const btn = document.getElementById(`btn-ind-${name.toLowerCase()}`);
            if (btn) {
                btn.className = activeIndicators[name]
                    ? "px-1.5 py-0.5 text-[9px] font-bold rounded bg-indigo-600 text-white border border-indigo-400/50 transition"
                    : "px-1.5 py-0.5 text-[9px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition";
            }
            if (currentSymbolHistory) renderChartInstance(currentSymbolHistory);
        }

        function toggleQuarterLines() {
            activeIndicators.QLINES = !activeIndicators.QLINES;
            const btn = document.getElementById('btn-ind-qlines');
            if (btn) {
                btn.className = activeIndicators.QLINES
                    ? "px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition ml-1"
                    : "px-1.5 py-0.5 text-[10px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition ml-1";
            }
            if (currentSymbolHistory) renderChartInstance(currentSymbolHistory);
        }

        function toggleQuarterZone() {
            activeIndicators.QZONE = !activeIndicators.QZONE;
            const btn = document.getElementById('btn-ind-qzone');
            if (btn) {
                btn.className = activeIndicators.QZONE
                    ? "px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white transition"
                    : "px-1.5 py-0.5 text-[10px] font-bold rounded bg-slate-900/40 text-slate-400 hover:text-white transition";
            }
            if (currentSymbolHistory) renderChartInstance(currentSymbolHistory);
        }

        function jumpToQuarter(type) {
            const details = quarterlyMeanDetails[currentSymbol];
            if (!details || !currentSymbolHistory) return;

            let chartData = [];
            if (currentInterval === 'D1') chartData = currentSymbolHistory.history_d1 || [];
            else if (currentInterval === 'W1') chartData = currentSymbolHistory.history_w1 || [];
            else if (currentInterval === 'MN') chartData = currentSymbolHistory.history_mn || [];

            const quarterStr = (type === 'start') ? details.start_quarter : details.end_quarter;
            if (!quarterStr) return;

            const parts = quarterStr.split('Q');
            const year = parseInt(parts[0]);
            const q = parseInt(parts[1]);
            const startMonth = (q - 1) * 3 + 1;
            const endMonth = q * 3;

            let indices = [];
            let qMinPrice = Infinity;
            let qMaxPrice = -Infinity;

            chartData.forEach((bar, idx) => {
                const barDate = new Date(bar.time);
                if (barDate.getFullYear() === year &&
                    (barDate.getMonth() + 1) >= startMonth &&
                    (barDate.getMonth() + 1) <= endMonth) {
                    indices.push(idx);
                    if (bar.low < qMinPrice) qMinPrice = bar.low;
                    if (bar.high > qMaxPrice) qMaxPrice = bar.high;
                }
            });

            if (indices.length > 0 && chartInstance) {
                const minIdx = indices[0];
                const maxIdx = indices[indices.length - 1];

                chartInstance.priceScale('right').applyOptions({
                    autoScale: true,
                });

                const rangeSpan = Math.max(15, (maxIdx - minIdx) * 2);
                const from = Math.max(0, minIdx - Math.floor(rangeSpan / 2));
                const to = Math.min(chartData.length - 1, maxIdx + Math.floor(rangeSpan / 2));
                chartInstance.timeScale().setVisibleLogicalRange({ from, to });

                if (qMinPrice !== Infinity && qMaxPrice !== -Infinity) {
                    const pricePadding = (qMaxPrice - qMinPrice) * 0.5;
                    chartInstance.priceScale('right').setVisiblePriceRange({
                        from: qMinPrice - pricePadding,
                        to: qMaxPrice + pricePadding
                    });
                }
            } else {
                alert(`Không tìm thấy dữ liệu thời gian cho ${quarterStr} trong khung thời gian hiện tại!`);
            }
        }

        function resizeChart() {
            if (chartInstance) {
                const container = document.getElementById('tv-chart-container');
                if (container) chartInstance.applyOptions({ width: container.clientWidth, height: container.clientHeight });
            }
        }

        function toggleFullscreen() {
            const modalBox = document.getElementById('chart-modal-box');
            const fsBtnIcon = document.querySelector('#fullscreen-btn i');
            modalBox.classList.toggle('fullscreen');
            fsBtnIcon.className = modalBox.classList.contains('fullscreen') ? "fa-solid fa-compress text-xs" : "fa-solid fa-expand text-xs";
            setTimeout(resizeChart, 200);
        }

        window.addEventListener('resize', () => {
            if (!document.getElementById('chart-modal').classList.contains('hidden')) setTimeout(resizeChart, 300);
        });

        async function openChartModal(symbol) {
            currentSymbol = symbol;
            currentInterval = 'D1';
            switchInterval('D1');

            document.getElementById('current-symbol-text').innerText = symbol;
            document.getElementById('symbol-dropdown').classList.add('hidden');
            document.getElementById('btn-view-ai').onclick = () => { closeChartModal(); openModal(symbol); };

            document.getElementById('chart-modal').classList.remove('hidden');
            document.getElementById('chart-loading').classList.remove('hidden');

            try {
                const res = await fetch(`history/${symbol}.json?t=` + new Date().getTime());
                if (!res.ok) throw new Error();
                currentSymbolHistory = await res.json();
                renderChartInstance(currentSymbolHistory);
            } catch (err) {
                document.getElementById('tv-chart-container').innerHTML = `<div class="flex items-center justify-center h-full text-rose-400 text-xs">Chưa có dữ liệu lịch sử cho mã này!</div>`;
            } finally {
                document.getElementById('chart-loading').classList.add('hidden');
            }
        }

        function calculateMA(data, period) {
            let result = [];
            for (let i = 0; i < data.length; i++) {
                if (i < period - 1) continue;
                let sum = 0;
                for (let j = 0; j < period; j++) sum += data[i - j].close;
                result.push({ time: data[i].time, value: sum / period });
            }
            return result;
        }

        function calculateVolumeMA(data, period = 20) {
            let result = [];
            for (let i = 0; i < data.length; i++) {
                if (i < period - 1) continue;
                let sum = 0;
                for (let j = 0; j < period; j++) sum += data[i - j].volume;
                result.push({ time: data[i].time, value: sum / period });
            }
            return result;
        }

        function calculateRSI(data, period = 14) {
            let result = [];
            let gains = 0, losses = 0;
            for (let i = 1; i < data.length; i++) {
                let change = data[i].close - data[i - 1].close;
                if (i <= period) {
                    if (change >= 0) gains += change; else losses -= change;
                    if (i === period) {
                        let avgGain = gains / period, avgLoss = losses / period;
                        let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
                        result.push({ time: data[i].time, value: 100 - (100 / (1 + rs)) });
                    }
                } else {
                    gains = (gains * (period - 1) + (change >= 0 ? change : 0)) / period;
                    losses = (losses * (period - 1) + (change < 0 ? -change : 0)) / period;
                    let rs = losses === 0 ? 100 : gains / losses;
                    result.push({ time: data[i].time, value: 100 - (100 / (1 + rs)) });
                }
            }
            return result;
        }

        function renderChartInstance(historyDataObj) {
            const container = document.getElementById('tv-chart-container');
            container.innerHTML = '';
            const LC = window.LightweightCharts;
            if (!LC) return;

            const width = container.clientWidth || 600;
            const height = container.clientHeight || 380;
            const hasRSI = activeIndicators.RSI;

            chartInstance = LC.createChart(container, {
                width: width, height: height,
                layout: { background: { type: 'solid', color: '#0f172a' }, textColor: '#94a3b8' },
                grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
                timeScale: { borderColor: '#334155' }
            });

            candleSeriesInstance = chartInstance.addSeries(LC.CandlestickSeries, {
                upColor: '#10b981', downColor: '#f43f5e',
                borderUpColor: '#10b981', borderDownColor: '#f43f5e',
                wickUpColor: '#10b981', wickDownColor: '#f43f5e',
            }, 0);

            volumeSeriesInstance = chartInstance.addSeries(LC.HistogramSeries, {
                priceFormat: { type: 'volume' },
                priceScaleId: 'volumeScale'
            }, 0);

            chartInstance.priceScale('volumeScale').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

            let chartData = [];
            if (currentInterval === 'D1') chartData = historyDataObj.history_d1 || [];
            else if (currentInterval === 'W1') chartData = historyDataObj.history_w1 || [];
            else if (currentInterval === 'MN') chartData = historyDataObj.history_mn || [];

            if (chartData && chartData.length > 0) {
                candleSeriesInstance.setData(chartData);
                volumeSeriesInstance.setData(chartData.map(row => ({
                    time: row.time, value: row.volume,
                    color: row.close >= row.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(244, 63, 94, 0.5)'
                })));

                const details = quarterlyMeanDetails[currentSymbol];
                if (details) {
                    function getQuarterBoxInfo(quarterStr, allBars) {
                        if (!quarterStr) return null;
                        const parts = quarterStr.split('Q');
                        const year = parseInt(parts[0]);
                        const q = parseInt(parts[1]);

                        const startMonth = (q - 1) * 3 + 1;
                        const endMonth = q * 3;

                        const quarterBars = allBars.filter(bar => {
                            const barDate = new Date(bar.time);
                            return barDate.getFullYear() === year &&
                                   (barDate.getMonth() + 1) >= startMonth &&
                                   (barDate.getMonth() + 1) <= endMonth;
                        });

                        if (quarterBars.length === 0) return null;

                        let qHigh = -Infinity;
                        let qLow = Infinity;
                        quarterBars.forEach(b => {
                            if (b.high > qHigh) qHigh = b.high;
                            if (b.low < qLow) qLow = b.low;
                        });

                        return {
                            high: qHigh,
                            low: qLow,
                            data: quarterBars.map(row => ({
                                time: row.time,
                                value: qHigh,
                                baseValue: qLow
                            }))
                        };
                    }

                    if (activeIndicators.QZONE) {
                        const startBoxInfo = getQuarterBoxInfo(details.start_quarter, chartData);
                        if (startBoxInfo && startBoxInfo.data.length > 0) {
                            const startBoxSeries = chartInstance.addSeries(LC.BaselineSeries, {
                                baseValue: { type: 'price', price: startBoxInfo.low },
                                topFillColor1: 'rgba(59, 130, 246, 0.45)',
                                topFillColor2: 'rgba(59, 130, 246, 0.15)',
                                topLineColor: '#2563eb',
                                bottomLineColor: '#2563eb',
                                lineWidth: 2
                            }, 0);
                            startBoxSeries.setData(startBoxInfo.data);
                        }

                        const endBoxInfo = getQuarterBoxInfo(details.end_quarter, chartData);
                        if (endBoxInfo && endBoxInfo.data.length > 0) {
                            const endBoxSeries = chartInstance.addSeries(LC.BaselineSeries, {
                                baseValue: { type: 'price', price: endBoxInfo.low },
                                topFillColor1: 'rgba(16, 185, 129, 0.45)',
                                topFillColor2: 'rgba(16, 185, 129, 0.15)',
                                topLineColor: '#059669',
                                bottomLineColor: '#059669',
                                lineWidth: 2
                            }, 0);
                            endBoxSeries.setData(endBoxInfo.data);
                        }
                    }

                    if (activeIndicators.QLINES) {
                        candleSeriesInstance.createPriceLine({
                            price: details.start_price_mean,
                            color: '#f97316',
                            lineWidth: 2,
                            lineStyle: LC.LineStyle.Dashed,
                            axisLabelVisible: true,
                            title: `Q.Đầu 5Y (${details.start_quarter}): ${details.start_price_mean}`
                        });

                        candleSeriesInstance.createPriceLine({
                            price: details.end_price_mean,
                            color: '#10b981',
                            lineWidth: 2,
                            lineStyle: LC.LineStyle.Dotted,
                            axisLabelVisible: true,
                            title: `Q.Cuối (${details.end_quarter}): ${details.end_price_mean}`
                        });
                    }
                }

                if (activeIndicators.MA20) {
                    chartInstance.addSeries(LC.LineSeries, { color: '#3b82f6', lineWidth: 1 }, 0).setData(calculateMA(chartData, 20));
                }
                if (activeIndicators.MA50) {
                    chartInstance.addSeries(LC.LineSeries, { color: '#eab308', lineWidth: 1 }, 0).setData(calculateMA(chartData, 50));
                }
                if (activeIndicators.VOLMA) {
                    chartInstance.addSeries(LC.LineSeries, { color: '#f97316', lineWidth: 1, priceScaleId: 'volumeScale' }, 0).setData(calculateVolumeMA(chartData, 20));
                }
                if (hasRSI) {
                    const rsiSeries = chartInstance.addSeries(LC.LineSeries, { color: '#a855f7', lineWidth: 1.5 }, 1);
                    rsiSeries.createPriceLine({ price: 70, color: '#ef5350', lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true });
                    rsiSeries.createPriceLine({ price: 30, color: '#26a69a', lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true });
                    rsiSeries.setData(calculateRSI(chartData, 14));
                }

                const legendTime = document.getElementById('legend-time');
                const legendClose = document.getElementById('legend-close');
                const legendChange = document.getElementById('legend-change');
                const legendVol = document.getElementById('legend-vol');

                const latestBar = chartData[chartData.length - 1];
                if (latestBar) updateLegend(latestBar, chartData);

                function updateLegend(bar, dataArr) {
                    legendTime.innerText = bar.time;
                    legendClose.innerText = formatNumber(bar.close);
                    const index = dataArr.findIndex(item => item.time === bar.time);
                    let changePct = 0;
                    if (index > 0) changePct = ((bar.close - dataArr[index - 1].close) / dataArr[index - 1].close) * 100;

                    legendChange.innerText = `(${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)`;
                    legendChange.className = `font-bold ${changePct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
                    legendClose.className = `font-bold ${changePct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
                    legendVol.innerText = formatNumber(bar.volume);
                }

                chartInstance.subscribeCrosshairMove(param => {
                    if (!param.point || !param.time) { if (latestBar) updateLegend(latestBar, chartData); }
                    else {
                        const dataPoint = param.seriesData.get(candleSeriesInstance);
                        if (dataPoint) updateLegend({ time: param.time, close: dataPoint.close, volume: param.seriesData.get(volumeSeriesInstance)?.value || 0 }, chartData);
                    }
                });

                setTimeout(() => {
                    const totalBars = chartData.length;
                    let visibleBarsCount = width > 1200 ? 120 : (width > 768 ? 90 : 50);
                    if (totalBars > visibleBarsCount) chartInstance.timeScale().setVisibleLogicalRange({ from: totalBars - visibleBarsCount, to: totalBars - 1 });
                    else chartInstance.timeScale().fitContent();
                }, 50);
            }
        }

        function closeChartModal() {
            document.getElementById('chart-modal').classList.add('hidden');
            if (chartInstance) { chartInstance.remove(); chartInstance = null; }
            currentSymbolHistory = null;
        }

        document.getElementById('search-input').addEventListener('input', renderCards);
        document.getElementById('sector-filter').addEventListener('change', renderCards);
        document.getElementById('ranking-filter').addEventListener('change', renderCards);
    </script>
</body>
</html>
"""

    # 5) Inject config + thời gian vào template
    html_content = html_template.replace("{firebase_config_json_placeholder}", firebase_config_json)
    html_content = html_content.replace("{last_update_str}", last_update_str)

    # 6) Ghi file
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✅ Đã render thành công {OUTPUT_HTML} (cập nhật: {last_update_str})")


if __name__ == "__main__":
    generate_html()

# Investing
1-Step: Lấy BCTC: crawl_bctc.py⁠ (PC)
2-Step: Lấy dữ liệu giá: fetch_data_local.py (PC)
3-Step: Lọc & Sắp xếp: advanced_screener.py
4-Step: Đánh giá AI: analyze_ai.py
4.5Step: Tính lợi nhuận: simulator.py
5-Step: Build: render_ui.py

#AI
1. Chạy top đầu mỗi ngành (khoảng 35 mã, không chia batch):
python analyze_ai.py --mode top
 
2. Chạy phần còn lại, chia 5 batch — lần lượt:
python analyze_ai.py --mode rest --total-batches 5 --batch 1
python analyze_ai.py --mode rest --total-batches 5 --batch 2
python analyze_ai.py --mode rest --total-batches 5 --batch 3
python analyze_ai.py --mode rest --total-batches 5 --batch 4
python analyze_ai.py --mode rest --total-batches 5 --batch 5
 
3. Chạy tất cả một lần (top trước, rồi hết phần còn lại nếu chỉ 1 batch):
python analyze_ai.py --mode all --total-batches 1
 
4. Chạy theo danh sách nhập tay qua biến môi trường (như cũ):
INPUT_SYMBOLS="ACB,FPT,MWG" python analyze_ai.py

#Workflow
1. Nếu bạn muốn chạy phân tích lại 34 mã Top đầu (mỗi ngành 5 mã)
• symbols: Để trống.
• mode: Chọn top.
• batch: Để 1 (không quan trọng).
• total_batches: Để 1 (không quan trọng).
• force: Tích chọn (như trong ảnh của bạn) - để ép chạy lại các mã vừa mới phân tích, không bị bỏ qua bởi cơ chế resume 7 ngày.
👉 Bấm Run workflow. 
2. Nếu bạn muốn chạy phần còn lại (69 mã) - Chia làm 5 lần chạy
 
Giả sử bạn muốn chạy lần 1 (khoảng 13-14 mã):
• symbols: Để trống.
• mode: Chọn rest.
• batch: Nhập 1.
• total_batches: Nhập 5.
• force: Tích hoặc không tích đều được (nếu tích thì nó sẽ chạy lại cả những mã trong danh sách "còn lại" dù mới chạy, nếu không tích nó sẽ tự động bỏ qua các mã mới chạy trong 7 ngày qua).
👉 Bấm Run workflow.
(Lần sau muốn chạy tiếp, bạn làm lại và đổi batch thành 2, 3, 4, 5). 
3. Nếu bạn muốn chạy đồng thời cả Top và Phần còn lại trong 1 lần bấm
• symbols: Để trống.
• mode: Chọn all.
• batch: 1
• total_batches: 1 (hoặc 5 nếu muốn chia nhỏ phần còn lại).
• force: Tích chọn.
👉 Bấm Run workflow. 
4. Nếu bạn chỉ muốn chạy một vài mã cụ thể (ví dụ: ACB, FPT)
• symbols: Nhập ACB, FPT (không cần dấu ngoặc kép).
• mode: Chọn top (lúc này mode không có tác dụng vì đã có symbols).
• batch / total_batches: Để 1.
• force: Tích chọn.
👉 Bấm Run workflow. 


## Firestore Rules security tests

- Prerequisites: Node.js 20+ and Java 21+.
- Install the test dependencies with `npm install`.
- Run the Firestore Rules Emulator suite with `npm run test:rules`.
- The suite uses a disposable `demo-dautu` project ID and does not connect to production Firebase.
- The candidate rules are not deployed automatically by this test workflow.

## Development and quality checks

- Python dependencies are listed in `requirements.txt`; install them with `python -m pip install -r requirements.txt`.
- Run the test suite with `python -m unittest discover -s tests -v`.
- Generated Python bytecode, local virtual environments, and local environment files should not be committed.
- Historical CAGR in `simulator.py` is calculated from the quarterly mean prices without an arbitrary percentage cap. Invalid or non-positive prices are excluded rather than converted into misleading returns.

## MongoDB connection configuration

- Dautu uses its own MongoDB database, selected by `MONGODB_DATABASE` (defaults to `dautu`); do not reuse another project's database name or credentials.
- Configure `MONGODB_URI`, `MONGODB_SERVER_SELECTION_TIMEOUT_MS` and `MONGODB_CONNECT_TIMEOUT_MS` as separate environment variables.
- The URI validator accepts only `mongodb://` and `mongodb+srv://`, requires a host, removes empty query options, and defaults `retryWrites=true` only when not explicitly configured.
- MongoDB client creation remains lazy. The FastAPI lifespan closes the cached client at shutdown; no connection is created merely to close it.
- MongoDB indexes, collections, repositories and migration behavior remain Dautu-specific. Shared infrastructure changes are maintained separately in [server-platform](https://github.com/nguyenanhtuan081196/server-platform).

## Data-quality note

The screener now calculates CFO TTM and net-profit TTM over the same four consecutive quarter labels and leaves either value unavailable when a quarter is missing or ambiguous. The calculation assumes the provider's quarter-labelled cash-flow observations are standalone quarterly values; verify provider payload semantics and monitor restatements before treating the cash-conversion score as fully validated. See `FINANCIAL_METRICS.md` for definitions and limitations.

The root `login.html` is a legacy URL that redirects to the canonical `index.html` application. Use `index.html` as the only supported website entry point.


## Quản lý tài khoản trong Admin

- Đăng nhập bằng tài khoản quản trị đã xác minh email, sau đó mở **Admin** trên thanh đầu trang.
- Tìm tài khoản theo email hoặc lọc theo trạng thái: đang hoạt động, hết hạn/đã thu hồi, Admin.
- Chọn **Gia hạn** để nhập số ngày (1–3650). Hạn mới được lưu dưới dạng Firestore Timestamp để tương thích với Firestore Rules.
- Chọn **Thu hồi** để chặn quyền sử dụng ứng dụng của tài khoản thường. Hồ sơ Firestore được giữ lại và đặt hạn về quá khứ; không xóa người dùng khỏi Firebase Authentication. Tài khoản Admin được khóa thao tác trong giao diện.
- Xóa người dùng khỏi Firebase Authentication là thao tác riêng, cần backend tin cậy dùng Firebase Admin SDK; không thực hiện trực tiếp từ trình duyệt.


## Gửi email xác minh qua Gmail trên Render

Hệ thống gửi email xác minh qua Gmail SMTP từ API Render. Cách tạo Google App Password, cấu hình biến môi trường và kiểm tra sau triển khai được hướng dẫn tại `docs/RENDER_GMAIL_SETUP.md`.

## Shared server-platform dependency

Dautu uses the reusable [server-platform](https://github.com/nguyenanhtuan081196/server-platform) Python package. The repository is public, so CI, Render and local development install it over HTTPS without deploy keys, PATs, GitHub Apps or private-key secrets.

The dependency is pinned to immutable commit `b928015c10a332fa783e76e9160db2e9336d6085` in `requirements.txt`. Keep this pin unchanged unless deliberately upgrading the shared platform and validating the consuming application.

Install all dependencies with:

```bash
python -m pip install -r requirements.txt
```

Render uses the same dependency file in its build command; no platform-specific credentials or helper script are required.

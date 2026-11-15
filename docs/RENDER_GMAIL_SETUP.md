# Cấu hình gửi email xác minh qua Gmail SMTP trên Render

Website không gửi email trực tiếp từ trình duyệt. Firebase Authentication xác thực phiên; Render kiểm tra ID token và lấy email người nhận từ claim đã xác thực; Firebase Admin SDK tạo liên kết xác minh; Render gửi thư qua SMTP của Gmail.

Firebase vẫn quản lý tài khoản, mật khẩu và trạng thái email_verified. Gmail chỉ vận chuyển email; người nhận bấm liên kết Firebase để xác minh.

## 1. Tài khoản gửi thư

Hệ thống hiện sử dụng tài khoản gửi thư đã được chủ dự án cấu hình: `mimo.homeserver@gmail.com`. Thông tin xác thực SMTP được quản lý riêng tư và lưu trong Render Environment; tài liệu này không chứa hướng dẫn tạo hoặc quản lý App Password.

## 2. Cấu hình Render

Mở Render → service dautu-api → Environment. Thêm:

| Key | Value |
| --- | --- |
| GMAIL_SMTP_USER | mimo.homeserver@gmail.com |
| GMAIL_SMTP_APP_PASSWORD | App Password 16 ký tự (có thể nhập liền, không dấu cách) |
| GMAIL_FROM_NAME | Dautu |
| FRONTEND_URL | https://mimohouse.ddns.net |

Giữ nguyên FIREBASE_SERVICE_ACCOUNT_JSON, MONGODB_URI và MONGODB_DATABASE. SMTP dùng smtp.gmail.com, SSL port 465. Không cần cài thêm thư viện Python.

Sau khi cấu hình, lưu và để Render restart/redeploy service.

Bản triển khai hiện tại không sử dụng Resend. Sau khi xác nhận Gmail SMTP hoạt động, các biến cũ `RESEND_API_KEY` và `RESEND_FROM_EMAIL` không còn cần thiết và cần được xóa khỏi Render Environment.

## 3. Kiểm tra

1. Nếu cần kiểm tra nhanh biến cấu hình, mở `https://dautu-api.onrender.com/api/test-send-mail`. Endpoint chỉ báo các biến Gmail/Firebase có được khai báo hay không; endpoint không kết nối Gmail, không xác thực App Password và không gửi email.
2. Dùng tài khoản thử nghiệm do anh kiểm soát, đăng nhập và bấm Gửi lại email xác minh đúng một lần.
3. Mở Render Logs, tìm gmail_smtp_email_accepted hoặc gmail_smtp_delivery_failed.
4. Kiểm tra Inbox và Spam của địa chỉ nhận thư.
5. Mở liên kết xác minh, sau đó đăng nhập/tải lại trạng thái. Backend vẫn từ chối tài khoản chưa xác minh bằng HTTP 403.

Log gmail_smtp_email_accepted nghĩa là Gmail SMTP đã chấp nhận thư, không đảm bảo thư chắc chắn vào Inbox; cần kiểm tra hộp thư nhận.

## 4. Giới hạn gửi thư

Gmail áp dụng giới hạn gửi theo tài khoản và có thể lọc/chặn thư bất thường. Tài liệu Google nêu giới hạn SMTP tối đa 500 thư/ngày cho Gmail cá nhân và 2.000 thư/ngày cho Google Workspace trả phí; giới hạn có thể thay đổi theo chính sách tài khoản.

Bộ đếm MongoDB Atlas hiện có vẫn được giữ nguyên:
- Mỗi tài khoản: 1 lần thử/phút, tối đa 3 lần/giờ.
- Mỗi IP: 10 lần/phút, 30 lần/giờ.
- Request vượt giới hạn nhận HTTP 429 và Retry-After.
- MongoDB là nguồn lưu bộ đếm dùng chung qua restart.

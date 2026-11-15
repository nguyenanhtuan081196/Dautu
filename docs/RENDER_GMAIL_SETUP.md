# Cấu hình gửi email xác minh qua Gmail SMTP trên Render

Website không gửi email trực tiếp từ trình duyệt. Firebase Authentication xác thực phiên; Render kiểm tra ID token và lấy email người nhận từ claim đã xác thực; Firebase Admin SDK tạo liên kết xác minh; Render gửi thư qua SMTP của Gmail.

Firebase vẫn quản lý tài khoản, mật khẩu và trạng thái email_verified. Gmail chỉ vận chuyển email; người nhận bấm liên kết Firebase để xác minh.

## 1. Chuẩn bị tài khoản Gmail

Đặt GMAIL_SMTP_USER bằng địa chỉ Gmail anh đã cấu hình trên Render (hiện tại: mimo.homeserver@gmail.com). Nếu đổi tài khoản gửi, cập nhật biến này trong Render Environment.

1. Đăng nhập đúng tài khoản Gmail gửi thư.
2. Bật Xác minh 2 bước (2-Step Verification) trong Google Account.
3. Mở phần bảo mật tài khoản → App passwords.
4. Tạo App Password riêng, ví dụ tên Dautu Render.
5. Sao chép mật khẩu ứng dụng 16 ký tự.

App Password chỉ có khi tài khoản đủ điều kiện và đã bật 2-Step Verification. Một số tài khoản tổ chức, Advanced Protection hoặc cấu hình chỉ dùng security key có thể không được cấp App Password. Khi đó cần chuyển sang OAuth 2.0, không dùng mật khẩu tài khoản thường.

KHÔNG gửi App Password qua chat, không commit lên GitHub, không đặt trong mã nguồn. Chỉ lưu trong Render Environment. Nếu bị lộ, thu hồi App Password và tạo cái mới.

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

1. Mở endpoint chẩn đoán mail hiện tại. Kết quả chỉ báo có/thiếu biến cấu hình; endpoint không gửi email và không xác thực mật khẩu SMTP.
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

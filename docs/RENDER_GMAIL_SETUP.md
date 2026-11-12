# Gửi email xác minh qua Gmail bằng Render

Website không gửi email trực tiếp từ trình duyệt nữa. Luồng mới:

1. Người dùng đăng ký hoặc bấm **Gửi lại email xác minh**.
2. Firebase Authentication xác thực phiên đăng nhập và cấp ID token.
3. Trình duyệt gửi token đến `POST /api/auth/send-verification` trên Render.
4. Render dùng Firebase Admin SDK tạo liên kết xác minh cho đúng email trong token.
5. Render gửi email qua Gmail SMTP bằng Google App Password.

## Cấu hình Gmail

1. Dùng một Gmail riêng cho hệ thống (khuyến nghị), ví dụ `your-system@gmail.com`.
2. Bật Xác minh 2 bước cho tài khoản Google.
3. Tạo **App Password** cho ứng dụng gửi mail. Không dùng mật khẩu Gmail thông thường.
4. Không gửi App Password qua chat, GitHub, hoặc commit vào mã nguồn.

## Environment variables trên Render

Mở service `dautu-api` → Environment và thêm:

| Key | Value |
| --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Địa chỉ Gmail gửi thư |
| `SMTP_APP_PASSWORD` | Google App Password (16 ký tự; có thể nhập liền không dấu cách) |
| `SMTP_FROM_EMAIL` | Cùng địa chỉ Gmail ở `SMTP_USER` |
| `FRONTEND_URL` | `https://mimohouse.ddns.net` |

Giữ nguyên `FIREBASE_SERVICE_ACCOUNT_JSON` hiện có trên Render. Không đưa JSON tài khoản dịch vụ vào GitHub.

Sau khi lưu biến môi trường, Render cần khởi động lại service để nhận cấu hình.

## Firebase Console

Trong Firebase Console → Authentication → Settings → Authorized domains, bảo đảm có:

- `mimohouse.ddns.net`
- `dau-tu-65931.firebaseapp.com`

Firebase vẫn quản lý tài khoản, mật khẩu và trạng thái xác minh. Gmail SMTP chỉ chịu trách nhiệm vận chuyển email; không thay thế Firebase Authentication.

## Kiểm tra sau triển khai

1. Đăng ký bằng một email do anh kiểm soát.
2. Kiểm tra Inbox, Promotions và Spam.
3. Mở liên kết xác minh trong email.
4. Quay lại website, đăng nhập và tải lại trang.
5. Nếu chưa nhận được thư, xem Render Logs của service `dautu-api`; API chỉ trả thông báo cấu hình chung ra trình duyệt, không làm lộ thông tin SMTP.

## Giới hạn chống lạm dụng

Endpoint yêu cầu Firebase ID token hợp lệ, chỉ gửi đến email gắn với token (không nhận email tùy ý từ trình duyệt), và giới hạn tối đa 3 lần gửi mỗi email trong một giờ trên mỗi tiến trình Render. Khi tăng số instance, nên chuyển bộ đếm giới hạn sang kho dùng chung.

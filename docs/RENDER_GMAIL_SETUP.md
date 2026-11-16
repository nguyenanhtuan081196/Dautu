# Cấu hình Gmail API gửi email xác minh trên Render

Dautu dùng Firebase Authentication để quản lý tài khoản, mật khẩu và trạng thái `email_verified`. API trên Render tạo liên kết xác minh bằng Firebase Admin SDK, sau đó gửi email bằng Gmail API qua HTTPS. Người nhận bấm liên kết Firebase để xác minh; backend tiếp tục kiểm tra claim `email_verified` trước khi cho truy cập dữ liệu.

## Biến môi trường Render

Trong service `dautu-api` → Environment, cấu hình:

| Key | Mục đích |
| --- | --- |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `GOOGLE_REFRESH_TOKEN` | Refresh token được cấp với scope Gmail send |
| `GMAIL_SENDER_EMAIL` | `mimo.homeserver@gmail.com` |
| `GMAIL_FROM_NAME` | Tên hiển thị, mặc định `Dautu` |
| `FRONTEND_URL` | URL HTTPS của website được Firebase Authorized Domains cho phép |

Giữ nguyên `FIREBASE_SERVICE_ACCOUNT_JSON`, `MONGODB_URI` và `MONGODB_DATABASE`. Không đưa bất kỳ OAuth secret hoặc refresh token nào vào GitHub, frontend hay log.

Trong Google Cloud project sở hữu OAuth Client, cần bật **Gmail API**. Refresh token phải được cấp với scope `https://www.googleapis.com/auth/gmail.send` và phải thuộc chính hộp thư được khai báo ở `GMAIL_SENDER_EMAIL`.

## Cách gửi

1. Người dùng đăng ký hoặc đăng nhập bằng tài khoản Firebase chưa xác minh.
2. Frontend gửi ID token Firebase đến `POST /api/auth/send-verification`.
3. Backend lấy email từ claim đã xác thực; client không được tự chỉ định người nhận.
4. Firebase Admin SDK tạo email verification action link.
5. Gmail API dùng OAuth refresh token để lấy access token mới rồi gửi MIME email qua HTTPS.
6. Khi người dùng mở liên kết, Firebase cập nhật `email_verified`. API vẫn từ chối tài khoản có claim chưa xác minh.

Endpoint giới hạn gửi lại ở mức một yêu cầu mỗi tài khoản trong 60 giây trên mỗi tiến trình API. Đây là lớp chống gửi lặp cơ bản; nếu sau này chạy nhiều instance, cần chuyển bộ đếm sang MongoDB Atlas hoặc kho dùng chung.

## Kiểm tra sau deploy

1. Xác nhận Render Environment có đủ các biến ở trên; không chia sẻ giá trị secret.
2. Chờ Render deploy thành công và kiểm tra `/healthz`.
3. Đăng nhập bằng một tài khoản thử nghiệm chưa xác minh rồi bấm **Gửi lại email xác minh**.
4. Kiểm tra Inbox, Spam và Quảng cáo của email nhận.
5. Mở liên kết xác minh, đăng nhập lại và kiểm tra truy cập Dautu.

Log `verification_email_accepted provider=gmail_api` nghĩa là Gmail API đã chấp nhận request gửi thư, không đảm bảo thư chắc chắn nằm trong Inbox. Log lỗi chỉ ghi loại exception, không ghi token, nội dung email hoặc địa chỉ người nhận.

## Vận hành và giới hạn

Gmail áp dụng giới hạn gửi và chống lạm dụng theo tài khoản. Không dùng Gmail cá nhân để gửi email marketing hoặc gửi hàng loạt; luồng này chỉ dành cho email xác minh giao dịch của Dautu. Nếu lưu lượng đăng ký tăng đáng kể, nên chuyển sang nhà cung cấp email giao dịch chuyên dụng.

Dautu không sử dụng Gmail SMTP, App Password hoặc Resend. Các biến SMTP/Resend cũ nếu còn trong Render Environment không được ứng dụng này đọc và có thể được xóa sau khi xác nhận deploy mới hoạt động.

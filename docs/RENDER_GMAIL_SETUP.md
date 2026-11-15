# Gửi email xác minh qua Resend bằng Render

Website không gửi email trực tiếp từ trình duyệt. Luồng gửi thư:

1. Người dùng đăng ký hoặc bấm **Gửi lại email xác minh**.
2. Firebase Authentication cấp ID token cho phiên đăng nhập.
3. Render xác minh token và lấy email từ claim Firebase (không nhận địa chỉ email tùy ý từ trình duyệt).
4. Firebase Admin SDK tạo liên kết xác minh.
5. Render gửi email qua Resend API bằng khóa bí mật chỉ lưu trên Render.

## 1. Tạo tài khoản Resend

1. Mở [https://resend.com/signup](https://resend.com/signup) và đăng ký tài khoản.
2. Xác nhận email và đăng nhập.
3. Vào **Domains** → **Add Domain**.
4. Dùng domain hoặc subdomain anh kiểm soát, ví dụ `mail.tenmiencuaanh.com` (thay bằng tên miền thật).
5. Resend cung cấp các bản ghi DNS riêng cho domain, thường gồm SPF và DKIM.
6. Mở Cloudflare DNS (nếu DNS tên miền đang quản lý ở Cloudflare), thêm chính xác từng bản ghi Resend cung cấp. Không tự sửa giá trị/host.
7. Quay lại Resend bấm Verify và chờ trạng thái domain là **Verified**.

Nếu domain gốc đang dùng email ở Google Workspace hoặc nhà cung cấp khác, ưu tiên xác minh một subdomain gửi thư riêng và không thay đổi MX của domain gốc.

## 2. Tạo API Key

1. Trong Resend, mở **API Keys** → **Create API Key**.
2. Đặt tên, ví dụ `Dautu Render Production`.
3. Chọn quyền **Sending access** (đủ để gửi email) và giới hạn key vào domain đã xác minh nếu giao diện cho phép.
4. Tạo key và sao chép ngay. Key thường bắt đầu bằng `re_` và chỉ hiển thị đầy đủ một lần.

**Không gửi API Key qua chat, không commit lên GitHub, không đặt trong `api-config.js` hoặc mã JavaScript Frontend.** Nếu lộ key, thu hồi và tạo key mới.

## 3. Cấu hình Render

Mở Render → service `dautu-api` → **Environment**. Thêm:

| Key | Value |
| --- | --- |
| `RESEND_API_KEY` | API Key vừa tạo (bí mật) |
| `RESEND_FROM_EMAIL` | Ví dụ `Dautu <no-reply@mail.tenmiencuaanh.com>` — phải thuộc domain đã Verified |
| `FRONTEND_URL` | `https://mimohouse.ddns.net` |

Giữ nguyên `FIREBASE_SERVICE_ACCOUNT_JSON`, `MONGODB_URI` và `MONGODB_DATABASE` hiện có. Bản code mới chỉ đọc hai biến RESEND. Sau khi thêm biến, lưu và để Render restart/redeploy service.

## 4. Kiểm tra

1. Dùng tài khoản thử nghiệm do anh kiểm soát, đăng nhập và bấm **Gửi lại email xác minh**.
2. Mở Render Logs, tìm `resend_email_accepted` hoặc `verification_resend_delivery_failed`.
3. Trong Resend Dashboard → Emails, kiểm tra trạng thái email.
4. Kiểm tra Inbox, Spam; mở link xác minh rồi đăng nhập lại.
5. Tài khoản chưa xác minh vẫn bị Backend từ chối HTTP 403. Đổi nhà cung cấp email không thay đổi chính sách bảo mật.

Resend có thể cho thử gửi bằng `onboarding@resend.dev` trong sandbox, nhưng chỉ gửi đến địa chỉ email của chính tài khoản Resend. Để gửi đến người dùng thật, cần xác minh domain và dùng địa chỉ From trên đúng domain đó.

## 5. Giới hạn chống lạm dụng

Endpoint yêu cầu Firebase ID token hợp lệ và chỉ gửi đến email trong token. Bộ đếm MongoDB Atlas collection `email_rate_limits` vẫn được giữ nguyên:

- Mỗi tài khoản: 1 lần thử/phút, tối đa 3 lần/giờ.
- Mỗi IP: 10 lần/phút, 30 lần/giờ.
- Request vượt giới hạn nhận HTTP 429 và `Retry-After`.
- MongoDB là nguồn lưu bộ đếm dùng chung qua restart.

Firebase vẫn quản lý tài khoản, mật khẩu và trạng thái xác minh. Resend chỉ vận chuyển email; không thay thế Firebase Authentication.

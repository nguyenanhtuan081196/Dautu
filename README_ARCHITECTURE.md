# Dautu – Current System Architecture

Last reviewed: 2026-11-14

This document describes the production-oriented architecture after moving operational data and scheduled price collection to Render + MongoDB Atlas. It is an operational map, not a claim that every external dashboard setting has been independently verified.

## 1. System at a glance

```text
GitHub repository (source + CI + frontend)
        |                         |
        | Render auto-deploy      | GitHub Actions
        v                         | (CI / Pages / manual recovery)
Render: dautu-api                 |
FastAPI + Uvicorn                 |
- authenticated read API         |
- in-process price Scheduler     |
- bounded background batches     |
        |                         |
        v                         |
MongoDB Atlas / dautu <-----------+
operational source of truth
stocks, price_history, financial_reports,
screener_results, ai_analyses, simulations,
pipeline_runs, dataset_versions, app_metadata

Browser frontend (GitHub Pages static site)
        |
        +--> authenticated Render API --> MongoDB Atlas

UptimeRobot (external monitor) --> public Render /healthz
```

**Source of truth:** MongoDB Atlas is the durable operational data store. Render's filesystem and GitHub are not used as the live stock-data database.

## 2. Render API and deployment

- Render web service: `dautu-api`, FastAPI/Uvicorn, production origin `https://dautu-api.onrender.com`.
- Merged commits on `main` are deployed by Render Auto-Deploy; confirm each deployment reaches **Live** in Render.
- `GET /healthz` checks Atlas connectivity and returns HTTP 200 only when the database is reachable.
- The static frontend is deployed by `.github/workflows/pages.yml`; its API origin is configured by the `DAUTU_API_BASE_URL` Actions variable.
- Firebase Authentication provides browser sign-in. The API verifies Firebase ID tokens and checks membership in Firestore.

## 3. Render Free Scheduler and automatic Metadata

The price Scheduler is an **in-process asyncio task inside the FastAPI web service**, not a paid Render Cron Job or a separate worker.

- FastAPI startup creates the scheduler task when `PRICE_SCHEDULER_ENABLED` is true (default true); shutdown cancels it.
- It polls every 60 seconds by default (`PRICE_SCHEDULER_POLL_SECONDS`) and schedules Monday–Friday at `PRICE_SYNC_TIME`, default **20:30 Asia/Ho_Chi_Minh**.
- The crawler runs via `asyncio.to_thread`; it processes 5 symbols per batch by default and is capped at 10 (`PRICE_BATCH_SIZE`).
- Atlas `pipeline_runs` stores durable checkpoints and a 30-minute lease. Partial/failed runs are retried from confirmed saved symbols.
- **Metadata is Scheduler-owned.** After a complete successful crawl, the Scheduler calls `ensure_price_metadata` to publish `app_metadata/_id=price_sync` from the durable successful pipeline run.
- If the process stops after the crawl commits success but before Metadata is written, the next poll/restart detects the successful `pipeline_runs` record and repairs Metadata without rerunning the crawler.
- If a crawl is partial or fails, Metadata is not published for that attempt; the date remains eligible for recovery. Once recovery completes successfully, Metadata is published automatically.
- Metadata writes are idempotent: the same run is not rewritten; a newer timestamp is never replaced by an older recovery; an older Metadata record advances to the newer successful run.
- `.github/workflows/backfill-price-metadata.yml` remains available as a manual emergency fallback. It is not part of the normal daily data path.

### Render Free limitations

- The Scheduler runs only while the Render web process is alive. Free services may sleep or restart, so exact wall-clock execution is not guaranteed.
- On startup/wake, the scheduler recovers the latest due weekday from Atlas. UptimeRobot health pings can provide monitoring/wake-up traffic, but do not guarantee continuous process uptime or exact schedule execution.
- Keep the service at one instance unless a distributed scheduler/lock strategy is introduced; Atlas leases prevent duplicate claims for the same run.
- Memory use is constrained by the 512 MB Free instance: bounded batches, background threads and garbage collection are intentional.

## 4. MongoDB Atlas

Atlas database: `dautu`. Operational collections include:

- `stocks`, `price_history`, `financial_reports`
- `screener_results`, `ai_analyses`, `simulations`
- `pipeline_runs`, `dataset_versions`, `app_metadata`

The API reads live data from Atlas; Render's local filesystem is not the operational database.

## 5. UptimeRobot

UptimeRobot is configured outside this repository. Its intended role is to monitor the public `/healthz` endpoint. Dashboard URL, probe interval and current monitor status must be verified in the UptimeRobot account; this repository cannot prove those external settings. A health ping is not a guarantee that the in-process Scheduler remains awake at the scheduled minute.

## 6. GitHub Actions responsibilities

- `python-tests.yml`: Python tests, compile checks, Quant Screener smoke test and Firestore Rules Emulator.
- `render-production-smoke.yml`: post-CI production `/healthz` check.
- `pages.yml`: build and publish the static frontend.
- `mongodb-import.yml`: manual legacy JSON-to-Atlas migration (dry-run/apply with confirmation).
- `mongodb-verify.yml`: manual Atlas connectivity/collection verification.
- `backfill-price-metadata.yml`: manual emergency Metadata recovery only; normal daily publication is handled by Render Scheduler.

GitHub Actions does **not** run the regular daily price crawler.

## 7. Configuration names (never store secret values here)

- `MONGODB_URI`, `MONGODB_DATABASE` (normally `dautu`)
- `PRICE_SCHEDULER_ENABLED`, `PRICE_SCHEDULER_POLL_SECONDS`
- `PRICE_SYNC_TIME`, `PRICE_BATCH_SIZE`, `PRICE_SESSIONS`
- Firebase Admin service-account configuration (secret JSON or supported file configuration)

Never commit database URIs, Firebase private keys or other credentials.


## 8. Optional SSI FastConnect realtime market-data collector

### Trạng thái hiện tại: OFF

Tính năng Realtime đã có trong code nhưng **chưa được bật**. Giữ
`ENABLE_REALTIME_CRAWLER=false` trên Render (hoặc để trống; mặc định của code
là `false`). Không bật trước khi có credentials SSI, kiểm tra quyền Market
Data, hoàn tất smoke test và có xác nhận riêng của chủ dự án.

Kiến trúc được giữ tách biệt:

- Background collector trong `app/pipeline/realtime_collector.py` kết nối SSI
  FastConnect WebSocket và ghi snapshot mới nhất vào MongoDB Atlas
  (`realtime_prices`).
- API chỉ đọc MongoDB qua `/api/realtime` và `/api/realtime/{symbol}`;
  request của frontend không gọi SSI.
- Đây là luồng dữ liệu push, không phải REST polling. Collector hoạt động
  trong tiến trình Render API, không phải một worker độc lập.

### A. Đăng ký SSI FastConnect và tạo credentials

1. Cần có tài khoản chứng khoán SSI đang hoạt động.
2. Truy cập [SSI Developer Portal](https://developers.ssi.com.vn/) và tạo/
   đăng nhập tài khoản Developer theo hướng dẫn **Registration & Activation**.
3. Hoàn tất điều khoản đăng ký FastConnect. Chọn môi trường **Production**
   khi chuẩn bị chạy dữ liệu thật; UAT và Production có credentials tách biệt.
4. Tạo một API Key riêng cho Dautu. Chỉ cấp scope/quyền **Market Data /
   streaming dữ liệu thị trường** cần thiết. Không cấp Trading, đặt lệnh,
   tài khoản hoặc portfolio permissions.
5. Lưu lại đúng ba giá trị do Developer Portal cấp:
   - `Client ID` → `SSI_CLIENT_ID`
   - `API Key` → `SSI_API_KEY`
   - `API Secret` → `SSI_API_SECRET`
6. API Secret thường chỉ hiển thị khi tạo key. Lưu ngay vào nơi quản lý bí mật
   an toàn; không gửi qua chat, email thường, commit Git hoặc đưa vào file
   README. Nếu lộ, thu hồi/xoá key cũ và tạo key mới.

Tài liệu SSI chính thức:

- [Tổng quan FastConnect và điều kiện đăng ký](https://developers.ssi.com.vn/docs/getting-started/overview)
- [Quy trình đăng ký và kích hoạt](https://developers.ssi.com.vn/en/docs/getting-started/registration)\n- [Tạo và quản lý API Key](https://developers.ssi.com.vn/en/docs/getting-started/api-keys)\n- [Điều kiện sử dụng và môi trường UAT/Production](https://developers.ssi.com.vn/docs/getting-started/terms-and-environments)
- [Python SDK 3.3.2](https://developers.ssi.com.vn/en/docs/sdk/python/overview)
- [WebSocket Market Data](https://developers.ssi.com.vn/en/docs/tutorials/websocket-data)
- [Cấu hình SDK, reconnect và retry](https://developers.ssi.com.vn/en/docs/sdk/python/configuration)

> Lưu ý: Bộ key của tài liệu FastConnect/iBoard phiên bản cũ
> (`ConsumerID`, `ConsumerSecret`, `PrivateKey`) không đồng nhất với bộ
> credentials của SDK/API v3 đang được tích hợp ở đây. Không điền nhầm
> ConsumerID/PrivateKey vào ba biến `SSI_*` trên.

### B. Cấu hình biến môi trường trên Render

Sau khi có đủ credentials và đã xác nhận key có scope Market Data:

1. Mở Render Dashboard → service **dautu-api** → **Environment**.
2. Thêm ba biến dạng **Secret**:
   - `SSI_CLIENT_ID` = Client ID từ SSI Developer Portal
   - `SSI_API_KEY` = API Key
   - `SSI_API_SECRET` = API Secret
3. Có thể thêm các biến giới hạn tải (không bắt buộc):
   - `SSI_STREAM_BATCH_SIZE=25` (code giới hạn tối đa 50)
   - `REALTIME_MAX_SYMBOLS=100`
   - `REALTIME_QUEUE_MAXSIZE=2000`
   - `REALTIME_FLUSH_SECONDS=2`
4. **Giữ nguyên `ENABLE_REALTIME_CRAWLER=false`.** Lưu credentials không tự
   khởi chạy collector. Không đổi thành `true` cho đến khi có kế hoạch smoke
   test và được chủ dự án xác nhận.
5. Không đưa giá trị thật của credentials vào GitHub Actions Variables,
   README, source code hoặc log. Chỉ lưu tại Render Environment (Secret).
6. Sau này, khi đã được cho phép bật, đổi riêng
   `ENABLE_REALTIME_CRAWLER=true` rồi thực hiện deploy/restart có kiểm soát.
   Xác minh log kết nối, trạng thái subscription và dữ liệu mới trong
   `realtime_prices`; nếu có lỗi thì chuyển về `false` ngay.

### C. Kết nối lại khi mạng đứt / Render restart

- SSI Python SDK Stream có `auto_reconnect` mặc định bật. SDK thực hiện
  exponential backoff có jitter (mặc định bắt đầu 2 giây, tối đa 60 giây),
  lấy token mới khi cần và tự subscribe lại các topic sau khi reconnect.
- Collector đăng ký callback trạng thái kết nối để log các trạng thái
  `connected`, `disconnected`, `reconnected`, `failed`. Trạng thái
  `failed` được đẩy ra vòng điều phối để đóng session và thử khởi tạo lại.
- Nếu lần khởi tạo/auth/connect mới thất bại, vòng ngoài retry với backoff
  5 → 10 → 20 → 40 → 80 → tối đa 120 giây. Backoff chỉ reset sau khi kết nối
  WebSocket thành công, không reset trước mỗi lần thử.
- Khi Render restart/sleep, tiến trình và socket cũ mất. Khi service chạy lại,
  task được tạo lại từ startup và tự kết nối/auth/subscribe từ đầu; không thể
  phục hồi các tick đã bỏ lỡ trong thời gian service dừng.
- Render Free có thể sleep/restart và không bảo đảm WebSocket chạy liên tục.
  Vì vậy tính năng này là best-effort trên kiến trúc hiện tại, không phải
  feed realtime SLA. Muốn duy trì liên tục cần worker luôn bật hoặc nền tảng
  chạy nền phù hợp, kèm cơ chế leader lease trước khi mở rộng nhiều instance.

### D. Giới hạn dữ liệu và vận hành

- Collector chỉ chạy ngày thường trong phiên 09:00–11:30 và 13:00–15:00
  (Asia/Ho_Chi_Minh).
- Mỗi mã có một document mới nhất trong `realtime_prices`; queue có giới hạn
  và gộp tick theo mã để bảo vệ RAM 512 MB. Khi queue đầy, tick cũ nhất bị
  loại để ưu tiên snapshot mới.
- Đây không phải kho lưu toàn bộ tick. D1 cuối ngày hiện được tạo từ snapshot
  realtime gần nhất; cần kiểm chứng payload OHLC/volume thực tế của SSI trước
  khi coi đó là nguồn nến D1 chính thức. Không được dùng để ghi đè dữ liệu
  lịch sử chuẩn nếu chưa có quy tắc đối soát.
- Chỉ chạy một Render instance. Nhiều instance cần distributed lease/
  leader-election để tránh nhiều collector cùng subscribe và ghi dữ liệu.

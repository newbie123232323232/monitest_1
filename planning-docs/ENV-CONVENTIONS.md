# Quy ước URL & môi trường (dev / prod)

Áp dụng từ đầu khi code để dev và prod chỉ khác biến môi trường, không khác đường dẫn API.

## Phân vai

| Biến | Ý nghĩa |
|------|--------|
| `APP_BASE_URL` | Origin của **Vue SPA** (link trong email verify, redirect sau login). **Không** có `/` cuối. |
| `API_PUBLIC_URL` | Origin của **FastAPI** mà browser hoặc Google redirect tới. **Không** có `/` cuối. |

## Đường dẫn API (cố định mọi môi trường)

- Prefix REST: **`/api/v1`**
- OAuth Google (server-side): callback do **backend** nhận  
  **`GET {API_PUBLIC_URL}/api/v1/auth/google/callback`**

Mọi chỗ trong code (authorize URL, `redirect_uri` gửi Google, đăng ký Google Console) dùng **đúng một chuỗi** trùng `GOOGLE_OAUTH_REDIRECT_URI` trong `.env`.

## Development (mặc định khi code local)

| Thành phần | URL |
|------------|-----|
| SPA (Vite) | `http://localhost:5173` |
| API (uvicorn) | `http://localhost:8000` |
| Google OAuth redirect URI | `http://localhost:8000/api/v1/auth/google/callback` |

Trong `.env` dev:

```env
APP_BASE_URL=http://localhost:5173
API_PUBLIC_URL=http://localhost:8000
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

**Google Cloud Console → OAuth client (Web):**

- **Authorized JavaScript origins:** `http://localhost:5173`
- **Authorized redirect URIs:** `http://localhost:8000/api/v1/auth/google/callback`

## Production (VPS + HTTPS)

Đặt tên miền ví dụ (thay bằng miền thật của bạn):

| Thành phần | URL ví dụ |
|------------|-----------|
| SPA | `https://app.example.com` |
| API | `https://api.example.com` |

```env
APP_BASE_URL=https://app.example.com
API_PUBLIC_URL=https://api.example.com
GOOGLE_OAUTH_REDIRECT_URI=https://api.example.com/api/v1/auth/google/callback
```

**Google Console (cùng OAuth client hoặc client prod riêng):**

- **Authorized JavaScript origins:** `https://app.example.com`
- **Authorized redirect URIs:** `https://api.example.com/api/v1/auth/google/callback`

## Frontend gọi API

Đặt trong **`frontend/.env`** hoặc **`.env.development`** / **`.env.production`** (Vite chỉ đọc `VITE_*` từ thư mục frontend):

- **Dev (khuyến nghị):** `VITE_API_BASE_URL` **để trống** — `fetch('/api/v1/...')` cùng origin với Vite; **`vite.config.ts`** proxy `/api` → backend (mặc định `http://127.0.0.1:8010`). **Không cần CORS** giữa SPA và API.
- **Dev (gọi thẳng API):** `VITE_API_BASE_URL=http://127.0.0.1:8010` — backend dev phải bật CORS (hiện tại dev dùng `allow_origins=["*"]`).
- **Prod:** `VITE_API_BASE_URL=https://api.example.com` — không dùng proxy Vite trên server tĩnh.

Giữ **`/api/v1`** trong router FastAPI; URL đầy đủ: `(VITE_API_BASE_URL hoặc '') + "/api/v1/..."`.

## PostgreSQL (`DATABASE_URL`)

Dùng **một** Postgres cho toàn app (API + worker Celery cùng DB). Chuỗi kết nối cho **SQLAlchemy async + asyncpg**:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

### Bảng khớp pgAdmin ↔ `.env` (dev — tránh nhầm)

Dùng **cùng một bộ** giá trị cho pgAdmin và cho `DATABASE_URL` trong `.env`:

| Trường trong pgAdmin (Connect / Register Server) | Giá trị chốt (dev local) |
|--------------------------------------------------|-------------------------|
| **Server name** | `MONI local` (chỉ là nhãn trong pgAdmin, không nằm trong `.env`) |
| **Host name/address** | `localhost` |
| **Port** | `5432` |
| **Database** | `moni` |
| **User** | `moni` |
| **Password** | Trùng mật khẩu trong chuỗi `DATABASE_URL` (mặc định doc: `moni_local_dev` — đổi thì sửa cả Postgres và `.env`) |

Chuỗi tương ứng trong `.env`:

```env
DATABASE_URL=postgresql+asyncpg://moni:moni_local_dev@localhost:5432/moni
```

**Lần đầu tạo user/database** (psql hoặc Query Tool, chạy với quyền superuser):

```sql
CREATE USER moni WITH PASSWORD 'moni_local_dev';
CREATE DATABASE moni OWNER moni;
```

Nếu đổi mật khẩu: đổi trong Postgres **và** cập nhật `DATABASE_URL`; ký tự đặc biệt trong mật khẩu phải **URL-encode** trong URL.

| Phần | Dev local | Prod (Docker/VPS) |
|------|-----------|---------------------|
| `USER` / `DATABASE` | `moni` / `moni` (như bảng trên) | Tùy server; cùng nguyên tắc: `.env` = pgAdmin |
| `HOST` | `localhost` | Tên service Docker (`postgres`) hoặc `localhost` nếu bind port |
| `PORT` | `5432` | Thường `5432` |
| `PASSWORD` | Như đã tạo user | Biến môi trường an toàn |

**Không** dùng prefix `postgresql://` thuần nếu code cấu hình driver `asyncpg` — giữ đúng `postgresql+asyncpg://` như quy ước dự án.

**Postgres 15+ — `permission denied for schema public` (Alembic / migrate):** User thường phải được quyền trên `public`, chạy bằng superuser:

`GRANT ALL ON SCHEMA public TO moni;`  
(hoặc `ALTER DATABASE moni OWNER TO moni;` tùy cách bạn tạo DB.)

## Redis (`REDIS_URL`)

Redis dùng cho **Celery broker** + **result backend** (và có thể cache sau). Định dạng chuẩn:

```text
redis://[PASSWORD@]HOST:PORT/DBINDEX
```

Ví dụ dev không mật khẩu, database logic `0`:

```env
REDIS_URL=redis://localhost:6379/0
```

| Phần | Ý nghĩa |
|------|--------|
| `HOST` / `PORT` | Mặc định `6379`; trong Compose thường host là tên service `redis` |
| `DBINDEX` | `0`–`15`; `/0` đủ cho MVP (broker + result cùng instance; tách `/0` và `/1` là tùy chọn sau) |
| Có mật khẩu | `redis://:yourpassword@localhost:6379/0` (dấu `:` trước password) |

**Cách có dev nhanh:**

1. Cài Redis (Linux/WSL) hoặc image `redis:7-alpine` trong Docker; trên Windows có thể WSL2 + Redis hoặc chỉ Docker.
2. Kiểm tra: `redis-cli -u redis://localhost:6379/0 ping` → `PONG`.
3. Điền `REDIS_URL` như trên.

Prod: cùng format, `HOST` là hostname nội bộ VPS/Docker; bật `requirepass` thì nhét password vào URL như bảng trên.

**Redis Cloud (Redis Labs / GCP):** Dashboard cung cấp public endpoint + user (thường `default`) + password. Chuỗi dạng:

`redis://default:PASSWORD@HOST:PORT/0`

Nếu client bắt buộc TLS, thử `rediss://` cùng host/port (xem tài liệu subscription). `redis-cli -u "..." ping` là cách kiểm tra nhanh trước khi gắn vào Celery.

### Celery & Beat (biến môi trường)

| Biến | Vai trò |
|------|--------|
| `CELERY_BROKER_URL` | Hàng đợi task (thường **trùng** `REDIS_URL` dev). |
| `CELERY_RESULT_BACKEND` | Lưu kết quả / trạng thái task (thường **trùng** broker hoặc cùng host, DB Redis khác ví dụ `/1`). |

**Celery Beat** (lịch `crontab` / `beat_schedule`) **không có biến env riêng**: chạy process `celery -A <app> beat`, dùng **cùng** `CELERY_BROKER_URL` với worker. Chỉ cần đảm bảo worker + beat trỏ cùng app Celery và cùng Redis broker.

Khi code backend, có thể `CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")` để dev chỉ cần `REDIS_URL` nếu muốn gọn — hiện `.env` đã ghi đủ cả ba cho rõ ràng.

## CORS

Backend cho phép origin từ `APP_BASE_URL`. Ở **`APP_ENV=development`**, API thêm **`allow_origin_regex`** khớp `http://localhost:*` và `http://127.0.0.1:*` (mọi cổng) cùng với cặp origin từ `APP_BASE_URL` — tránh **`Failed to fetch`** do CORS khi đổi cổng Vite hoặc khi response lỗi (5xx) khiến trình duyệt báo thiếu header CORS.

Đăng ký: nếu SMTP lỗi, API trả **503** + `smtp_failed` (không còn 500 không rõ nguyên nhân).

Prod: không dùng regex dev; chỉ `APP_BASE_URL` (HTTPS) thật.

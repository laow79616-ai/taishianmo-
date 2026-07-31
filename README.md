# 泰美国际养生 · 预约系统 (taishianmo)

用户端预约 + 后台管理（FastAPI + 静态 HTML）

## 功能概览

- 服务商列表 / 详情（图文视频轮播、多项目价格、国家、可预约状态）
- 到店 / 上门预约（打车费、地图地址）
- 订单查询、后台仪表盘与订单管理
- 服务商在线咨询（详情页对话、未读角标、提示音）
- Telegram 新订单/咨询通知
- 图片视频上传

## 目录

```
backend/main.py      # API
frontend/            # 用户端 + 后台页面
static/uploads/      # 上传文件
```

## 本地运行

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

访问: http://127.0.0.1:8000/

后台: http://127.0.0.1:8000/admin-login.html  
默认账号见数据库 admins 表（当前多为 admin / taimei123）

## 生产部署

- Nginx 反代到 uvicorn 127.0.0.1:8000
- 域名示例: taimeili.pw
- 服务器项目路径示例: /www/thai-massage/

## GitHub

https://github.com/laow79616-ai/taishianmo-.git

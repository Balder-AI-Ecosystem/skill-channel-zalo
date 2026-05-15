# UPDATE PLAN — skill-channel-zalo

> Audit date: 2026-04-21 | Grade: **B** | Priority: Medium

---

## Vấn đề tìm thấy

### 1. Schemas chưa khai báo properties (CRITICAL)
`zalo_status` output và `zalo_webhook` input/output chưa có property definitions.  
Fields thực tế: `payload`, `provided_secret`, `state_dir`, `outputs_dir`.

### 2. `state_dir` / `outputs_dir` không document trong schema
Hai fields runtime này cần được khai báo để caller biết inject đúng.

### 3. Test coverage tối thiểu
Chỉ manifest existence check. Không test webhook parsing, secret validation, error paths.

---

## Fix cần làm

### Fix 1 — Cập nhật schemas trong skill.yaml

```yaml
# channel_gateway.zalo_status
input_schema:
  type: object
  additionalProperties: false
output_schema:
  type: object
  properties:
    status:
      type: string
      enum: [ok, error, degraded]
    gateway_name:
      type: string
    connected:
      type: boolean
    last_event_at:
      type: ["string", "null"]
  required: [status]

# channel_gateway.zalo_webhook
input_schema:
  type: object
  required: [payload]
  properties:
    payload:
      type: object
      description: "Raw Zalo OA webhook JSON"
    provided_secret:
      type: ["string", "null"]
      description: "Zalo webhook verification token"
    state_dir:
      type: string
      description: "Runtime state directory path (injected by core)"
    outputs_dir:
      type: string
      description: "Runtime outputs directory path (injected by core)"
  additionalProperties: false
output_schema:
  type: object
  properties:
    status:
      type: string
      enum: [ok, error, ignored]
    reply_sent:
      type: boolean
    detail:
      type: ["string", "null"]
  required: [status]
```

### Fix 2 — Thêm functional tests

```python
# tests/test_webhook.py
def test_health_endpoint_returns_200():
    from fastapi.testclient import TestClient
    from src.skill_channel_zalo_service.app import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200

def test_webhook_missing_payload_returns_error():
    from fastapi.testclient import TestClient
    from src.skill_channel_zalo_service.app import app
    client = TestClient(app)
    resp = client.post("/execute", json={
        "capability_id": "channel_gateway.zalo_webhook",
        "parameters": {}  # missing required payload
    })
    assert resp.status_code in (400, 422)

def test_zalo_status_returns_status_field():
    from fastapi.testclient import TestClient
    from src.skill_channel_zalo_service.app import app
    client = TestClient(app)
    resp = client.post("/execute", json={
        "capability_id": "channel_gateway.zalo_status",
        "parameters": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
```

---

## Không cần làm
- Không cần thay đổi ZaloChannelManager integration
- Service mode, port 8422 đúng rồi
- Pattern giống Telegram — có thể sync update cùng lúc

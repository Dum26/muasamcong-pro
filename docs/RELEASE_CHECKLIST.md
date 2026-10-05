# Checklist phát hành 5.3

- [x] Python unit/integration tests, `npm test`, React tests, CSS build, TypeScript, lint và syntax check local đều qua ngày 01/10/2026.
- [x] E2E trình duyệt: 15 tuyến, light/dark, 1280/1366/1440/1920px và mobile qua.
- [ ] Docker image build, startup production với schema đã migrate và `/ready` qua.
- [ ] Migration được xem xét; backup Cloud SQL trước migration đã hoàn tất.
- [ ] Secret Manager versions, IAM tối thiểu, Cloud SQL và GCS private đã cấu hình.
- [ ] `APP_BASE_URL` là URL HTTPS thật; `python -m server.production_check` in `PRODUCTION READY` trong môi trường production.
- [ ] Cloud Run revision, URL, service account và giới hạn pool/instances đã xác nhận.
- [ ] Smoke test các chức năng chính, `/health`, `/ready`, `/version` qua.
- [ ] Cloud Logging/Monitoring và alert 5xx, latency, DB, storage, backup đang hoạt động.
- [ ] Biết revision tốt gần nhất và đã kiểm tra lệnh rollback.
- [ ] Không có secret trong repo, image, log hoặc shell history.

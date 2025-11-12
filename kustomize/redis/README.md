# Redis Kustomize Deployment

Kustomize overlay untuk menjalankan Redis StatefulSet beserta Web UI `Redis Commander` di namespace `default`.

## Struktur

- `redis-service.yaml` – Headless Service untuk StatefulSet Redis.
- `redis-statefulset.yaml` – StatefulSet Redis tanpa volume persisten (PVC dikomentari untuk opsi di masa depan).
- `redis-commander-service.yaml` – Service untuk mengakses Redis Commander.
- `redis-commander-deployment.yaml` – Deployment Redis Commander yang terhubung ke Service Redis.

## Deploy

```bash
kubectl apply -k /home/nurahmat/devops-tools/kustomize/redis
```

Pastikan context kubeconfig sudah mengarah ke cluster yang diinginkan.

## Akses Redis

Pod Redis dapat di-port-forward:

```bash
kubectl port-forward statefulset/redis 6379:6379
```

Gunakan `redis-cli` lokal untuk terhubung ke `localhost:6379`.

## Akses Redis Commander (Web UI)

Port-forward Service Redis Commander:

```bash
kubectl port-forward svc/redis-commander 8081:8081
```

Kemudian buka browser ke `http://localhost:8081`. Koneksi ke Redis sudah dikonfigurasi otomatis dengan host `redis:6379` pada namespace yang sama.

## Membersihkan

```bash
kubectl delete -k /home/nurahmat/devops-tools/kustomize/redis
```

## Catatan

- Jika membutuhkan penyimpanan persisten, aktifkan kembali blok PVC yang dikomentari di `redis-statefulset.yaml`.
- Update `REDIS_HOSTS` di `redis-commander-deployment.yaml` jika nama Service/namespace berubah.


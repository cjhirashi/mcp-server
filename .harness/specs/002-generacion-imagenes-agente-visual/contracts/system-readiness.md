# Contrato — `GET /system/readiness`

Endpoint de sistema (sin prefijo de dominio, sin JWT — igual que `GET /health` y
`POST /system/error-report`). Verifica dependencias externas que `/health` no
comprueba, para no ampliar el radio de un healthcheck de Docker/Caddy a un blip
transitorio de MinIO. Cubre RF-008.

## Request

```
GET /system/readiness
```

Sin parámetros, sin body, sin autenticación.

## Response — todo listo

`200 OK`

```json
{
  "status": "ready",
  "checks": {
    "minio": true
  }
}
```

## Response — alguna dependencia falla

`503 Service Unavailable`

```json
{
  "status": "not_ready",
  "checks": {
    "minio": false
  }
}
```

`checks.minio = false` cuando `storage_service.check_connection()` no puede
autenticar o no encuentra el bucket configurado (credenciales desincronizadas,
`minio_storage` caído, red). No es un error RFC 9457 (Problem Details): es un
endpoint de monitoreo/infra, mismo criterio que `/health`.

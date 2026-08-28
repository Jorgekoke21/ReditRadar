# Worker

## Ciclo de vida

python -m app.worker espera la base de datos, construye un AsyncIOScheduler, registra exactamente ocho jobs y muestra
nombre, frecuencia y next_run_at. Los callbacks son coroutines directas de APScheduler; no se crean event loops ni
tareas desacopladas por callback.

Cada callback abre una sesiÃ³n nueva y el servicio de jobs mantiene el lock DB. Las excepciones se convierten en una
ejecuciÃ³n failed y se registran; una ejecuciÃ³n fallida no termina el scheduler. main() captura cancelaciÃ³n, apaga el
scheduler con espera y libera el engine.

## Jobs

1. fetch_reddit_conversations - cada 15 minutos.
2. analyze_pending_conversations - cada 5 minutos.
3. recalculate_scores - cada 6 horas.
4. send_urgent_alerts - cada 30 minutos.
5. send_daily_digest - 09:00.
6. send_weekly_digest - lunes 09:00.
7. purge_expired_reddit_content - cada hora.
8. sync_deleted_reddit_content - cada 6 horas.

max_instances=1, coalesce=True y misfire_grace_time=60 evitan acumulaciÃ³n local. El lock persistente evita solapes
entre procesos; la idempotencia del dedupe evita duplicados tras reinicios.

## Observabilidad

scheduled_job_runs guarda status, processed_count, error_count, error_message, duration_ms y metrics. /diagnostics
consume /api/jobs y /api/jobs/diagnostics; la prÃ³xima ejecuciÃ³n tambiÃ©n se imprime en los logs del worker. El endpoint
estÃ¡ protegido: en producciÃ³n se requiere JOB_ADMIN_EMAILS; en desarrollo local, con AUTH_MODE=development, se mantiene
el modo single-user.


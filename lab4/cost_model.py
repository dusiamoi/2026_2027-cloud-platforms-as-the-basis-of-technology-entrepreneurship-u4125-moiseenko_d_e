#!/usr/bin/env python3
"""Экономическая модель инфраструктуры AI-приложения «ЧекСкан» (Lab4).

Запуск:  python3 lab4/cost_model.py
Ничего не создаёт в облаке и не ходит в сеть: только арифметика по тарифам,
проверенным 02.11.2026 (USD, on-demand, us-central1 / global для Gemini).
Результаты пишутся в lab4/cost_results.json и печатаются таблицей.
"""
import json
import math
import os

HOURS = 720            # расчётный месяц = 30 дней
SECONDS = HOURS * 3600
GIB = 2 ** 30
KIB = 2 ** 10
MIB = 2 ** 20

# ---------------------------------------------------------------- тарифы
P = {
    # Vertex AI, Gemini 3.1 Flash-Lite, Standard, global endpoint
    "ai_in_per_mtok": 0.25,
    "ai_out_per_mtok": 1.50,
    # Cloud Run, request-based billing, Tier 1
    "run_cpu_s": 0.000024,
    "run_mem_gib_s": 0.0000025,
    "run_idle_cpu_s": 0.0000025,       # min instance вне запросов
    "run_idle_mem_gib_s": 0.0000025,
    "run_req_per_m": 0.40,
    # Cloud SQL for PostgreSQL Enterprise, Iowa
    "sql_f1_micro_h": 0.0105,
    "sql_vcpu_h": 0.0413, "sql_mem_gib_h": 0.007,          # zonal
    "sql_vcpu_h_ha": 0.0826, "sql_mem_gib_h_ha": 0.014,    # HA (regional)
    "sql_ssd_gib_h": 0.000232877, "sql_ssd_gib_h_ha": 0.000465753,
    "sql_backup_gib_h": 0.000109589,
    # Cloud Storage, Iowa, flat namespace
    "gcs_std_gib_h": 0.000027397, "gcs_nl_gib_h": 0.000013699,
    "gcs_std_a_per_k": 0.005, "gcs_std_b_per_k": 0.0004,
    "gcs_nl_a_per_k": 0.01, "gcs_nl_b_per_k": 0.001,
    "gcs_nl_retrieval_gib": 0.01,
    # Сеть: интернет-трафик (Европа, первые 10 TiB), балансировщик, Cloud Armor
    "egress_gib": 0.12,
    "lb_rule_h": 0.025, "lb_data_gib": 0.008,
    "armor_policy_h": 0.006849315, "armor_rule_h": 0.001369863,
    "armor_req_per_m": 0.75,
    # Eventarc Standard = 0, транспорт Pub/Sub: $40/TiB, минимум 1000 байт на сообщение
    "pubsub_tib": 40.0,
    # Identity Platform, Tier 1 (email + Google): 0–50k MAU бесплатно, 50k–100k $0.0055
    "idp_free_mau": 50_000, "idp_mau_50_100k": 0.0055,
    # Cloud Scheduler: $0.10 за задание в месяц
    "scheduler_job": 0.10,
    # Наблюдаемость и CI/CD
    "logging_gib": 0.50,
    "ar_gib_h": 0.000136986,
    "build_min": 0.006,
}

# ---------------------------------------------------------------- допущения
COMMON = {
    "receipts_per_mau": 12,          # чеков в месяц на активного пользователя
    "attempt_factor": 1.05,          # оплачиваемых попыток на 1 успешный чек
    # токены на 1 попытку распознавания (Gemini 3: media_resolution HIGH = 1120 токенов/изображение)
    "tok_image": 1120, "tok_prompt": 500, "tok_out": 700,
    # ежемесячный AI-отчёт по тратам: 1 на активного пользователя
    "tok_insight_in": 3000, "tok_insight_out": 600,
    "worker_sec": 6.0,               # время одной попытки Worker (ожидание Gemini + запись в БД)
    "worker_vcpu": 1, "worker_gib": 1.0,
    "api_vcpu": 1, "api_gib": 0.5,
    "visits_per_mau": 12, "api_calls_per_visit": 6, "api_calls_per_receipt": 3,
    "api_sec_per_call": 0.15, "static_req_per_visit": 4,
    "static_mib_per_visit": 1.5, "api_kib_per_call": 4,
    "thumbs_per_visit": 10, "thumb_kib": 40,
    "photo_kib": 450,                # фото после сжатия в браузере (длинная сторона 1600 px)
    "full_photo_view_share": 0.2,    # доля чеков, чьё полное фото открывают
    "retention_months": 12,          # фото хранятся 12 месяцев (гарантия/возврат)
    "nearline_read_share": 0.03,     # доля «старых» фото, открываемых за месяц
    "db_kib_per_receipt": 5,         # строка чека + позиции + индексы
    "log_kib_per_request": 1, "log_kib_per_attempt": 3,
    "reserve": 0.20,
}

STAGES = {
    "pilot": {
        "title": "Начальное (пилот)", "mau": 300, "peak_rps": 0.2,
        "sql": {"kind": "f1-micro", "ha": False, "disk_gib": 10},
        "api_min": 0, "api_max": 3, "worker_max": 5,
        "staging": None, "lb_armor": False,
        "ar_gib": 1, "build_min": 60, "scheduler_jobs": 1,
    },
    "partners": {
        "title": "Тестирование партнёрами", "mau": 5_000, "peak_rps": 3,
        "sql": {"kind": "custom", "vcpu": 1, "mem": 3.75, "ha": False, "disk_gib": 20},
        "api_min": 0, "api_max": 20, "worker_max": 30,
        "staging": {"variable_share": 0.10, "sql": "f1-micro"}, "lb_armor": False,
        "ar_gib": 2, "build_min": 300, "scheduler_jobs": 2,
    },
    "prod": {
        "title": "Продовое решение", "mau": 60_000, "peak_rps": 30,
        "sql": {"kind": "custom", "vcpu": 2, "mem": 7.5, "ha": True, "disk_gib": 100},
        "api_min": 1, "api_max": 50, "worker_max": 250,
        "staging": {"variable_share": 0.10, "sql": "f1-micro"}, "lb_armor": True,
        "armor_rules": 5,
        "ar_gib": 5, "build_min": 1000, "scheduler_jobs": 2,
    },
}


def sql_cost(cfg, steady_db_gib):
    if cfg["kind"] == "f1-micro":
        inst = P["sql_f1_micro_h"] * HOURS
    elif cfg["ha"]:
        inst = (cfg["vcpu"] * P["sql_vcpu_h_ha"] + cfg["mem"] * P["sql_mem_gib_h_ha"]) * HOURS
    else:
        inst = (cfg["vcpu"] * P["sql_vcpu_h"] + cfg["mem"] * P["sql_mem_gib_h"]) * HOURS
    disk_rate = P["sql_ssd_gib_h_ha"] if cfg["ha"] else P["sql_ssd_gib_h"]
    disk = cfg["disk_gib"] * disk_rate * HOURS
    # бэкапы: 7 ежедневных копий инкрементальные ≈ 1,5 × объём данных
    backup = 1.5 * steady_db_gib * P["sql_backup_gib_h"] * HOURS
    return inst, disk, backup


def model(stage_key, c=COMMON):
    s = STAGES[stage_key]
    U = s["mau"]
    N = U * c["receipts_per_mau"]               # успешных чеков в месяц
    M = N * c["attempt_factor"]                 # попыток распознавания
    r = {}

    # --- Vertex AI
    tok_in = M * (c["tok_image"] + c["tok_prompt"]) + U * c["tok_insight_in"]
    tok_out = M * c["tok_out"] + U * c["tok_insight_out"]
    r["ai_receipts"] = M * ((c["tok_image"] + c["tok_prompt"]) * P["ai_in_per_mtok"]
                            + c["tok_out"] * P["ai_out_per_mtok"]) / 1e6
    r["ai_insights"] = U * (c["tok_insight_in"] * P["ai_in_per_mtok"]
                            + c["tok_insight_out"] * P["ai_out_per_mtok"]) / 1e6

    # --- Cloud Run API (SPA + REST)
    visits = U * c["visits_per_mau"]
    api_calls = visits * c["api_calls_per_visit"] + N * c["api_calls_per_receipt"]
    static_req = visits * c["static_req_per_visit"]
    api_req = api_calls + static_req
    api_sec = api_calls * c["api_sec_per_call"] + static_req * 0.01
    r["run_api"] = (api_sec * (c["api_vcpu"] * P["run_cpu_s"] + c["api_gib"] * P["run_mem_gib_s"])
                    + api_req * P["run_req_per_m"] / 1e6)
    r["run_api_min_instance"] = s["api_min"] * SECONDS * (
        c["api_vcpu"] * P["run_idle_cpu_s"] + c["api_gib"] * P["run_idle_mem_gib_s"])

    # --- Cloud Run Worker (распознавание) + job ежемесячных отчётов (≈2 c на пользователя)
    r["run_worker"] = (M * c["worker_sec"] * (c["worker_vcpu"] * P["run_cpu_s"]
                                              + c["worker_gib"] * P["run_mem_gib_s"])
                       + M * P["run_req_per_m"] / 1e6)
    r["run_insights_job"] = U * 2 * (P["run_cpu_s"] + 0.5 * P["run_mem_gib_s"])

    # --- Eventarc / Pub/Sub (push = публикация + доставка, по 1000 байт минимум)
    r["eventarc_pubsub"] = M * 2 * 1000 / 2 ** 40 * P["pubsub_tib"]

    # --- Cloud Storage: фото + миниатюры, 1 мес Standard, затем Nearline до 12 мес
    obj_kib = c["photo_kib"] + c["thumb_kib"]
    month_gib = N * obj_kib * KIB / GIB
    std_gib = month_gib
    nl_gib = month_gib * (c["retention_months"] - 1)
    storage = std_gib * P["gcs_std_gib_h"] * HOURS + nl_gib * P["gcs_nl_gib_h"] * HOURS
    # операции: загрузка фото (A), запись миниатюры (A), lifecycle-перевод в Nearline (A Nearline),
    # чтение фото Worker'ом (B), просмотры миниатюр и фото (B)
    ops_a = 2 * N * P["gcs_std_a_per_k"] / 1e3 + 2 * N * P["gcs_nl_a_per_k"] / 1e3
    thumb_views = visits * c["thumbs_per_visit"]
    photo_views = N * c["full_photo_view_share"]
    ops_b = (M + thumb_views + photo_views) * P["gcs_std_b_per_k"] / 1e3
    nl_reads = nl_gib * c["nearline_read_share"]
    nl_cost = nl_reads * P["gcs_nl_retrieval_gib"] + (nl_reads * GIB / (obj_kib * KIB)) * P["gcs_nl_b_per_k"] / 1e3
    r["gcs"] = storage + ops_a + ops_b + nl_cost

    # --- Cloud SQL
    db_gib = N * c["retention_months"] * c["db_kib_per_receipt"] * KIB / GIB
    inst, disk, backup = sql_cost(s["sql"], db_gib)
    r["sql_instance"] = inst
    r["sql_storage_backup"] = disk + backup

    # --- Интернет-трафик к пользователям
    egress_gib = (visits * (c["static_mib_per_visit"] * MIB
                            + c["thumbs_per_visit"] * c["thumb_kib"] * KIB)
                  + api_calls * c["api_kib_per_call"] * KIB
                  + photo_views * c["photo_kib"] * KIB) / GIB
    r["egress"] = egress_gib * P["egress_gib"]

    # --- Балансировщик + Cloud Armor (только прод)
    if s["lb_armor"]:
        # через LB идут только SPA и API; фото и миниатюры отдаются из GCS по signed URL, мимо LB
        lb_gib = egress_gib - (photo_views * c["photo_kib"]
                               + visits * c["thumbs_per_visit"] * c["thumb_kib"]) * KIB / GIB
        r["lb"] = P["lb_rule_h"] * HOURS + lb_gib * P["lb_data_gib"]
        r["armor"] = (P["armor_policy_h"] + s["armor_rules"] * P["armor_rule_h"]) * HOURS \
            + api_req * P["armor_req_per_m"] / 1e6
    else:
        r["lb"] = 0.0
        r["armor"] = 0.0

    # --- Identity Platform
    paid_mau = max(0, min(U, 100_000) - P["idp_free_mau"])
    r["identity"] = paid_mau * P["idp_mau_50_100k"]

    # --- Логи, Scheduler, CI/CD
    log_gib = (api_req * c["log_kib_per_request"] + M * c["log_kib_per_attempt"]) * KIB / GIB
    r["logging"] = log_gib * P["logging_gib"]
    r["scheduler"] = s["scheduler_jobs"] * P["scheduler_job"]
    r["artifact_registry"] = s["ar_gib"] * P["ar_gib_h"] * HOURS
    r["cloud_build"] = s["build_min"] * P["build_min"]

    # --- Staging: доля переменных затрат + собственная маленькая БД
    variable_keys = ["ai_receipts", "ai_insights", "run_api", "run_worker", "run_insights_job",
                     "eventarc_pubsub", "gcs", "egress", "logging"]
    if s["staging"]:
        var = sum(r[k] for k in variable_keys)
        r["staging"] = var * s["staging"]["variable_share"] + P["sql_f1_micro_h"] * HOURS \
            + 10 * P["sql_ssd_gib_h"] * HOURS
    else:
        r["staging"] = 0.0

    total = sum(r.values())
    reserve = total * c["reserve"]

    # --- проверка пиковой мощности
    worker_peak = math.ceil(s["peak_rps"] * c["attempt_factor"] * c["worker_sec"])
    peak_tpm_in = s["peak_rps"] * c["attempt_factor"] * (c["tok_image"] + c["tok_prompt"]) * 60

    return {
        "title": s["title"], "mau": U, "receipts": N, "attempts": M,
        "tokens_in": tok_in, "tokens_out": tok_out,
        "photo_stock_gib": std_gib + nl_gib, "db_gib": db_gib, "egress_gib": egress_gib,
        "log_gib": log_gib,
        "items": r, "total": total, "reserve": reserve, "budget": total + reserve,
        "per_receipt": (total + reserve) / N,
        "ai_share": (r["ai_receipts"] + r["ai_insights"]) / total,
        "worker_peak_instances": worker_peak, "worker_max": s["worker_max"],
        "peak_input_tpm": peak_tpm_in,
    }


LABELS = [
    ("ai_receipts", "Vertex AI: распознавание чеков"),
    ("ai_insights", "Vertex AI: ежемесячные отчёты"),
    ("run_api", "Cloud Run API: запросы и время"),
    ("run_api_min_instance", "Cloud Run API: 1 тёплый экземпляр"),
    ("run_worker", "Cloud Run Worker"),
    ("run_insights_job", "Cloud Run Job отчётов"),
    ("eventarc_pubsub", "Eventarc / Pub/Sub"),
    ("gcs", "Cloud Storage: фото, операции"),
    ("sql_instance", "Cloud SQL: инстанс"),
    ("sql_storage_backup", "Cloud SQL: диск и бэкапы"),
    ("egress", "Интернет-трафик"),
    ("lb", "Load Balancer"),
    ("armor", "Cloud Armor"),
    ("identity", "Identity Platform"),
    ("logging", "Cloud Logging"),
    ("scheduler", "Cloud Scheduler"),
    ("artifact_registry", "Artifact Registry"),
    ("cloud_build", "Cloud Build"),
    ("staging", "Окружение staging"),
]


def fmt(v):
    return f"{v:.4f}" if 0 < v < 0.01 else f"{v:.2f}"


def sensitivity():
    base = model("prod")["budget"]
    cases = [
        ("Базовый", {}),
        ("Изображение 2240 токенов (ULTRA_HIGH) вместо 1120", {"tok_image": 2240}),
        ("Изображение 560 токенов (MEDIUM) вместо 1120", {"tok_image": 560}),
        ("Ответ 1 400 токенов вместо 700", {"tok_out": 1400}),
        ("25 чеков на пользователя вместо 12", {"receipts_per_mau": 25}),
        ("1,30 попытки вместо 1,05", {"attempt_factor": 1.30}),
    ]
    out = []
    for name, ch in cases:
        c = dict(COMMON, **ch)
        b = model("prod", c)["budget"]
        out.append({"case": name, "budget": b, "delta": b / base - 1})
    return out


def main():
    res = {k: model(k) for k in STAGES}
    sens = sensitivity()
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "cost_results.json"), "w", encoding="utf-8") as f:
        json.dump({"prices": P, "assumptions": COMMON, "stages": STAGES,
                   "results": res, "sensitivity": sens}, f, ensure_ascii=False, indent=2)

    keys = list(STAGES)
    print("| Статья, USD/месяц | " + " | ".join(res[k]["title"] for k in keys) + " |")
    print("|---|" + "---:|" * len(keys))
    for key, label in LABELS:
        print(f"| {label} | " + " | ".join(fmt(res[k]["items"][key]) for k in keys) + " |")
    print("| **Всего облако** | " + " | ".join(f"**{res[k]['total']:.2f}**" for k in keys) + " |")
    print("| **Резерв 20%** | " + " | ".join(f"**{res[k]['reserve']:.2f}**" for k in keys) + " |")
    print("| **Бюджет с резервом** | " + " | ".join(f"**{res[k]['budget']:.2f}**" for k in keys) + " |")
    print()
    for k in keys:
        x = res[k]
        print(f"{x['title']}: MAU={x['mau']}, чеков={x['receipts']}, USD/чек={x['per_receipt']:.5f}, "
              f"доля AI={x['ai_share']:.1%}, фото={x['photo_stock_gib']:.1f} GiB, БД={x['db_gib']:.2f} GiB, "
              f"egress={x['egress_gib']:.1f} GiB, worker пик={x['worker_peak_instances']}/{x['worker_max']}, "
              f"TPM вход на пике={x['peak_input_tpm']:.0f}")
    print()
    for s in sens:
        print(f"| {s['case']} | {s['budget']:.2f} | {s['delta']:+.1%} |")


if __name__ == "__main__":
    main()

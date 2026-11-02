# Облачные платформы как основа технологического предпринимательства

Репозиторий с отчётами по лабораторным работам курса
[Cloud platforms as the basis of technology entrepreneurship](https://github.com/itmo-ict-faculty/cloud-platforms-as-the-basis-of-technology-entrepreneurship) (Университет ИТМО, ФИКТ).

* **Студент:** Моисеенко Дарья Евгеньевна
* **Группа:** U4125
* **Учебный год:** 2026/2027
* **Облако:** Google Cloud, проект `cloud-platforms-as-the-basis`

## Лабораторные работы

| № | Тема | Отчёт | Статус |
|---|---|---|---|
| 1 | Обзор Google Cloud и исследование основных сервисов (IAM, Compute Engine, Cloud Storage) | [lab1/lab1_report.md](lab1/lab1_report.md) | выполнена |
| 2 | Исследование Cloud Run | [lab2/lab2_report.md](lab2/lab2_report.md) | выполнена |
| 3 | Исследование Cloud Storage | [lab3/lab3_report.md](lab3/lab3_report.md) | выполнена |

## Заметки

* Все ресурсы созданы с префиксом `dmoiseenko-` и после выполнения каждой работы удалены.
* Лаба 1: бакет `lab1-bucket-itmo` публичный (`allUsers` → Storage Object Viewer), поэтому чтение из него работает при любой роли сервисного аккаунта. Разница между Storage Admin и Compute Viewer показана на операциях `storage.buckets.list` и `compute.instances.list`.
* Лаба 2: для разделения трафика между N ревизиями max instances сервиса должно быть не меньше N.

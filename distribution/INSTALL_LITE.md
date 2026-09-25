# Установка EFREN Lite

## Что нужно

- Windows 10/11;
- около 8–12 ГБ свободного места после загрузки моделей;
- процессор с поддержкой AVX2 желательно;
- интернет только на этапе подготовки файлов.

Дискретная видеокарта не требуется: Lite использует CPU для распознавания и Piper для озвучивания.

## Подготовка сборки разработчиком

Из корня проекта запускаются скрипты из `distribution`:

```powershell
python distribution/prepare_lite.py distribution/staging-lite
python distribution/add_python.py distribution/staging-lite
python distribution/add_gigaam.py distribution/staging-lite
python distribution/prepare_voice_assets.py distribution/staging-lite
```

Готовую папку `staging-lite` можно упаковать в ZIP и передать другу. Не включайте в архив `lite-auth.json`, логи, личные настройки и Discord-токены.

## Первый запуск у друга

1. Распаковать архив в папку без кириллицы, например `C:\EFREN-Lite`.
2. Запустить панель управления.
3. Создать локальный пароль Lite.
4. Нажать запуск JARVIS.
5. Проверить микрофон и устройство вывода в настройках Windows.

Lite не подключается к вашему Discord-боту и не получает его токен.

## Проверка

Из папки сборки можно выполнить:

```powershell
runtime\python\python.exe -s distribution\check_python.py .
```

Проверка целостности и обновления должны выполняться отдельным установщиком или скриптом обновления, а не заменой файлов вручную во время работы JARVIS.

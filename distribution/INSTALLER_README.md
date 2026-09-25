# Установщик Lite

`install-lite.ps1` распаковывает `EFREN-Lite.zip`, создаёт ярлык на рабочем столе и запускает панель.

Запуск из PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-lite.ps1
```

Для настоящего `Setup.exe` нужен Inno Setup или NSIS. После установки компилятора этот скрипт можно заменить единым установщиком без изменения содержимого Lite-архива.

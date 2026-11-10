# Сторонний код и ресурсы

Проект использует библиотеки (и не только) других разработчиков. Они лежат в репозитории
целиком, чтобы прошивка собиралась без установки пакетов, и сохраняют
оригинальные заголовки с копирайтами.

| Компонент | Где | Автор | Лицензия |
|-----------|-----|-------|----------|
| micro-gui | `src/gui/` | Peter Hinch | MIT |
| Драйвер ILI9341 и `boolpalette` | `src/drivers/` | Peter Hinch, на основе [rdagger/micropython-ili9341](https://github.com/rdagger/micropython-ili9341) | MIT |
| primitives (encoder, pushbutton, delay_ms и др.) | `src/gui/primitives/` | Peter Hinch | MIT |
| aioble | `src/lib/aioble/` | Jim Mussared, проект MicroPython | MIT |
| USB device, USB MIDI | `src/lib/usb/device/` | Angus Gratton, Paul Hamshere | MIT |
| Шрифт Press Start 2P | `src/apps/system/explorer/utils/index.html`, `usb_tool.py` | The Press Start 2P Project Authors | SIL OFL 1.1 |

Ссылки:

- micro-gui — https://github.com/peterhinch/micropython-micro-gui
- nano-gui и драйверы — https://github.com/peterhinch/micropython-nano-gui
- micropython-async — https://github.com/peterhinch/micropython-async
- aioble — https://github.com/micropython/micropython-lib/tree/master/micropython/bluetooth/aioble
- USB — https://github.com/micropython/micropython-lib/tree/master/micropython/usb
- Press Start 2P — https://fonts.google.com/specimen/Press+Start+2P

## Шрифт Press Start 2P

Шрифт встроен в веб-интерфейс в виде двух WOFF2-сабсетов (латиница и кириллица),
закодированных в base64, поэтому страница не ходит в интернет за шрифтом.
Копирайт и полный текст лицензии — в `LICENSES/OFL-1.1.txt`.

```
Copyright 2012 The Press Start 2P Project Authors (cody@zone38.net),
with Reserved Font Name "Press Start 2P".
```

## Лицензия самого проекта

Код, написанный для этого проекта, распространяется по MIT (`LICENSE`).
Вендорные файлы остаются под своими лицензиями, указанными выше; все они
совместимы с MIT.

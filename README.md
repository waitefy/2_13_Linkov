# Анализ и визуализация зависимостей NuGet  
### Практическая работа №2

Приложение на Python анализирует зависимости NuGet-пакетов и визуализирует их в виде графа.  
Поддерживаются режимы `real` и `test`. Реализованы этапы 1–5.

---

## 1. Структура проекта

```text
.
├── main.py
├── config.yaml
├── requirements.txt
├── scripts/
├── tests/
└── README.md
```

---

## 2. Требования

```bash
pip install -r requirements.txt
```

- Python 3.10+
- Для режима `real` необходим доступ в интернет (NuGet flatcontainer API)

---

## 3. Конфигурация и запуск

`config.yaml` (пример):

```yaml
package_name: "A"
repo: "tests/repos/repo_linear.txt"
test_mode: "test"
version: "1.0.0"
graph_image_file: "linear.svg"
```

Запуск:

```bash
python main.py [--stage N]
```

### Аргументы

Параметр | Описание
-------- | --------
`--stage` | Номер этапа (1–5). Если не задан — запускается интерактивное меню.

---

# ЭТАП 1. Чтение конфигурации

```bash
python main.py --stage 1
```

Пример вывода:

```text
Конфигурация:
        package_name = A
        repo = tests/repos/repo_linear.txt
        test_mode = test
        version = 1.0.0
        graph_image_file = linear.svg
```

---

# ЭТАП 2. Прямые зависимости (режим real)

```bash
python main.py --stage 2
```

Пример вывода (Newtonsoft.Json):

```text
Прямые зависимости:
        Microsoft.CSharp 4.3.0
        NETStandard.Library 1.6.1
        System.ComponentModel.TypeConverter 4.3.0
        System.Runtime.Serialization.Primitives 4.3.0
```

---

# ЭТАП 3. Полный граф зависимостей (DFS)

```bash
python main.py --stage 3
```

Пример (ветвящийся граф):

```text
Граф зависимостей:
        A: B, C
        B: D
        C: (нет зависимостей)
        D: (нет зависимостей)
```

---

# ЭТАП 4. Порядок загрузки и циклы

```bash
python main.py --stage 4
```

Пример:

```text
Порядок загрузки:
        C
        B
        A
```

---

# ЭТАП 5. Визуализация (Mermaid + SVG)

```bash
python main.py --stage 5
```

Пример:

```text
Текст диаграммы Mermaid:
graph TD
        C
        A --> B
        B --> C
SVG-файл: linear.svg
```

---

## Итог

- Проверка и валидация конфигурации  
- Получение зависимостей NuGet (`real`) и файловый режим (`test`)  
- Построение графа (DFS)  
- Топологическая сортировка и поиск циклов  
- Генерация Mermaid-диаграммы и SVG  
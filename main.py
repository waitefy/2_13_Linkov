import argparse
import math
import sys
import re
import io
import zipfile
import urllib.parse
import urllib.request
import yaml
from xml.etree import ElementTree as ET
from pathlib import Path
from collections import deque


# -------------------- конфиг --------------------
# Определение обязательных параметров конфигурации и допустимых форматов.

SCHEME = [
    'package_name', 'repo', 'test_mode', 'version', 'graph_image_file'
]
NAME_RE = re.compile(r'^[A-Za-z0-9._\-]+$')
ALLOWED_MODES = {'real', 'test'}


def load_config(path='config.yaml') -> dict:
    """
    Загрузка и валидация конфигурации.
    Проверяются обязательные параметры и корректность их значений.
    """
    data = yaml.safe_load(open(path, 'r', encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(
            'конфигурация: корневой объект должен быть словарём'
        )

    errs = []

    # Поочередная валидация каждого параметра.
    for k in SCHEME:
        v = data.get(k)
        if v is None:
            errs.append(f'{k}: отсутствует')
            continue

        if k == 'package_name':
            # Формат имени NuGet-пакета.
            if not (isinstance(v, str) and v.strip() and NAME_RE.fullmatch(v)):
                errs.append(
                    'package_name: допустимы символы A–Z a–z 0–9 . _ -'
                )

        elif k == 'repo':
            # Путь к тестовому файлу или URL репозитория.
            if not (isinstance(v, str) and v.strip()):
                errs.append('repo: пусто')

        elif k == 'test_mode':
            # Режим работы: test или real.
            if not (isinstance(v, str)
                    and v.strip().lower() in ALLOWED_MODES):
                errs.append("test_mode: допустимо значение 'real' или 'test'")

        elif k == 'version':
            # Формат версии NuGet-пакета.
            if not (
                isinstance(v, str)
                and v.strip()
                and re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.\-+]*', v)
            ):
                errs.append('version: недопустимый формат')

        elif k == 'graph_image_file':
            # Проверка имени SVG-файла без путей.
            if not (
                isinstance(v, str) and v.strip() and '.' in v
                and not v.startswith('.') and '/' not in v
                and '\\' not in v
            ):
                errs.append(
                    'graph_image_file: требуется имя файла с расширением '
                    'без директорий'
                )

    # Вывод ошибок конфигурации.
    if errs:
        print('ошибка конфигурации:', file=sys.stderr)
        for e in errs:
            print(f'- {e}', file=sys.stderr)
        sys.exit(2)

    return data


# -------------------- NuGet (реальный режим) --------------------
# Получение .nupkg, распаковка и извлечение .nuspec.

def flat_url(base: str, pkg: str, ver: str) -> str:
    """
    Формирование URL формата NuGet flatcontainer:
    <repo>/<id>/<version>/<id>.<version>.nupkg
    """
    base = base if base.endswith('/') else base + '/'
    return f'{base}{pkg.lower()}/{ver.lower()}/{pkg.lower()}.{ver.lower()}.nupkg'


def fetch_nuspec(repo_url: str, package: str, version: str) -> ET.Element:
    """
    Загрузка .nupkg, поиск файла .nuspec внутри архива и разбор XML.
    """
    with urllib.request.urlopen(flat_url(repo_url, package, version)) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(
            (n for n in zf.namelist() if n.lower().endswith('.nuspec')),
            None
        )
        if not name:
            raise RuntimeError('в пакете не найден файл .nuspec')
        return ET.fromstring(zf.read(name))


def extract_direct_deps(nuspec: ET.Element):
    """
    Извлечение прямых зависимостей из тега <dependency> в .nuspec.
    """
    return [
        (d.get('id'), d.get('version'))
        for d in nuspec.findall('.//{*}dependency')
        if d.get('id')
    ]


# -------------------- тестовый репозиторий --------------------
# Чтение зависимостей из текстового файла вида: A: B C D

def load_test_graph(path: str) -> dict:
    """
    Загрузка тестового графа зависимостей из текстового файла.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f'файл тестового репозитория {path} не найден'
        )

    g = {}
    for line in open(p, 'r', encoding='utf-8'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if ':' not in s:
            raise ValueError(f'некорректная строка: «{s}»')
        name, deps = s.split(':', 1)
        g[name.strip()] = [d.strip() for d in deps.split() if d.strip()]
    return g


# -------------------- построение графа (DFS) --------------------
# Вычисление транзитивных зависимостей с использованием рекурсии.

def build_graph_real_dfs(repo_url: str,
                         root_name: str,
                         root_ver: str) -> dict:
    """
    Построение графа зависимостей в реальном режиме на основе NuGet.
    Обход производится алгоритмом DFS.
    """
    graph, seen = {}, set()

    def dfs(name: str, ver: str):
        key = name.lower()
        if key in seen:
            return
        seen.add(key)

        deps = extract_direct_deps(fetch_nuspec(repo_url, name, ver))
        graph[name] = [d for d, _ in deps]

        # Рекурсивный обход зависимостей.
        for d, dv in deps:
            dfs(d, dv or root_ver)

    dfs(root_name, root_ver)
    return graph


def build_graph_test_dfs(repo_graph: dict, root_name: str) -> dict:
    """
    Построение графа зависимостей в тестовом режиме на основе файла.
    """
    graph, seen = {}, set()

    def dfs(n: str):
        if n in seen:
            return
        seen.add(n)

        deps = repo_graph.get(n, [])
        graph[n] = deps

        for d in deps:
            dfs(d)

    dfs(root_name)
    return graph


# -------------------- доп операции --------------------
# Топологическая сортировка и выявление циклов.

def topo_load_order(graph: dict):
    """
    Выполнение топологической сортировки.
    Возвращаются два списка:
    - порядок загрузки
    - узлы, входящие в цикл (если есть)
    """
    nodes = set(graph.keys())
    for deps in graph.values():
        nodes.update(deps)

    indeg = {n: 0 for n in nodes}
    rev = {n: [] for n in nodes}

    # Подсчёт входящих рёбер.
    for n, deps in graph.items():
        for d in deps:
            indeg[n] += 1
            rev[d].append(n)

    # Очередь узлов с нулевой степенью.
    q = deque(n for n in nodes if indeg[n] == 0)
    order = []

    # Классический алгоритм Кана.
    while q:
        v = q.popleft()
        order.append(v)
        for w in rev[v]:
            indeg[w] -= 1
            if indeg[w] == 0:
                q.append(w)

    cyc = [n for n in nodes if indeg[n] > 0]
    return order, cyc


def build_mermaid(graph: dict) -> str:
    """
    Формирование текстового описания графа в формате Mermaid.
    """
    lines = ['graph TD']
    nodes = set(graph.keys())
    for deps in graph.values():
        nodes.update(deps)

    # Изолированные узлы.
    for n in sorted(nodes):
        if not graph.get(n):
            lines.append(f'\t{n}')

    # Рёбра.
    for s in sorted(graph.keys()):
        for d in sorted(graph[s]):
            lines.append(f'\t{s} --> {d}')

    return '\n'.join(lines)


# -------------------- простая SVG-визуализация --------------------
# Автоматическая раскладка узлов и отрисовка рёбер.

def positions_bfs(graph: dict, root: str):
    """
    Расстановка узлов по уровням графа с помощью BFS.
    """
    nodes = set(graph.keys())
    for deps in graph.values():
        nodes.update(deps)
    if root not in nodes:
        nodes.add(root)

    lvl, q = {root: 0}, deque([root])

    # Вычисление уровней.
    while q:
        v = q.popleft()
        for d in graph.get(v, []):
            if d not in lvl:
                lvl[d] = lvl[v] + 1
                q.append(d)

    # Группировка узлов по уровням.
    per = {}
    for n, l in lvl.items():
        per.setdefault(l, []).append(n)
    for l in per:
        per[l].sort()

    # Координаты узлов.
    pos, xstep, ystep = {}, 200, 100
    for l, arr in per.items():
        for i, n in enumerate(arr):
            pos[n] = (100 + l * xstep, 100 + i * ystep)

    # Обработка недостижимых узлов.
    for n in nodes:
        if n not in pos:
            pos[n] = (100, 100 + (len(pos) * ystep))

    return pos


def render_svg(graph: dict, root: str, svg_file: str):
    """
    Генерация SVG-файла на основе графа:
    - одиночные рёбра;
    - двойные рёбра при цикле A <-> B;
    - кружки и подписи узлов.
    """
    pos = positions_bfs(graph, root)

    xs = [x for x, _ in pos.values()]
    ys = [y for _, y in pos.values()]
    w = max(xs) + 100 if xs else 300
    h = max(ys) + 100 if ys else 200

    # Сбор рёбер.
    edges = [(s, d) for s, deps in graph.items() for d in deps]
    edge_set = set(edges)
    processed_pairs = set()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="10" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#000"/></marker></defs>'
    ]

    # Отрисовка рёбер.
    for s, d in edges:
        # Взаимные рёбра (A <-> B)
        if (d, s) in edge_set and (s, d) not in processed_pairs \
                and (d, s) not in processed_pairs:
            x1, y1 = pos.get(s, (0, 0))
            x2, y2 = pos.get(d, (0, 0))

            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy) or 1.0
            scale = 10.0 / length
            px = -dy * scale
            py = dx * scale

            parts.append(
                f'<line x1="{x1 + px}" y1="{y1 + py}" '
                f'x2="{x2 + px}" y2="{y2 + py}" '
                f'stroke="#000" marker-end="url(#arrow)"/>'
            )
            parts.append(
                f'<line x1="{x2 - px}" y1="{y2 - py}" '
                f'x2="{x1 - px}" y2="{y1 - py}" '
                f'stroke="#000" marker-end="url(#arrow)"/>'
            )

            processed_pairs.add((s, d))
            processed_pairs.add((d, s))
        elif (d, s) not in edge_set:
            # Обычное однонаправленное ребро.
            x1, y1 = pos.get(s, (0, 0))
            x2, y2 = pos.get(d, (0, 0))
            parts.append(
                f'<line x1="{x1}" y1="{y1}" '
                f'x2="{x2}" y2="{y2}" '
                f'stroke="#000" marker-end="url(#arrow)"/>'
            )

    # Узлы.
    for n, (x, y) in pos.items():
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="20" stroke="#000" fill="#fff"/>'
        )
        parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" dy=".3em" '
            f'font-family="monospace" font-size="12">{n}</text>'
        )

    parts.append('</svg>')
    Path(svg_file).write_text('\n'.join(parts), encoding='utf-8')


# -------------------- этапы --------------------
# Каждая функция соответствует одному этапу из задания.

def stage1_print_config(cfg: dict):
    """
    Этап 1: вывод параметров конфигурации в формате ключ=значение.
    """
    print('Конфигурация:')
    for k in SCHEME:
        print(f'\t{k} = {cfg[k]}')


def stage2_print_direct(cfg: dict):
    """
    Этап 2: вывод прямых зависимостей реального NuGet-пакета.
    """
    if cfg['test_mode'].strip().lower() != 'real':
        print(
            'ошибка: этап 2 возможен только в режиме real '
            '(используется реальный репозиторий NuGet)',
            file=sys.stderr
        )
        sys.exit(2)
    root = fetch_nuspec(cfg['repo'], cfg['package_name'], cfg['version'])
    deps = extract_direct_deps(root)

    print('Прямые зависимости:')
    if not deps:
        print('\t(нет прямых зависимостей)')
    else:
        for d, v in deps:
            print(f'\t{d} {v or ""}'.rstrip())


def graph_for_mode(cfg: dict) -> dict:
    """
    Выбор источника данных для построения графа:
    - тестовый режим: текстовый файл
    - реальный режим: NuGet
    """
    mode = cfg['test_mode'].strip().lower()

    if mode == 'test':
        repo_graph = load_test_graph(cfg['repo'])
        return build_graph_test_dfs(repo_graph, cfg['package_name'])

    return build_graph_real_dfs(
        cfg['repo'],
        cfg['package_name'],
        cfg['version'],
    )


def stage3_graph(cfg: dict):
    """
    Этап 3: построение и вывод полного графа зависимостей.
    """
    g = graph_for_mode(cfg)
    print('Граф зависимостей:')
    for n in sorted(g.keys()):
        deps = ', '.join(g[n]) if g[n] else '(нет зависимостей)'
        print(f'\t{n}: {deps}')


def stage4_order(cfg: dict):
    """
    Этап 4: вычисление порядка загрузки и определение циклов.
    """
    g = graph_for_mode(cfg)
    order, cyc = topo_load_order(g)

    print('Порядок загрузки:')
    for x in order:
        print(f'\t{x}')

    if cyc:
        print('\t(обнаружен цикл: ' + ', '.join(sorted(cyc)) + ')')


def stage5_visual(cfg: dict):
    """
    Этап 5: генерация Mermaid и SVG представлений графа.
    """
    g = graph_for_mode(cfg)
    print('Текст диаграммы Mermaid:')
    print(build_mermaid(g))

    render_svg(g, cfg['package_name'], cfg['graph_image_file'])
    print(f'SVG-файл: {cfg["graph_image_file"]}')


def parse_args():
    """
    Разбор командной строки.
    Опция --stage позволяет запускать этапы автоматически.
    """
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--stage', type=int)
    return ap.parse_args()


# -------------------- меню --------------------
# Основная точка входа: запуск этапов через аргумент или меню.

def main():
    try:
        args = parse_args()
        cfg = load_config('config.yaml')

        # Автоматический запуск этапа через --stage.
        if args.stage is not None:
            stage = args.stage

            if stage == 1:
                stage1_print_config(cfg)
            elif stage == 2:
                stage2_print_direct(cfg)
            elif stage == 3:
                stage3_graph(cfg)
            elif stage == 4:
                stage4_order(cfg)
            elif stage == 5:
                stage5_visual(cfg)
            else:
                print('ошибка: неверный номер этапа', file=sys.stderr)
                sys.exit(2)

            return

        # Интерактивный режим.
        print('Выберите этап:\n'
              '  1. Печать конфигурации\n'
              '  2. Прямые зависимости (режим real)\n'
              '  3. Граф зависимостей (DFS)\n'
              '  4. Порядок загрузки зависимостей\n'
              '  5. Визуализация (Mermaid + SVG)\n'
              '  0. Выход')

        ch = ''
        while ch != '0':
            ch = input('> ').strip().lower()
            if ch == '1':
                stage1_print_config(cfg)
            elif ch == '2':
                stage2_print_direct(cfg)
            elif ch == '3':
                stage3_graph(cfg)
            elif ch == '4':
                stage4_order(cfg)
            elif ch == '5':
                stage5_visual(cfg)

    except Exception as e:
        # Общий перехват ошибок.
        print(f'ошибка: {e}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()

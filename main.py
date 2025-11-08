import sys, re, urllib.parse, urllib.request, io, zipfile
from xml.etree import ElementTree
from pathlib import Path
from collections import deque

try:
    import yaml  # pip install pyyaml
except ImportError:
    yaml = None
    print('error: PyYAML не установлен. Установите: pip install pyyaml', file=sys.stderr)
    sys.exit(2)


def is_valid_url(url):
    if not isinstance(url, str):
        raise TypeError(f'ожидалась строка, получено {type(url).__name__}')
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f'«{url}» не является корректным URL (нужен http/https)')
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f'недопустимая схема «{parsed.scheme}», разрешены http/https')
    return True


def validate_param(name: str, value, name_re, allowed_modes):
    if name == 'package_name':
        if not isinstance(value, str) or not value.strip():
            return 'package_name: пусто'
        if not name_re.fullmatch(value):
            return 'package_name: допустимы A–Z a–z 0–9 . _ -'

    elif name == 'repo':
        if not isinstance(value, str) or not value.strip():
            return 'repo: пусто'
        try:
            if is_valid_url(value):
                return None
        except (TypeError, ValueError):
            pass
        if not Path(value).exists():
            return 'repo: не URL и путь не существует'

    elif name == 'test_mode':
        if isinstance(value, str):
            value = value.strip().lower()
        if value not in allowed_modes:
            return "test_mode: допустимо 'real' или 'test'"

    elif name == 'version':
        if not isinstance(value, str) or not value.strip():
            return 'version: пусто'
        if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.\-+]*', value):
            return 'version: недопустимый формат'

    elif name == 'graph_image_file':
        if not isinstance(value, str) or not value.strip():
            return 'graph_image_file: пусто'
        if '/' in value or '\\' in value:
            return 'graph_image_file: без директорий, только имя файла'
        if '.' not in value or value.startswith('.'):
            return 'graph_image_file: требуется расширение'
    return None


def load_yaml_config(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError('config: корневой объект должен быть словарём')
    return data


def fetch_nuspec_from_nuget(repo_url: str, package_name: str, version: str) -> ElementTree.Element:
    base = repo_url
    if not base.endswith('/'):
        base += '/'
    package_id = package_name.lower()
    package_version = version.lower()
    nupkg_url = f'{base}{package_id}/{package_version}/{package_id}.{package_version}.nupkg'

    try:
        with urllib.request.urlopen(nupkg_url) as resp:
            data = resp.read()
    except Exception as e:
        raise RuntimeError(f'не удалось скачать пакет по URL {nupkg_url}: {e}')

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            nuspec_name = None
            for name in zf.namelist():
                if name.lower().endswith('.nuspec'):
                    nuspec_name = name
                    break
            if nuspec_name is None:
                raise RuntimeError('в пакете не найден .nuspec файл')
            nuspec_bytes = zf.read(nuspec_name)
    except Exception as e:
        raise RuntimeError(f'ошибка распаковки nupkg: {e}')

    try:
        root = ElementTree.fromstring(nuspec_bytes)
    except Exception as e:
        raise RuntimeError(f'ошибка разбора nuspec: {e}')
    return root


def extract_direct_dependencies(nuspec_root: ElementTree.Element):
    deps = []
    for dep in nuspec_root.findall('.//{*}dependency'):
        dep_id = dep.get('id')
        dep_ver = dep.get('version')
        if dep_id:
            deps.append((dep_id, dep_ver))
    return deps


def build_dependency_graph_real(repo_url: str, root_name: str, root_version: str):
    graph = {}
    visited = set()
    queue = deque()

    visited.add(root_name.lower())
    queue.append((root_name, root_version))

    while queue:
        package_name, version = queue.popleft()
        try:
            nuspec_root = fetch_nuspec_from_nuget(repo_url, package_name, version)
            deps = extract_direct_dependencies(nuspec_root)
        except RuntimeError as e:
            print(f'warn: не удалось получить зависимости для {package_name} {version}: {e}', file=sys.stderr)
            deps = []

        dep_ids = []
        for dep_id, dep_ver in deps:
            dep_ids.append(dep_id)
            key = dep_id.lower()
            if key in visited:
                continue
            visited.add(key)
            dep_version = dep_ver if dep_ver else root_version
            queue.append((dep_id, dep_version))

        graph[package_name] = dep_ids

    return graph


def load_test_repo_graph(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f'файл тестового репозитория {path} не найден')

    repo_graph = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                raise RuntimeError(f'некорректная строка в тестовом репозитории: «{line}»')
            name, deps_str = line.split(':', 1)
            name = name.strip()
            deps = [d.strip() for d in deps_str.split() if d.strip()]
            repo_graph[name] = deps
    return repo_graph


def build_dependency_graph_test(repo_graph: dict, root_name: str):
    graph = {}
    visited = set()
    queue = deque()

    visited.add(root_name)
    queue.append(root_name)

    while queue:
        pkg = queue.popleft()
        deps = repo_graph.get(pkg, [])
        graph[pkg] = deps
        for dep in deps:
            if dep in visited:
                continue
            visited.add(dep)
            queue.append(dep)

    return graph


def compute_load_order(graph: dict, root_name: str):
    nodes = set(graph.keys())
    for deps in graph.values():
        nodes.update(deps)

    indegree = {n: 0 for n in nodes}
    reverse_adj = {n: [] for n in nodes}

    for node, deps in graph.items():
        for dep in deps:
            indegree[node] += 1
            reverse_adj[dep].append(node)

    queue = deque()
    for n in nodes:
        if indegree[n] == 0:
            queue.append(n)

    order = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for nxt in reverse_adj[n]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(nodes):
        cyclic = [n for n in nodes if indegree[n] > 0]
        return order, cyclic
    return order, []


def main():
    scheme = ['package_name', 'repo', 'test_mode', 'version', 'graph_image_file']
    name_re = re.compile(r'^[A-Za-z0-9._\-]+$')
    allowed_modes = {'real', 'test'}
    config_path = 'config.yaml'

    try:
        cfg = load_yaml_config(config_path)
    except FileNotFoundError:
        print(f'error: файл {config_path} не найден', file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f'error: не удалось прочитать конфигурацию: {e}', file=sys.stderr)
        sys.exit(2)

    errors = []
    for key in scheme:
        if key not in cfg:
            errors.append(f'{key}: отсутствует')
        else:
            err = validate_param(key, cfg[key], name_re, allowed_modes)
            if err:
                errors.append(err)

    for extra in (k for k in cfg.keys() if k not in scheme):
        print(f"warn: неизвестный параметр '{extra}' будет проигнорирован", file=sys.stderr)

    if errors:
        print('invalid configuration:', file=sys.stderr)
        for e in errors:
            print(f'- {e}', file=sys.stderr)
        sys.exit(2)

    package_name = cfg['package_name']
    repo = cfg['repo']
    version = cfg['version']
    mode = cfg['test_mode']
    if isinstance(mode, str):
        mode = mode.strip().lower()
    else:
        mode = 'real'

    if mode == 'test':
        try:
            repo_graph = load_test_repo_graph(Path(repo))
            graph = build_dependency_graph_test(repo_graph, package_name)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(2)
    else:
        if not isinstance(repo, str) or not repo.startswith(('http://', 'https://')):
            print('error: в режиме real repo должен быть URL NuGet (http/https)', file=sys.stderr)
            sys.exit(2)
        graph = build_dependency_graph_real(repo, package_name, version)

    print('dependency_graph:')
    for node in sorted(graph.keys()):
        deps = graph[node]
        if deps:
            print(f'\t{node}: ' + ', '.join(deps))
        else:
            print(f'\t{node}: (нет зависимостей)')

    if mode == 'test':
        load_order, cyclic = compute_load_order(graph, package_name)
        print('load_order:')
        for n in load_order:
            print(f'\t{n}')
        if cyclic:
            print('\t(обнаружен цикл: ' + ', '.join(sorted(cyclic)) + ')')


if __name__ == '__main__':
    main()

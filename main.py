import sys, re, urllib.parse, urllib.request, io, zipfile
from xml.etree import ElementTree
from pathlib import Path
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

    # Этап 1: вывод параметров
    # for key in scheme:
    #     print(f'{key}={cfg[key]}')

    # Этап 2: получение и вывод прямых зависимостей NuGet
    repo = cfg['repo']
    package_name = cfg['package_name']
    version = cfg['version']

    if not isinstance(repo, str) or not repo.startswith(('http://', 'https://')):
        print('error: на этапе 2 repo должен быть URL NuGet (http/https)', file=sys.stderr)
        sys.exit(2)

    try:
        nuspec_root = fetch_nuspec_from_nuget(repo, package_name, version)
        deps = extract_direct_dependencies(nuspec_root)
    except RuntimeError as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(2)

    print('direct_dependencies:')
    if not deps:
        print('\t(нет прямых зависимостей)')
    else:
        for dep_id, dep_ver in deps:
            if dep_ver:
                print(f'\t{dep_id} {dep_ver}')
            else:
                print(f'\t{dep_id}')


if __name__ == '__main__':
    main()

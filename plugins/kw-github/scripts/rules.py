"""올리면 안 되는 파일을 판정한다. 저장과 이력 검사가 이 판정 하나를 함께 쓴다."""
import fnmatch
import json
import re
from pathlib import Path, PurePosixPath

MIB = 1024 * 1024

# 내용 정규식을 태울 텍스트 파일의 확장자다. 저장과 이력 검사가 같은 목록을 쓰도록 여기에만 둔다.
TEXT_SUFFIXES = {
    ".py", ".ipynb", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".json", ".md", ".txt",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env", ".xml", ".html",
    ".htm", ".css", ".scss", ".sql", ".sh", ".bash", ".ps1", ".psm1", ".bat", ".cmd", ".r",
    ".java", ".kt", ".go", ".rs", ".cs", ".c", ".h", ".cpp", ".hpp", ".rb", ".php", ".tf",
    ".gradle",
}
TEXT_NAMES = {"dockerfile", "makefile", "jenkinsfile", "procfile"}

REQUIRED_KEYS = {
    "secret": ("filename_patterns", "filename_allow", "content_patterns"),
    "data": ("extensions", "json_allow", "json_max_kib", "file_max_mib"),
}


class RulesError(Exception):
    """규칙 파일을 믿을 수 없을 때 올린다. 검사 없이 저장하는 길을 막는다."""


def load(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RulesError(f"규칙 파일이 없다: {path}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RulesError(f"규칙 파일 JSON 이 깨졌다: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise RulesError(f"규칙 파일의 최상위가 객체가 아니다: {path}")
    for section, keys in REQUIRED_KEYS.items():
        for key in keys:
            if key not in (data.get(section) or {}):
                raise RulesError(f"규칙 파일에 {section}.{key} 가 없다: {path}")
    patterns = data["secret"]["content_patterns"]
    if not patterns:
        raise RulesError(
            "비밀값 내용 정규식이 비어 있다. 파일 이름 패턴만으로는 코드에 적힌 비밀값을 찾지 못한다."
        )
    for rule in patterns:
        try:
            re.compile(rule["regex"])
        except (KeyError, TypeError, re.error) as exc:
            raise RulesError(f"내용 정규식 {rule.get('name')} 을 읽지 못했다: {exc}") from exc
    return data


def is_text_path(path):
    name = PurePosixPath(path).name.lower()
    return name in TEXT_NAMES or name.startswith(".env") or PurePosixPath(name).suffix in TEXT_SUFFIXES


def decode(raw):
    # 한국어 Windows 에서 만든 파일은 cp949 일 수 있다. 둘 다 아니면 내용 검사를 하지 않는다.
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _matches(path, pattern):
    # Windows 의 fnmatch 는 대소문자를 가리지 않는다. .ENV 도 .env 로 본다.
    return fnmatch.fnmatch(PurePosixPath(path).name, pattern) or fnmatch.fnmatch(path, pattern)


def classify(data, path, size, text):
    """판정 결과를 (종류, 규칙 이름) 으로 돌려준다. 걸리지 않으면 None 이다."""
    secret = data["secret"]
    if not any(_matches(path, allow) for allow in secret["filename_allow"]):
        for rule in secret["filename_patterns"]:
            if _matches(path, rule["glob"]):
                return ("secret-filename", rule["name"])

    conf = data["data"]
    suffix = PurePosixPath(path).suffix.lower().lstrip(".")
    if suffix in conf["extensions"]:
        return ("data", "data-extension")
    if (suffix == "json" and size > conf["json_max_kib"] * 1024
            and not any(_matches(path, allow) for allow in conf["json_allow"])):
        return ("data", "data-json-size")
    if size > conf["file_max_mib"] * MIB:
        return ("data", "data-file-size")

    # 의존성 잠금 파일은 도구가 만드는 파일이라 패키지 이름이 대입 패턴에 잘못 해당한다(예: "js-tokens").
    content_allowed = any(_matches(path, allow) for allow in secret.get("content_allow", []))
    if text is not None and not content_allowed:
        for rule in secret["content_patterns"]:
            if re.search(rule["regex"], text):
                return ("secret-content", rule["name"])
    return None


def judge(data, path, size, read):
    """저장과 이력 검사가 함께 쓰는 입구다. 이름과 크기로 먼저 보고, 텍스트 파일일 때만 내용을 읽는다."""
    verdict = classify(data, path, size, None)
    if verdict is not None or not is_text_path(path):
        return verdict
    return classify(data, path, size, decode(read()))

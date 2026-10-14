"""레포를 이 PC 에서 실행하고 끈다. 캡처 단계가 쓴다.

    python run_repo.py exec <레포> -- <명령…>        # 사내 인증서 묶음을 SSL_CERT_FILE 로 주고 명령을 실행
    python run_repo.py plan <레포>                   # 설치 · 실행 계획만 출력
    python run_repo.py --check                       # 붙박이 예제로 자체 검사

토큰은 화면 · 파일 · 명령줄에 남기지 않고 하위 프로세스 환경변수로만 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

APP_ID = "2826312"            # Kiwoom-ESG gen_token.sh · backend/Dockerfile 에 적힌 공개 식별자
INSTALLATION_ID = "108948292"
GIT_URL = re.compile(r"git\+https://github\.com/[^\s\"'\\]+")
UVICORN_APP = re.compile(r"[\w.]+:[\w]+")


class RepoError(Exception):
    pass


def ca_bundle(repo: Path, out_dir: Path) -> Path | None:
    crt = repo / "certs" / "ePrism.crt"
    if not crt.exists():
        return None
    pems = []
    if hasattr(ssl, "enum_certificates"):  # 윈도우 인증서 저장소
        for der, enc, _ in ssl.enum_certificates("ROOT"):
            if enc == "x509_asn":
                pems.append(ssl.DER_cert_to_PEM_cert(der))
    else:
        cafile = ssl.get_default_verify_paths().cafile
        if cafile and Path(cafile).exists():
            pems.append(Path(cafile).read_text(encoding="utf-8"))
    out = out_dir / "ca-bundle.pem"
    out.write_text("".join(pems) + "\n" + crt.read_text(encoding="utf-8"), encoding="utf-8")
    return out


def mask(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def git_token_env(token: str) -> dict[str, str]:
    return {"GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.https://x-access-token:{token}@github.com/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/"}


def free_port(preferred: int | None = None) -> int:
    if preferred:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dirs(repo: Path):
    yield repo
    for d in sorted(repo.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in ("node_modules", "docs"):
            yield d


def _node_service(d: Path) -> dict | None:
    pj = d / "package.json"
    if not pj.exists():
        return None
    pkg = json.loads(pj.read_text(encoding="utf-8"))
    if "dev" not in (pkg.get("scripts") or {}):
        return None
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    # dev 스크립트가 박아 둔 호스트 · 포트를 피하려고 스크립트를 거치지 않고 실행 파일을 직접 부른다
    if "next" in deps:
        run = ["npm", "exec", "--", "next", "dev", "-H", "127.0.0.1", "-p", "{port}"]
    elif "vite" in deps:
        run = ["npm", "exec", "--", "vite", "--host", "127.0.0.1", "--port", "{port}", "--strictPort"]
    else:
        raise RepoError(f"{d.name}: Next.js · Vite 가 아닌 dev 스크립트는 아직 실행 방법을 모릅니다")
    if (d / "node_modules").exists():
        install = []
    else:
        install = [["npm", "ci"] if (d / "package-lock.json").exists() else ["npm", "install", "--no-save"]]
    return {"name": "frontend", "cwd": str(d), "install": install, "run": run, "preferred": None}


def _py_service(d: Path, private: list[str]) -> dict | None:
    pyproject, req = d / "pyproject.toml", d / "requirements.txt"
    if not (pyproject.exists() or req.exists()):
        return None
    docker = d / "Dockerfile"
    text = docker.read_text(encoding="utf-8") if docker.exists() else ""
    for url in GIT_URL.findall(text):
        if url not in private:
            private.append(url)
    app, preferred = None, None
    for line in text.splitlines():
        if "uvicorn" in line:
            found = [t for t in re.findall(r"[\w.:-]+", line) if UVICORN_APP.fullmatch(t)]
            app = app or (found[0] if found else None)
            pm = re.search(r"--port[\"',\s]+(\d+)", line)
            preferred = preferred or (int(pm.group(1)) if pm else None)
    if not app:
        raise RepoError(f"{d.name}: 백엔드 시작 명령(uvicorn 모듈:앱)을 찾지 못했습니다")
    if pyproject.exists() and (d / "uv.lock").exists():
        install = [["uv", "sync", "--frozen"]]
    else:
        install = [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt" if req.exists() else "pyproject.toml"]]
    run = ["uv", "run", "--no-sync", "uvicorn", app, "--host", "127.0.0.1", "--port", "{port}"]
    return {"name": "backend", "cwd": str(d), "install": install, "run": run, "preferred": preferred}


def plan(repo: Path) -> dict:
    services, private, notes = [], [], []
    back = front = None
    for d in _dirs(repo):
        back = back or _py_service(d, private)
        front = front or _node_service(d)
    for svc in (back, front):  # 프론트엔드가 백엔드에 붙으므로 백엔드를 먼저 실행한다
        if svc:
            svc["port"] = free_port(svc["preferred"])
            if svc["preferred"] and svc["port"] != svc["preferred"]:
                notes.append(f"{svc['name']} 포트 {svc['preferred']} 이 쓰이고 있어 {svc['port']} 로 실행합니다")
            svc["run"] = [str(svc["port"]) if t == "{port}" else t for t in svc["run"]]
            services.append(svc)
    if not services:
        raise RepoError("이 레포의 실행 방법을 찾지 못했습니다(package.json 의 dev 스크립트나 파이썬 백엔드가 없습니다)")
    return {"services": services, "private": private, "notes": notes}


def _exec(repo: Path, cmd: list[str]) -> int:
    env = dict(os.environ)
    bundle = ca_bundle(repo, Path(tempfile.mkdtemp(prefix="code-flow-")))
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    return subprocess.call([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], env=env)


def _check() -> int:
    import tempfile
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        nxt = root / "nextrepo"; nxt.mkdir()
        (nxt / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev -H 0.0.0.0 -p 3000"}, "dependencies": {"next": "14"}}), encoding="utf-8")
        (nxt / "package-lock.json").write_text("{}", encoding="utf-8")
        p = plan(nxt)
        run = p["services"][0]["run"]
        expect("Next 레포는 npm ci 로 설치한다", p["services"][0]["install"] == [["npm", "ci"]])
        expect("dev 스크립트를 거치지 않고 루프백으로 실행한다", run[:5] == ["npm", "exec", "--", "next", "dev"] and "127.0.0.1" in run and "0.0.0.0" not in run)

        py = root / "pyrepo"; (py / "backend").mkdir(parents=True)
        (py / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (py / "backend" / "Dockerfile").write_text(
            'RUN uv pip install "git+https://github.com/KiwoomAM/Kiwoom-Manager.git@main#subdirectory=llm-manager"\n'
            'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]\n', encoding="utf-8")
        p = plan(py)
        svc = p["services"][0]
        expect("Dockerfile 에서 uvicorn 진입점을 찾는다", "main:app" in svc["run"] and "127.0.0.1" in svc["run"])
        expect("Dockerfile 의 포트를 선호 포트로 쓴다", svc["preferred"] == 8002)
        expect("Dockerfile 의 사설 패키지를 찾는다", p["private"] == ["git+https://github.com/KiwoomAM/Kiwoom-Manager.git@main#subdirectory=llm-manager"])
        expect("requirements 레포는 uv venv 뒤 uv pip install 로 설치한다", svc["install"][:2] == [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt"]])

        empty = root / "empty"; empty.mkdir()
        try:
            plan(empty)
            expect("실행 방법이 없는 레포는 오류를 낸다", False)
        except RepoError as e:
            expect("실행 방법이 없는 레포는 오류를 낸다", "실행 방법" in str(e))

        crt = root / "certs"; crt.mkdir()
        (crt / "ePrism.crt").write_text("-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n", encoding="utf-8")
        b = ca_bundle(root, root)
        text = b.read_text(encoding="utf-8") if b else ""
        expect("인증서 묶음 끝에 ePrism 이 붙는다", text.rstrip().endswith("-----END CERTIFICATE-----") and "AAAA" in text)
        expect("ePrism 이 없으면 묶음을 만들지 않는다", ca_bundle(nxt, root) is None)

    secret = "ghs_abcdef123456"
    expect("토큰을 *** 로 가린다", mask(f"fatal: https://x-access-token:{secret}@github.com/x", secret) == "fatal: https://x-access-token:***@github.com/x")
    env = git_token_env(secret)
    expect("git 설정은 환경변수 세 개로 넘긴다", env["GIT_CONFIG_COUNT"] == "1" and env["GIT_CONFIG_VALUE_0"] == "https://github.com/" and secret in env["GIT_CONFIG_KEY_0"])

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); s.listen(); busy = s.getsockname()[1]
        expect("선호 포트가 쓰이고 있으면 다른 포트를 고른다", free_port(busy) != busy)
    return 0 if ok else 1


def main() -> int:
    # PYTHONUTF8=1 을 준 것과 같은 결과다. 그 값이 없는 윈도우 PC 에서도 한국어 출력이 깨지지 않는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p_exec = sub.add_parser("exec")
    p_exec.add_argument("repo")
    p_exec.add_argument("rest", nargs=argparse.REMAINDER)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("repo")
    a = ap.parse_args()
    if a.check:
        return _check()
    try:
        if a.cmd == "exec":
            rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
            return _exec(Path(a.repo).resolve(), rest)
        if a.cmd == "plan":
            print(json.dumps(plan(Path(a.repo).resolve()), ensure_ascii=False, indent=2))
            return 0
    except RepoError as e:
        print(str(e))
        return 2
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""레포를 이 PC 에서 실행하고 끈다. 캡처 단계가 쓴다.

    python run_repo.py exec <레포> -- <명령…>        # 사내 인증서 묶음을 SSL_CERT_FILE 로 주고 명령을 실행
    python run_repo.py plan <레포>                   # 설치 · 실행 계획만 출력
    python run_repo.py doctor <레포>                 # 도구와 토큰 발급이 되는지 확인(토큰은 출력하지 않음)
    python run_repo.py start <레포> --state <파일>   # 설치하고 서버를 실행한 뒤 주소를 출력
    python run_repo.py start <레포> --state <파일> --cmd "<시작 명령>" --port <포트>   # 판별하지 못하는 레포
    python run_repo.py stop --state <파일>           # 서버를 끄고 레포의 추적 파일이 바뀌었는지 알림
    python run_repo.py --check                       # 붙박이 예제로 자체 검사

토큰은 화면 · 파일 · 명령줄에 남기지 않고 하위 프로세스 환경변수로만 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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


def ssl_file(repo: Path, out_dir: Path) -> Path | None:
    # 컨트롤 타워 설치기가 윈도우 PC 에 사내 인증서 묶음을 SSL_CERT_FILE 로 설정해 둔다. 그 값이 없을 때(WSL)만 레포의 인증서로 만든다
    given = os.environ.get("SSL_CERT_FILE")
    if given and Path(given).is_file():
        return Path(given)
    return ca_bundle(repo, out_dir)


def listen_hosts(text: str, port: int) -> list[str]:
    """netstat -ano 나 ss -ltn 출력에서 그 포트로 듣고 있는 연결 주소를 모은다."""
    hosts = []
    for line in text.splitlines():
        if "LISTEN" not in line:
            continue
        for tok in line.split():
            host, sep, p = tok.rpartition(":")
            if sep and p == str(port):
                hosts.append(host.strip("[]"))
                break
    return hosts


def only_loopback(hosts: list[str]) -> bool:
    return bool(hosts) and all(h in ("127.0.0.1", "::1") for h in hosts)


def _listening(port: int) -> list[str]:
    cmd = ["netstat", "-ano", "-p", "TCP"] if os.name == "nt" else ["ss", "-ltnH"]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout
    if os.name == "nt":
        out += subprocess.run(["netstat", "-ano", "-p", "TCPv6"], capture_output=True, text=True, errors="replace").stdout
    return listen_hosts(out, port)


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


def _cmd_service(repo: Path, cmd: str, port: int) -> dict:
    """판별하지 못하는 레포를 주 세션이 찾은 시작 명령과 포트로 실행한다."""
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            raise RepoError(f"포트 {port} 이 이미 쓰이고 있어 실행하지 않았습니다. 그 포트를 쓰는 프로그램을 닫은 뒤 다시 시도해 주십시오")
    run = shlex.split(cmd, posix=os.name != "nt")
    install = []
    if (repo / "requirements.txt").exists() or (repo / "pyproject.toml").exists():
        if (repo / "pyproject.toml").exists() and (repo / "uv.lock").exists():
            install = [["uv", "sync", "--frozen"]]
        else:
            install = [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt" if (repo / "requirements.txt").exists() else "pyproject.toml"]]
        if run and run[0] in ("python", "python3", "py"):
            run[0] = str(repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    elif (repo / "package.json").exists() and not (repo / "node_modules").exists():
        install = [["npm", "ci"] if (repo / "package-lock.json").exists() else ["npm", "install", "--no-save"]]
    return {"name": "app", "cwd": str(repo), "install": install, "run": run, "preferred": port, "port": port, "fixed_port": True}


def plan(repo: Path, cmd: str | None = None, port: int | None = None) -> dict:
    if cmd:
        if not port:
            raise RepoError("--cmd 를 쓸 때는 --port 도 함께 지정해야 합니다")
        return {"services": [_cmd_service(repo, cmd, port)], "private": [], "notes": []}
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


def github_token(repo: Path, bundle: Path | None) -> str:
    import jwt  # uv run --with "pyjwt[crypto]" 로 들어온다
    pem = repo / "certs" / "kiwoom.pem"
    if not pem.exists():
        raise RepoError("certs/kiwoom.pem 이 없어 사내 패키지를 설치할 수 없습니다")
    now = int(time.time())
    tok = jwt.encode({"iat": now - 60, "exp": now + 600, "iss": APP_ID}, pem.read_text(encoding="utf-8"), algorithm="RS256")
    req = urllib.request.Request(f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens", method="POST",
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    ctx = ssl.create_default_context(cafile=str(bundle)) if bundle else ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.load(r)["token"]


def _needs_token(p: dict) -> bool:
    if p["private"]:
        return True
    for s in p["services"]:
        for name in ("requirements.txt", "pyproject.toml"):
            f = Path(s["cwd"]) / name
            if f.exists() and "git+https" in f.read_text(encoding="utf-8", errors="ignore"):
                return True
    return False


def _run_logged(cmd: list[str], cwd: str, env: dict, log: Path, secret: str) -> None:
    r = subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    with log.open("a", encoding="utf-8") as f:
        f.write(mask(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n", secret))
    if r.returncode != 0:
        raise RepoError(f"설치 명령 {' '.join(cmd)} 가 실패했습니다. 기록: {log}")


def _git_status(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True)
    return sorted(r.stdout.splitlines())


def _wait_http(port: int, proc: subprocess.Popen, seconds: int = 180) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # 오류 응답이라도 오면 서버는 떠 있다
        except Exception:
            time.sleep(1)
    return False


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def start(repo: Path, state_path: Path, cmd: str | None = None, port: int | None = None) -> dict:
    p = plan(repo, cmd, port)
    tmp = state_path.parent
    tmp.mkdir(parents=True, exist_ok=True)
    log = tmp / "run_repo.log"
    env = dict(os.environ)
    bundle = ssl_file(repo, tmp)
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    token = github_token(repo, bundle) if _needs_token(p) else ""
    inst_env = {**env, **(git_token_env(token) if token else {})}
    state = {"repo": str(repo), "git_before": _git_status(repo), "pids": [], "notes": p["notes"]}
    try:
        for svc in p["services"]:
            for cmd in svc["install"]:
                _run_logged(cmd, svc["cwd"], inst_env, log, token)
            if svc["name"] == "backend" and p["private"]:
                _run_logged(["uv", "pip", "install", *p["private"]], svc["cwd"], inst_env, log, token)
            out = (tmp / f"{svc['name']}.log").open("w", encoding="utf-8")
            kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            proc = subprocess.Popen([shutil.which(svc["run"][0]) or svc["run"][0], *svc["run"][1:]], cwd=svc["cwd"], env=env,
                                    stdout=out, stderr=subprocess.STDOUT, **kw)
            state["pids"].append(proc.pid)
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            if not _wait_http(svc["port"], proc):
                raise RepoError(f"{svc['name']} 서버가 응답하지 않습니다. 기록: {tmp / (svc['name'] + '.log')}")
            hosts = _listening(svc["port"])
            if not only_loopback(hosts):
                raise RepoError(f"{svc['name']} 서버가 이 PC 밖에서도 접속되는 주소({', '.join(hosts) or '알 수 없음'})에 열려 바로 껐습니다")
            state["url"] = f"http://127.0.0.1:{svc['port']}"
    except Exception:
        stop(state_path)
        raise
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return {"url": state["url"], "notes": state["notes"]}


def stop(state_path: Path) -> list[str]:
    if not state_path.exists():
        return []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for pid in reversed(state.get("pids", [])):
        _kill_tree(pid)
    after = _git_status(Path(state["repo"]))
    return [line for line in after if line not in state.get("git_before", [])]


def doctor(repo: Path) -> int:
    ok = True
    for tool in ("git", "uv", "node", "npm"):
        found = shutil.which(tool) is not None
        print(("있음  " if found else "없음  ") + tool)
        ok = ok and (found or tool in ("node", "npm"))  # Node 는 Node 레포에만 필요하다
    chrome = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    print(("있음  " if chrome.exists() or shutil.which("google-chrome") else "없음  ") + "Chrome")
    if (repo / "certs" / "kiwoom.pem").exists():
        try:
            github_token(repo, ssl_file(repo, Path(tempfile.mkdtemp(prefix="code-flow-"))))
            print("있음  사내 패키지 토큰 발급")
        except Exception as e:
            ok = False
            print(f"없음  사내 패키지 토큰 발급 ({type(e).__name__})")
    return 0 if ok else 1


def _exec(repo: Path, cmd: list[str]) -> int:
    env = dict(os.environ)
    bundle = ssl_file(repo, Path(tempfile.mkdtemp(prefix="code-flow-")))
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

    with tempfile.TemporaryDirectory() as t:
        app = Path(t) / "stdlibapp"; app.mkdir()
        (app / "requirements.txt").write_text("pywin32==312\n", encoding="utf-8")
        p = plan(app, cmd="python -m src.app", port=free_port())
        svc = p["services"][0]
        py = str(app / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        expect("--cmd 레포는 uv venv 뒤 requirements 로 설치한다", svc["install"] == [["uv", "venv"], ["uv", "pip", "install", "-r", "requirements.txt"]])
        expect("--cmd 의 python 은 레포 가상환경의 python 으로 바꾼다", svc["run"] == [py, "-m", "src.app"] and svc["fixed_port"])
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); s.listen(); busy = s.getsockname()[1]
            try:
                plan(app, cmd="python -m src.app", port=busy)
                expect("고정 포트가 쓰이고 있으면 다른 프로그램을 건드리지 않고 멈춘다", False)
            except RepoError as e:
                expect("고정 포트가 쓰이고 있으면 다른 프로그램을 건드리지 않고 멈춘다", str(busy) in str(e))

    win = ("  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       1234\n"
           "  TCP    0.0.0.0:3012           0.0.0.0:0              LISTENING       99\n"
           "  TCP    [::1]:8765             [::]:0                 LISTENING       1234\n")
    posix = ("LISTEN 0 511 127.0.0.1:46991 0.0.0.0:*\nLISTEN 0 511 0.0.0.0:3012 0.0.0.0:*\nLISTEN 0 511 [::]:3012 [::]:*\n")
    expect("netstat 출력에서 포트의 연결 주소를 읽는다", sorted(listen_hosts(win, 8765)) == ["127.0.0.1", "::1"])
    expect("ss 출력에서 바깥 연결 주소를 읽는다", sorted(listen_hosts(posix, 3012)) == ["0.0.0.0", "::"])
    expect("루프백만이면 안전하다", only_loopback(["127.0.0.1", "::1"]) and not only_loopback(["0.0.0.0"]) and not only_loopback([]))

    with tempfile.TemporaryDirectory() as t:
        given = Path(t) / "corp.pem"; given.write_text("x", encoding="utf-8")
        old = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = str(given)
        try:
            expect("PC 에 설정된 SSL_CERT_FILE 을 먼저 쓴다", ssl_file(Path(t), Path(t)) == given)
        finally:
            if old is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = old

    with tempfile.TemporaryDirectory() as t:
        st = Path(t) / "state.json"
        st.write_text(json.dumps({"repo": t, "pids": [999999], "git_before": []}), encoding="utf-8")
        try:
            stop(st); stop(st)
            expect("이미 꺼진 프로세스를 두 번 꺼도 오류가 없다", True)
        except Exception as e:
            expect(f"이미 꺼진 프로세스를 두 번 꺼도 오류가 없다 ({e})", False)
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
    p_doc = sub.add_parser("doctor")
    p_doc.add_argument("repo")
    p_start = sub.add_parser("start")
    p_start.add_argument("repo")
    p_start.add_argument("--state", required=True)
    p_start.add_argument("--cmd", help="판별하지 못하는 레포의 시작 명령(예: \"python -m src.app\")")
    p_start.add_argument("--port", type=int, help="--cmd 로 실행한 서버의 포트")
    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--state", required=True)
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
        if a.cmd == "doctor":
            return doctor(Path(a.repo).resolve())
        if a.cmd == "start":
            print(json.dumps(start(Path(a.repo).resolve(), Path(a.state).resolve(), a.cmd, a.port), ensure_ascii=False))
            return 0
        if a.cmd == "stop":
            changed = stop(Path(a.state).resolve())
            if changed:
                print("레포의 추적 파일이 바뀌었습니다:\n" + "\n".join(changed))
                return 3
            print("서버를 껐습니다. 레포의 추적 파일은 그대로입니다.")
            return 0
    except RepoError as e:
        print(str(e))
        return 2
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""캡처 단계가 쓰는 실행 도구다. 백엔드는 실행하지 않고, Node 화면의 개발 서버만 띄웠다가 끈다.

    python run_repo.py exec <레포> -- <명령…>        # 사내 인증서 묶음을 SSL_CERT_FILE 로 주고 명령을 실행
    python run_repo.py plan <레포>                   # Node 화면의 설치 · 실행 계획만 출력
    python run_repo.py doctor                        # 필요한 도구가 있는지 확인
    python run_repo.py start <레포> --state <파일>   # Node 화면을 설치하고 개발 서버를 띄운 뒤 주소를 출력
    python run_repo.py stop --state <파일>           # 개발 서버를 끄고 레포의 추적 파일이 바뀌었는지 알림
    python run_repo.py --check                       # 붙박이 예제로 자체 검사

정적 HTML 화면은 서버를 띄우지 않는다. capture.py 가 레포 파일로 바로 응답한다.
"""
from __future__ import annotations

import argparse
import json
import os
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
    if os.name == "nt":
        out = "".join(subprocess.run(["netstat", "-ano", "-p", proto], capture_output=True, text=True, errors="replace").stdout
                      for proto in ("TCP", "TCPv6"))
    else:
        out = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, errors="replace").stdout
    return listen_hosts(out, port)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dirs(repo: Path):
    """레포 루트와 그 아래 2단계까지의 폴더(src/frontend 같은 구조)를 차례로 낸다."""
    skip = ("node_modules", "docs", "dist", "build")
    yield repo
    for d in sorted(repo.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in skip:
            yield d
            for dd in sorted(d.iterdir()):
                if dd.is_dir() and not dd.name.startswith(".") and dd.name not in skip:
                    yield dd


def _node_service(d: Path) -> dict | None:
    pj = d / "package.json"
    if not pj.exists():
        return None
    pkg = json.loads(pj.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts") or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    cra = "react-scripts" in deps and "start" in scripts  # Create React App 은 dev 대신 start 로 띄운다
    if "dev" not in scripts and not cra:
        return None
    env = {}
    # 스크립트가 박아 둔 호스트 · 포트를 피하려고 스크립트를 거치지 않고 실행 파일을 직접 부른다
    if "next" in deps:
        run = ["npm", "exec", "--", "next", "dev", "-H", "127.0.0.1", "-p", "{port}"]
    elif "vite" in deps:
        run = ["npm", "exec", "--", "vite", "--host", "127.0.0.1", "--port", "{port}", "--strictPort"]
    elif cra:
        # react-scripts 는 호스트 · 포트를 환경변수로 받는다. BROWSER=none 은 브라우저 창을 저절로 열지 않게 한다
        run = ["npm", "exec", "--", "react-scripts", "start"]
        env = {"HOST": "127.0.0.1", "PORT": "{port}", "BROWSER": "none"}
    else:
        # 모노레포 루트의 dev 처럼 화면이 아닌 스크립트일 수 있으므로 여기서 멈추지 않고 다음 폴더를 찾게 한다
        return {"unknown": d.name}
    if (d / "node_modules").exists():
        install = []
    else:
        install = [["npm", "ci"] if (d / "package-lock.json").exists() else ["npm", "install", "--no-save"]]
    return {"cwd": str(d), "install": install, "run": run, "env": env}


def plan(repo: Path) -> dict:
    unknown = []
    for d in _dirs(repo):
        svc = _node_service(d)
        if svc and "unknown" in svc:
            unknown.append(svc["unknown"])
            continue
        if svc:
            port = free_port()
            svc["port"] = port
            svc["run"] = [str(port) if t == "{port}" else t for t in svc["run"]]
            svc["env"] = {k: str(port) if v == "{port}" else v for k, v in svc["env"].items()}
            return svc
    if unknown:
        raise RepoError(f"{', '.join(unknown)}: Next.js · Vite · Create React App 이 아닌 화면은 아직 띄우는 방법을 모릅니다")
    raise RepoError("이 레포에서 Node 화면(package.json 의 dev 스크립트, 또는 Create React App 의 start 스크립트)을 찾지 못했습니다")


def _run_logged(cmd: list[str], cwd: str, env: dict, log: Path) -> None:
    r = subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    with log.open("a", encoding="utf-8") as f:
        f.write(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n")
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


def start(repo: Path, state_path: Path) -> dict:
    # 지난 실행이 남긴 상태 파일은 지우기만 한다. 오래된 파일의 프로그램 번호는 이미 다른 프로그램의 것일 수 있어 끄지 않는다.
    # 지워 두면 이번 설치가 실패해 stop 이 실행돼도 지난 실행의 번호를 읽지 않는다
    state_path.unlink(missing_ok=True)
    svc = plan(repo)
    tmp = state_path.parent
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    bundle = ssl_file(repo, tmp)
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    state = {"repo": str(repo), "git_before": _git_status(repo), "pids": []}
    try:
        for cmd in svc["install"]:
            try:
                _run_logged(cmd, svc["cwd"], env, tmp / "install.log")
            except RepoError:
                if cmd != ["npm", "ci"]:
                    raise
                # 잠금 파일이 package.json 과 맞지 않으면 npm ci 가 거절한다. 잠금 파일을 쓰지 않는 설치로 한 번 더 시도해
                # 레포의 추적 파일은 그대로 둔다
                _run_logged(["npm", "install", "--no-save", "--package-lock=false"], svc["cwd"], env, tmp / "install.log")
                state["lock_mismatch"] = True
        env.update(svc["env"])
        out = (tmp / "frontend.log").open("w", encoding="utf-8")
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        proc = subprocess.Popen([shutil.which(svc["run"][0]) or svc["run"][0], *svc["run"][1:]], cwd=svc["cwd"], env=env,
                                stdout=out, stderr=subprocess.STDOUT, **kw)
        state["pids"].append(proc.pid)
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        if not _wait_http(svc["port"], proc):
            raise RepoError(f"화면 개발 서버가 응답하지 않습니다. 기록: {tmp / 'frontend.log'}")
        hosts = _listening(svc["port"])
        if not only_loopback(hosts):
            raise RepoError(f"화면 개발 서버가 이 PC 밖에서도 접속되는 주소({', '.join(hosts) or '알 수 없음'})에 열려 바로 껐습니다")
    except Exception:
        stop(state_path)
        raise
    state["url"] = f"http://127.0.0.1:{svc['port']}"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    out = {"url": state["url"]}
    if state.get("lock_mismatch"):
        out["note"] = "package-lock.json 이 package.json 과 맞지 않아 잠금 파일 없이 설치했습니다. 사용자에게 알립니다"
    return out


def stop(state_path: Path) -> list[str]:
    if not state_path.exists():
        return []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for pid in reversed(state.get("pids", [])):
        _kill_tree(pid)
    # 끈 뒤 상태 파일을 지운다. 남겨 두면 다음 stop 이 이미 끝난 프로그램 번호를 다시 강제 종료하는데,
    # Windows 는 그 번호를 곧 다른 프로그램에 다시 주므로 사용자가 쓰던 프로그램이 꺼질 수 있다
    state_path.unlink(missing_ok=True)
    after = _git_status(Path(state["repo"]))
    return [line for line in after if line not in state.get("git_before", [])]


def doctor() -> int:
    ok = True
    for tool in ("uv", "node", "npm"):
        found = shutil.which(tool) is not None
        print(("있음  " if found else "없음  ") + tool)
        ok = ok and (found or tool in ("node", "npm"))  # Node 는 Node 화면에만 필요하다
    chrome = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    has_chrome = chrome.exists() or shutil.which("google-chrome") is not None
    print(("있음  " if has_chrome else "없음  ") + "Chrome")
    return 0 if ok and has_chrome else 1


def _exec(repo: Path, cmd: list[str]) -> int:
    env = dict(os.environ)
    bundle = ssl_file(repo, Path(tempfile.mkdtemp(prefix="code-flow-")))
    if bundle:
        env["SSL_CERT_FILE"] = str(bundle)
    return subprocess.call([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], env=env)


def _check() -> int:
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
        expect("Next 화면은 npm ci 로 설치한다", p["install"] == [["npm", "ci"]])
        expect("dev 스크립트를 거치지 않고 루프백으로 띄운다", p["run"][:5] == ["npm", "exec", "--", "next", "dev"] and "127.0.0.1" in p["run"] and "0.0.0.0" not in p["run"])

        tpl = root / "template"; (tpl / "src" / "frontend" / "node_modules").mkdir(parents=True)
        (tpl / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (tpl / "src" / "frontend" / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "6"}}), encoding="utf-8")
        p = plan(tpl)
        expect("src/frontend 처럼 2단계 아래의 화면도 찾는다", p["cwd"].replace("\\", "/").endswith("src/frontend"))
        expect("Vite 화면은 루프백 · 고정 포트로 띄운다", p["run"][3] == "vite" and "127.0.0.1" in p["run"] and "--strictPort" in p["run"])
        expect("node_modules 가 있으면 설치하지 않는다", p["install"] == [])

        cra = root / "crarepo"; (cra / "frontend").mkdir(parents=True)
        (cra / "frontend" / "package.json").write_text(json.dumps({"scripts": {"start": "DANGEROUSLY_DISABLE_HOST_CHECK=true react-scripts start"}, "dependencies": {"react-scripts": "5"}}), encoding="utf-8")
        p = plan(cra)
        expect("Create React App 화면은 start 스크립트로 찾고 react-scripts 를 직접 부른다", p["run"][3:] == ["react-scripts", "start"])
        expect("Create React App 은 루프백 · 빈 포트를 환경변수로 준다", p["env"].get("HOST") == "127.0.0.1" and p["env"].get("PORT") == str(p["port"]) and p["env"].get("BROWSER") == "none")

        mono = root / "monorepo"; (mono / "src" / "frontend").mkdir(parents=True)
        (mono / "package.json").write_text(json.dumps({"scripts": {"dev": "concurrently \"npm:api\" \"npm:web\""}}), encoding="utf-8")
        (mono / "src" / "frontend" / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "6"}}), encoding="utf-8")
        try:
            p = plan(mono)
            expect("루트의 dev 스크립트가 화면이 아니면 하위 폴더의 화면을 찾는다", p["cwd"].replace("\\", "/").endswith("src/frontend"))
        except RepoError as e:
            expect(f"루트의 dev 스크립트가 화면이 아니면 하위 폴더의 화면을 찾는다 ({e})", False)
        only = root / "onlyroot"; only.mkdir()
        (only / "package.json").write_text(json.dumps({"scripts": {"dev": "nodemon server.js"}}), encoding="utf-8")
        try:
            plan(only)
            expect("어느 폴더에도 아는 화면이 없으면 실행 방법을 모른다고 알린다", False)
        except RepoError as e:
            expect("어느 폴더에도 아는 화면이 없으면 실행 방법을 모른다고 알린다", "띄우는 방법을 모릅니다" in str(e) and "onlyroot" in str(e))

        empty = root / "static"; (empty / "src" / "web").mkdir(parents=True)
        try:
            plan(empty)
            expect("Node 화면이 없는 레포는 오류를 낸다", False)
        except RepoError as e:
            expect("Node 화면이 없는 레포는 오류를 낸다", "Node 화면" in str(e))

        crt = root / "certs"; crt.mkdir()
        (crt / "ePrism.crt").write_text("-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n", encoding="utf-8")
        b = ca_bundle(root, root)
        text = b.read_text(encoding="utf-8") if b else ""
        expect("인증서 묶음 끝에 ePrism 이 붙는다", text.rstrip().endswith("-----END CERTIFICATE-----") and "AAAA" in text)
        expect("ePrism 이 없으면 묶음을 만들지 않는다", ca_bundle(nxt, root) is None)

        given = root / "corp.pem"; given.write_text("x", encoding="utf-8")
        old = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = str(given)
        try:
            expect("PC 에 설정된 SSL_CERT_FILE 을 먼저 쓴다", ssl_file(root, root) == given)
        finally:
            if old is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = old

        st = root / "state.json"
        st.write_text(json.dumps({"repo": t, "pids": [999999], "git_before": []}), encoding="utf-8")
        try:
            stop(st); stop(st)
            expect("이미 꺼진 프로세스를 두 번 꺼도 오류가 없다", True)
        except Exception as e:
            expect(f"이미 꺼진 프로세스를 두 번 꺼도 오류가 없다 ({e})", False)

        # Windows 는 끝난 프로그램 번호를 곧 다른 프로그램에 다시 준다. 한 번 끈 번호를 다시 강제 종료하지 않아야 한다
        killed = []
        real_kill = globals()["_kill_tree"]
        globals()["_kill_tree"] = killed.append
        try:
            st.write_text(json.dumps({"repo": t, "pids": [999999], "git_before": []}), encoding="utf-8")
            stop(st); first = list(killed); stop(st)
            expect("stop 을 두 번 실행해도 두 번째는 아무 프로그램도 끄지 않는다", first == [999999] and killed == [999999] and not st.exists())
            # start 첫머리는 남은 상태 파일을 지우기만 하고 그 번호를 끄지 않는다. 화면이 없는 레포라 plan 에서 멈추게 해 확인한다
            st.write_text(json.dumps({"repo": t, "pids": [888888], "git_before": []}), encoding="utf-8")
            try:
                start(empty, st)
            except RepoError:
                pass
            expect("start 는 지난 실행의 상태 파일을 지우기만 하고 그 프로그램은 끄지 않는다", 888888 not in killed and not st.exists())
        finally:
            globals()["_kill_tree"] = real_kill

    win = ("  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       1234\n"
           "  TCP    0.0.0.0:3012           0.0.0.0:0              LISTENING       99\n"
           "  TCP    [::1]:8765             [::]:0                 LISTENING       1234\n")
    posix = "LISTEN 0 511 127.0.0.1:46991 0.0.0.0:*\nLISTEN 0 511 0.0.0.0:3012 0.0.0.0:*\nLISTEN 0 511 [::]:3012 [::]:*\n"
    expect("netstat 출력에서 포트의 연결 주소를 읽는다", sorted(listen_hosts(win, 8765)) == ["127.0.0.1", "::1"])
    expect("ss 출력에서 바깥 연결 주소를 읽는다", sorted(listen_hosts(posix, 3012)) == ["0.0.0.0", "::"])
    expect("루프백만이면 안전하다", only_loopback(["127.0.0.1", "::1"]) and not only_loopback(["0.0.0.0"]) and not only_loopback([]))
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
    sub.add_parser("doctor")
    p_start = sub.add_parser("start")
    p_start.add_argument("repo")
    p_start.add_argument("--state", required=True)
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
            return doctor()
        if a.cmd == "start":
            print(json.dumps(start(Path(a.repo).resolve(), Path(a.state).resolve()), ensure_ascii=False))
            return 0
        if a.cmd == "stop":
            changed = stop(Path(a.state).resolve())
            if changed:
                print("레포의 추적 파일이 바뀌었습니다:\n" + "\n".join(changed))
                return 3
            print("개발 서버를 껐습니다. 레포의 추적 파일은 그대로입니다.")
            return 0
    except RepoError as e:
        print(str(e))
        return 2
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

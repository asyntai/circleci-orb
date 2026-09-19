#!/usr/bin/env python3
"""Test the orb the way CircleCI runs it.

The test does not run sync.py directly. It reads the PACKED orb, takes the
shell command out of the sync step, undoes the `\\<<` escape that CircleCI
undoes at run time, and runs that exact text with bash against a stand-in API.
So what the test exercises is the artifact that ships.

Usage:
    python tests/run_tests.py <packed-orb.yml>
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API_KEY = "test-key-2f8a1c"

# Resolve bash once, from the PATH this process started with. On Windows the
# bare name "bash" can also reach the WSL bash, which does not receive the
# environment variables the test sets, so the absolute path matters.
BASH = shutil.which("bash") or "bash"
if os.name == "nt":
    _git_bash = "C:/Program Files/Git/usr/bin/bash.exe"
    if os.path.exists(_git_bash):
        BASH = _git_bash

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  PASS  %s" % name)
    else:
        FAILED.append((name, detail))
        print("  FAIL  %s" % name)
        if detail:
            print("        %s" % detail)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def extract_command(orb_path):
    with open(orb_path, "r", encoding="utf-8") as handle:
        orb = yaml.safe_load(handle)
    command = orb["commands"]["sync"]["steps"][0]["run"]["command"]
    # CircleCI turns the literal escape `\<<` back into `<<` before the shell
    # sees it. Do the same here.
    return command.replace("\\<<", "<<"), orb


def make_docs(base):
    docs = os.path.join(base, "docs")
    os.makedirs(os.path.join(docs, "guides"))
    os.makedirs(os.path.join(docs, "drafts"))
    files = {
        "index.md": "# Welcome\n\nAsyntai answers questions on your website.",
        "pricing.md": "# Pricing\n\nThe Starter plan covers one website.",
        "guides/setup.md": "# Setup\n\nPaste the script tag before the body ends.",
        "drafts/wip.md": "# Draft\n\nThis page is not ready for readers yet.",
        "tiny.md": "short",
        "logo.png": "not text at all, and not a pattern match either",
        "notes.txt": "Plain text notes that are long enough to send.",
    }
    for name, text in files.items():
        with open(os.path.join(docs, name), "w", encoding="utf-8") as handle:
            handle.write(text)
    return docs


def run_step(script, env_extra, cwd):
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(
        [BASH, os.path.basename(script)],
        cwd=cwd, env=env, capture_output=True, text=True,
    )
    return proc


def server_dump(dump_path):
    flag = dump_path + ".flush"
    open(flag, "w").close()
    for _ in range(100):
        if not os.path.exists(flag):
            break
        time.sleep(0.05)
    with open(dump_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def titles(dump):
    return sorted(entry["title"] for entry in dump["entries"])


def main():
    if len(sys.argv) < 2:
        print("Usage: run_tests.py <packed-orb.yml>", file=sys.stderr)
        return 2

    orb_path = sys.argv[1]
    command, orb = extract_command(orb_path)

    workdir = tempfile.mkdtemp(prefix="asyntai-orb-test-")
    script_path = os.path.join(workdir, "shipped_sync.sh")
    with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(command)

    # Windows ships a stub named python that only advertises the Store. Put a
    # real python3 at the front of PATH so the wrapper's own lookup succeeds.
    shim_dir = os.path.join(workdir, "shim")
    os.makedirs(shim_dir)
    shim = os.path.join(shim_dir, "python3")
    with open(shim, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('#!/bin/sh\nexec "%s" "$@"\n'
                     % sys.executable.replace(os.sep, "/"))
    os.chmod(shim, 0o755)

    docs = make_docs(workdir)
    port = free_port()
    dump_path = os.path.join(workdir, "server.json")

    server = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "fake_api.py"), str(port), dump_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:%d" % port

    # Wait for the stand-in API to answer.
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        print("The stand-in API did not start.", file=sys.stderr)
        server.kill()
        return 2

    base_env = {
        "PATH": shim_dir + os.pathsep + os.environ.get("PATH", ""),
        "ASYNTAI_API_KEY": API_KEY,
        "ASYNTAI_ORB_PATH": "docs",
        "ASYNTAI_ORB_BASE_URL": base_url,
        "ASYNTAI_ORB_KEY_VAR": "ASYNTAI_API_KEY",
    }

    try:
        print("\nStructure of the packed orb")
        check("the orb declares version 2.1", str(orb.get("version")) == "2.1",
              "version is %r" % orb.get("version"))
        check("the orb has a description",
              bool(orb.get("description", "").strip()))
        check("display.home_url and display.source_url are set",
              bool(orb.get("display", {}).get("home_url")) and
              bool(orb.get("display", {}).get("source_url")))
        check("the orb ships at least one usage example, which a public orb needs",
              len(orb.get("examples") or {}) >= 1,
              "examples: %s" % list((orb.get("examples") or {}).keys()))
        check("the sync command and the sync job both exist",
              "sync" in (orb.get("commands") or {}) and
              "sync" in (orb.get("jobs") or {}))
        check("path is the only parameter without a default",
              [name for name, spec in
               orb["commands"]["sync"]["parameters"].items()
               if "default" not in spec] == ["path"])
        check("the shipped command holds no unresolved escape",
              "\\<<" not in command)

        print("\nThe shell wrapper")
        syntax = subprocess.run(
            [BASH, "-n", os.path.basename(script_path)],
            cwd=workdir, capture_output=True, text=True)
        check("bash accepts the shipped script", syntax.returncode == 0,
              syntax.stderr.strip())

        print("\nFirst run, an empty knowledge base")
        proc = run_step(script_path, base_env, workdir)
        check("the step succeeds", proc.returncode == 0,
              proc.stdout[-600:] + proc.stderr[-600:])
        dump = server_dump(dump_path)
        expected = ["guides/setup.md", "index.md", "notes.txt", "pricing.md",
                    "drafts/wip.md"]
        check("every matching file became an entry",
              titles(dump) == sorted(expected),
              "got %s" % titles(dump))
        check("the file under ten characters was skipped",
              "tiny.md" not in titles(dump))
        check("the file that matches no pattern was skipped",
              "logo.png" not in titles(dump))
        check("the text of a file arrived whole",
              any(e["content"].startswith("# Pricing")
                  for e in dump["entries"]))
        check("no DELETE was sent when nothing was there",
              not any(c["method"] == "DELETE" for c in dump["calls"]))

        check("the output counts them as added",
              "%d added" % len(expected) in proc.stdout, proc.stdout[-300:])

        print("\nSecond run, nothing changed")
        first_ids = {e["title"]: e["id"] for e in dump["entries"]}
        posts_before = sum(1 for c in dump["calls"] if c["method"] == "POST")
        proc = run_step(script_path, base_env, workdir)
        check("the step succeeds again", proc.returncode == 0,
              proc.stdout[-600:] + proc.stderr[-600:])
        dump = server_dump(dump_path)
        check("the entry count did not grow, so nothing was duplicated",
              len(dump["entries"]) == len(expected),
              "%d entries" % len(dump["entries"]))
        second_ids = {e["title"]: e["id"] for e in dump["entries"]}
        check("every entry was left exactly as it was",
              first_ids == second_ids)
        check("no DELETE was sent",
              not any(c["method"] == "DELETE" for c in dump["calls"]))
        check("no text was sent again, so the daily limit is untouched",
              sum(1 for c in dump["calls"] if c["method"] == "POST") ==
              posts_before)
        check("the output counts them as unchanged",
              "%d unchanged" % len(expected) in proc.stdout,
              proc.stdout[-300:])

        print("\nChanged text")
        with open(os.path.join(docs, "pricing.md"), "w", encoding="utf-8") as h:
            h.write("# Pricing\n\nThe Standard plan covers three websites.")
        proc = run_step(script_path, base_env, workdir)
        dump = server_dump(dump_path)
        pricing = [e for e in dump["entries"] if e["title"] == "pricing.md"]
        check("the entry now holds the new text",
              len(pricing) == 1 and "Standard plan" in pricing[0]["content"],
              str(pricing))
        check("only the changed file was sent",
              "0 added, 1 updated, %d unchanged" % (len(expected) - 1)
              in proc.stdout, proc.stdout[-300:])

        print("\nThe exclude parameter")
        env = dict(base_env, ASYNTAI_ORB_EXCLUDE="drafts/*")
        proc = run_step(script_path, env, workdir)
        check("the step succeeds", proc.returncode == 0, proc.stderr[-400:])
        check("the excluded folder is named in no line of the output",
              "drafts/wip.md" not in proc.stdout.replace("skip", ""),
              proc.stdout[-400:])

        print("\nThe title prefix")
        env = dict(base_env, ASYNTAI_ORB_TITLE_PREFIX="Docs / ")
        run_step(script_path, env, workdir)
        dump = server_dump(dump_path)
        check("the prefix is on the titles",
              "Docs / index.md" in titles(dump), str(titles(dump)))
        check("the run without a prefix left its own entries in place",
              "index.md" in titles(dump))

        print("\nPrune")
        prune_env = dict(base_env, ASYNTAI_ORB_TITLE_PREFIX="Docs / ",
                         ASYNTAI_ORB_PRUNE="true")
        run_step(script_path, prune_env, workdir)
        os.remove(os.path.join(docs, "notes.txt"))
        proc = run_step(script_path, prune_env, workdir)
        check("the step succeeds", proc.returncode == 0, proc.stderr[-400:])
        dump = server_dump(dump_path)
        check("the entry of the deleted file is gone",
              "Docs / notes.txt" not in titles(dump), str(titles(dump)))
        check("the entries without the prefix were not touched",
              "notes.txt" in titles(dump), str(titles(dump)))
        check("the output counts the deletion",
              "1 deleted" in proc.stdout, proc.stdout[-300:])

        print("\nPrune without a title prefix")
        proc = run_step(script_path, dict(base_env, ASYNTAI_ORB_PRUNE="true"),
                        workdir)
        check("the step succeeds", proc.returncode == 0, proc.stderr[-400:])
        check("the output warns that prune was ignored",
              "prune was ignored" in proc.stdout, proc.stdout[-300:])
        check("nothing was deleted",
              "0 deleted" in proc.stdout, proc.stdout[-300:])

        print("\nDry run")
        calls_before = len(server_dump(dump_path)["calls"])
        env = dict(base_env, ASYNTAI_ORB_DRY_RUN="true")
        proc = run_step(script_path, env, workdir)
        check("the step succeeds", proc.returncode == 0, proc.stderr[-400:])
        check("the output says nothing was sent",
              "Nothing was sent" in proc.stdout, proc.stdout[-400:])
        check("the API was not called at all",
              len(server_dump(dump_path)["calls"]) == calls_before)

        print("\nA dry run needs no key")
        env = dict(base_env, ASYNTAI_ORB_DRY_RUN="true", ASYNTAI_API_KEY="")
        proc = run_step(script_path, env, workdir)
        check("the step still succeeds", proc.returncode == 0,
              proc.stderr[-400:])

        print("\nFailures are reported")
        env = dict(base_env, ASYNTAI_API_KEY="")
        proc = run_step(script_path, env, workdir)
        check("an empty key stops the step", proc.returncode != 0)
        check("the message names the variable to set",
              "ASYNTAI_API_KEY" in proc.stderr, proc.stderr[-400:])

        env = dict(base_env, ASYNTAI_API_KEY="wrong-key")
        proc = run_step(script_path, env, workdir)
        check("a wrong key stops the step", proc.returncode != 0)
        check("the message repeats what the API said",
              "Invalid API key" in (proc.stderr + proc.stdout),
              proc.stderr[-400:])

        env = dict(base_env, ASYNTAI_ORB_PATH="no-such-folder")
        proc = run_step(script_path, env, workdir)
        check("a missing folder stops the step", proc.returncode != 0)
        check("the message names the missing folder",
              "no-such-folder" in proc.stderr, proc.stderr[-400:])

        env = dict(base_env, ASYNTAI_ORB_PATTERNS="*.rst")
        proc = run_step(script_path, env, workdir)
        check("a pattern that matches nothing stops the step",
              proc.returncode != 0)

        env = dict(base_env, ASYNTAI_ORB_BASE_URL="http://127.0.0.1:1")
        proc = run_step(script_path, env, workdir)
        check("an unreachable server stops the step", proc.returncode != 0)
        check("the message says the server could not be reached",
              "Cannot reach" in proc.stderr, proc.stderr[-400:])

        print("\nA single file as the path")
        env = dict(base_env, ASYNTAI_ORB_PATH="docs/index.md")
        proc = run_step(script_path, env, workdir)
        check("the step succeeds", proc.returncode == 0, proc.stderr[-400:])
        check("the title is the file name on its own",
              "index.md" in titles(server_dump(dump_path)))

        print("\nA custom key variable")
        env = dict(base_env, ASYNTAI_ORB_KEY_VAR="MY_OWN_KEY",
                   ASYNTAI_API_KEY="", MY_OWN_KEY=API_KEY)
        proc = run_step(script_path, env, workdir)
        check("the step reads the key from the named variable",
              proc.returncode == 0, proc.stderr[-400:])

    finally:
        open(dump_path + ".stop", "w").close()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n%d passed, %d failed." % (len(PASSED), len(FAILED)))
    for name, detail in FAILED:
        print("  FAILED: %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

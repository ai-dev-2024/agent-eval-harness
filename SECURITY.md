# Security

## Reporting a vulnerability

Open a private security advisory on this repository: **Security → Advisories → Report a
vulnerability** on the GitHub repository page. Do not open a public issue for security
problems, and do not post working exploits or credentials in issues or pull requests.

Include the affected version or commit, reproduction steps, and the impact you expect. Only
the latest commit on `main` is supported.

## Threat model

This harness **executes model-generated Python code** as the user running it. The temporary
workdir and the subprocess keep attempts from interfering with each other by accident. They
do not contain hostile code. A generated module or CLI agent can:

- read and write any file the user can, including the task's hidden tests on disk;
- open network connections;
- use unbounded CPU, memory and disk, or tamper with its own grading.

These are known limitations, not vulnerabilities. Reports that show the harness doing
something beyond them are in scope. Examples: leaking a configured API key into saved
artifacts, writing outside the run directory, or hanging past its configured timeouts.

## Running untrusted generations

Run on a disposable host or in a container with no sensitive bind mounts. The supplied image
runs as a non-root user. For the offline demo:

```sh
docker build -t agent-eval-harness .
docker run --rm --network none --memory 512m --cpus 2 --pids-limit 128 \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  agent-eval-harness run examples/mock-demo.yaml --out /tmp/demo
```

To keep the report without a bind mount, use a named container and copy the run out:

```sh
docker create --name eval-demo --network none --memory 512m --cpus 2 --pids-limit 128 \
  agent-eval-harness run examples/mock-demo.yaml --out runs/demo
docker start -a eval-demo
docker cp eval-demo:/app/runs/demo ./container-demo
docker rm eval-demo
```

Real API runs need network access. Generation and grading run in the same container, so
generated code sees the same network and the API keys in the environment. For real endpoints,
use short-lived keys with spending limits.

## Secrets in artifacts

Configs name environment variables rather than containing keys. Before any text is written to a
run directory, every configured `api_key_env` value is replaced with `[REDACTED]`. That is exact
matching on known keys. It won't catch other secrets that appear in prompts, generated code or
CLI output. HTTP errors are recorded as the status code only. Review a run directory before
sharing it.

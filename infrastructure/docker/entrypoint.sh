#!/bin/sh
# Entrypoint da API: garante que /app/var (Lakehouse, relatórios) seja gravável e roda o processo sem privilégios.
# Em hospedagens com disco persistente (ex.: Render) o volume pode montar como root; no docker compose já é do usuário.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/var
  chown -R goops:goops /app/var 2>/dev/null || true
  exec python -c 'import os, pwd, sys; p = pwd.getpwnam("goops"); os.setgroups([]); os.setgid(p.pw_gid); os.setuid(p.pw_uid); os.environ["HOME"] = p.pw_dir; os.execvp(sys.argv[1], sys.argv[1:])' "$@"
fi
exec "$@"
